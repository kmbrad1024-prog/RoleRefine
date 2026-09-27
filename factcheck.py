"""Automatic fact check: did the rewrite drop real facts about the job?

The LLM is told never to change facts, but this check doesn't take its word
for it. It pulls key facts out of the original (working conditions, pay terms,
experience years, who the role reports to) and warns when they're missing from
the rewrite. It needs no API calls, so it's fast, free and repeatable.

Two kinds of facts:
- MUST-KEEP facts (schedule, location/travel, pay, equipment, employment type,
  reporting line) should never disappear, even if the change was logged.
  They can be reworded, but a candidate needs to know them.
- CHECK facts (numbers such as years of experience) may legitimately change,
  so they're only flagged when the change log doesn't mention them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scoring import (_is_sub_intro, _looks_like_heading, count_optional, count_required,
                     next_section, reading_grade)

# Each concept: label shown to the user, and a regex. A concept "survives" if the
# rewrite matches the same regex (so rewording like "weekends" -> "weekend
# shifts" is fine).
MUST_KEEP = {
    "schedule": [
        ("long hours / overtime", r"long hours|overtime|extended hours|\d+\+? hours? (a|per) (week|day)"),
        ("weekends", r"weekends?"),
        ("evenings / nights", r"evenings?|nights?|overnight"),
        ("shift work", r"\bshifts?\b"),
        ("on-call", r"on[- ]call"),
    ],
    "location & travel": [
        ("relocation", r"relocat\w*"),
        ("travel", r"\btravel\w*"),
        ("commute / in-office", r"\bcommut\w*|\bin[- ]office\b|\bon[- ]?site\b|\bin person\b|\bdays? (a|per) week in\b"),
        ("driving / own vehicle", r"driver'?s licen[sc]e|\bcar\b|vehicle|reliable transportation"),
    ],
    "pay & employment type": [
        ("hourly pay", r"hourly|per hour|/hr\b|an hour\b"),
        ("commission", r"commission|\bOTE\b"),
        ("unpaid", r"unpaid"),
        ("contract / temporary", r"\bcontract\b|temporary|fixed[- ]term"),
        ("part-time", r"part[- ]time"),
    ],
    "equipment": [
        ("own laptop / equipment", r"laptop|own (computer|device|phone|equipment)"),
    ],
}

NUMBER_FACT = re.compile(
    r"(\$\s?\d[\d,.]*\s?[kK]?(\s?[-–]\s?\$?\s?\d[\d,.]*\s?[kK]?)?"      # pay: $70,000–$85,000
    r"|\d+\+?\s?(-|–|to)?\s?\d*\+?\s?years?"                          # 2+ years, 2-4 years
    r"|\d+(?:\.\d+)?\s?%?(?:\s?(?:-|–|to)\s?\d+(?:\.\d+)?)?\s?%"        # 30%, 0.25–0.5%
    r"|\d+\s?(paid )?(vacation |holi)?days?\b"                         # 20 paid vacation days
    r"|\d+\s?(lbs|pounds))",                                          # 50 lbs
    re.IGNORECASE,
)

REPORTS_TO = re.compile(
    r"report(?:s|ing)? (?:directly )?(?:in)?to (?:the |a |an |our )?"
    r"((?:[A-Z][\w&/-]*\s?){1,5})"
)

# Writing systems that shouldn't appear in a rewrite unless the original uses them
# (models occasionally emit stray characters, e.g. a Chinese word mid-paragraph).
FOREIGN_SCRIPTS = re.compile(
    r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u097F\u0E00-\u0E7F"
    r"\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]+"
)

# Words that mark a qualification as optional.
PREFERRED = re.compile(r"\b(strongly preferred|preferred|is a plus|a plus|nice to have|"
                       r"bonus|desired|ideally)\b", re.IGNORECASE)

# Accommodation wording belongs with physical tasks, not with licenses,
# credentials, location or travel.
NON_PHYSICAL = re.compile(r"licen[sc]e|certif|degree|diploma|travel|relocat|reside|"
                          r"located|commut|in[- ]person|on[- ]site", re.IGNORECASE)

# Capitalized words that aren't names of employers, clients or products.
NOT_NAMES = {
    "I", "AI", "CEO", "CTO", "HR", "US", "USA", "EU", "UK", "NYC", "API", "APIs", "SQL",
    "The", "This", "You", "Your", "We", "Our", "And", "Or", "For", "With", "In", "On",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Manager", "Director", "Lead", "Team", "Senior", "Junior", "Associate", "Coordinator",
    "Equal", "Opportunity", "Employer",
}
MIN_NAME_MENTIONS = 2

# Details a rewrite must not add: they're facts about the job, so they can only
# come from the employer.
ADDED_DETAILS = [
    ("pay period", r"\bper (hour|week|month|year|annum)\b|/\s?(hr|hour|mo|month|yr|year)\b"),
    ("employment type", r"\btemporary\b|\bpart[- ]time\b|\bfull[- ]time\b|\bseasonal\b|"
                        r"\binternship\b|\bcontract (role|position|basis)\b"),
    ("schedule", r"\bevenings?\b|(?<!late-)(?<!late )\bnights?\b|\bovernight\b|\bweekends?\b|"
                 r"\bholidays?\b|\bon[- ]call\b"),
    ("work arrangement", r"\bremote\b|\bhybrid\b|\bwork from home\b"),
    ("benefits", r"\b401\s?\(?k\)?|\bdental\b|\bvision (insurance|coverage|plan)\b|\bmedical\b|"
                 r"\bhealth (insurance|benefits|coverage|plan)\b|\bpto\b|\bpaid time off\b|"
                 r"\bpaid (vacation|leave|holidays)\b|\bparental leave\b|\bstock options?\b|\bequity\b|"
                 r"\b(performance |annual |signing |sign-on )?bonus(es)?\b(?! points)|\bteam events?\b|"
                 r"\bgym\b|\bwellness\b|\bemployee benefits\b|\brelocation (assistance|package|support)\b"),
]

REQUIREMENTS_KEPT = 0.7       # warn if fewer than 70% of listed qualifications survive
READABILITY_JUMP = 1.5        # grade levels
READABILITY_CEILING = 10.0    # only warn if the rewrite ends up at or above this grade

LENGTH_TOLERANCE = 0.25
MIN_WORDS_FOR_LENGTH_CHECK = 100


@dataclass
class Warning:
    category: str
    fact: str
    detail: str
    logged: bool = False


@dataclass
class FactCheck:
    warnings: list[Warning] = field(default_factory=list)
    length_change: float = 0.0  # e.g. -0.58 for 58% shorter

    @property
    def ok(self) -> bool:
        return not self.warnings


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("–", "-")).lower()


def _logged(term_regex: str, changes: list[dict]) -> bool:
    return any(re.search(term_regex, _norm(c.get("original", "")), re.IGNORECASE) for c in changes)


def _number_core(s: str) -> str:
    """'2+ years' -> '2', '$70,000–$85,000' -> '70000 85000': compare the digits only."""
    return " ".join(n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?", s.replace(",", "")))


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'+#.-]{3,}", text.lower())
            if w not in {"with", "that", "this", "your", "have", "from", "will", "and/or"}}


def _lines_with_sections(text: str) -> list[tuple[str, str | None]]:
    """(line, section) pairs, where section is 'required', 'optional' or None."""
    out, section = [], None
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*•·●▪◦ ").strip()
        if not line:
            continue
        if _looks_like_heading(raw.strip()) or _is_sub_intro(raw.strip()):
            section = next_section(raw.strip(), section)
            continue
        out.append((line, section))
    return out


def _preferred_made_required(original: str, rewrite: str) -> list[str]:
    """Qualifications the original marked as optional that the rewrite lists as required."""
    rewrite_lines = _lines_with_sections(rewrite)
    hits = []
    for line, section in _lines_with_sections(original):
        if not (PREFERRED.search(line) or section == "optional"):
            continue
        words = _content_words(PREFERRED.sub(" ", line))
        if len(words) < 3:
            continue
        best, best_section, best_overlap = None, None, 0.0
        for r_line, r_section in rewrite_lines:
            overlap = len(words & _content_words(r_line)) / len(words)
            if overlap > best_overlap:
                best, best_section, best_overlap = r_line, r_section, overlap
        if best and best_overlap >= 0.6 and best_section == "required" and not PREFERRED.search(best):
            hits.append(line)
    return hits


def _names(text: str) -> dict[str, int]:
    """Capitalized words used mid-sentence (likely employer, client or product names)."""
    found = re.findall(r"(?<=[a-z,] )([A-Z][A-Za-z0-9&.'-]+)", text)
    # Words in headings or at the start of a line are capitalized for layout, not
    # because they're names; words also used in lowercase are ordinary words.
    layout_words = set()
    for raw in text.splitlines():
        line = raw.strip().lstrip("#-*•·●▪◦ ").strip()
        if not line:
            continue
        words = re.findall(r"[A-Za-z0-9&.'-]+", line)
        layout_words.add(words[0] if words else "")
        if _looks_like_heading(raw.strip()):
            layout_words.update(words)
    lower_words = set(re.findall(r"\b[a-z][a-z'-]+\b", text))
    counts: dict[str, int] = {}
    for name in {n.rstrip(".'") for n in found}:
        if (name in NOT_NAMES or len(name) < 3 or name in layout_words
                or name.lower() in lower_words):
            continue
        counts[name] = len(re.findall(r"\b" + re.escape(name), text))
    return counts


def _short(line: str, limit: int = 90) -> str:
    return line if len(line) <= limit else line[: limit - 3] + "…"


def _title(text: str) -> str:
    for raw in text.splitlines():
        if raw.strip().startswith("#"):
            return raw.strip().lstrip("#").strip()
    return ""


def check(original: str, rewrite: str, changes: list[dict] | None = None) -> FactCheck:
    changes = changes or []
    o, r = _norm(original), _norm(rewrite)
    result = FactCheck()

    for category, concepts in MUST_KEEP.items():
        for label, rx in concepts:
            m = re.search(rx, o, re.IGNORECASE)
            if m and not re.search(rx, r, re.IGNORECASE):
                result.warnings.append(Warning(
                    category, label,
                    f'The original mentions "{m.group(0)}", but the rewrite doesn\'t.',
                    logged=_logged(rx, changes)))

    rewrite_numbers = {_number_core(m.group(0)) for m in NUMBER_FACT.finditer(r)}
    rewrite_tokens = {n for core in rewrite_numbers for n in core.split()}
    seen = set()
    for m in NUMBER_FACT.finditer(o):
        core = _number_core(m.group(0))
        if (not core or core in seen or core in rewrite_numbers
                or set(core.split()) <= rewrite_tokens):  # e.g. "0.25% – 0.5%" kept as "0.25-0.5%"
            continue
        seen.add(core)
        if _logged(re.escape(_norm(m.group(0))), changes):
            continue  # a logged change (e.g. an inflated requirement) is allowed
        result.warnings.append(Warning(
            "numbers", m.group(0).strip(),
            f'"{m.group(0).strip()}" appears in the original but not in the rewrite.'))

    for m in REPORTS_TO.finditer(original):
        title = m.group(1).strip()
        key = title.split()[-1].lower() if title else ""
        if key and key not in r:
            result.warnings.append(Warning(
                "reporting line", title,
                f'The original says the role reports to "{title}", but the rewrite doesn\'t.'))

    unexpected = sorted({m.group(0) for m in FOREIGN_SCRIPTS.finditer(rewrite)}
                        - {m.group(0) for m in FOREIGN_SCRIPTS.finditer(original)})
    for chars in unexpected:
        i = rewrite.find(chars)
        context = rewrite[max(i - 25, 0): i + len(chars) + 25].replace("\n", " ").strip()
        result.warnings.append(Warning(
            "stray characters", chars,
            f'The rewrite contains characters that aren\'t in the original: "…{context}…". '
            "This is a model glitch; delete them before posting."))

    # --- v3 checks: quieter ways a rewrite can change the job ---

    promoted = _preferred_made_required(original, rewrite)
    if len(promoted) >= 3:
        result.warnings.append(Warning(
            "requirement level", f"{len(promoted)} items",
            f"{len(promoted)} items the original lists as optional or preferred (e.g. "
            f'"{_short(promoted[0])}") are listed as required in the rewrite.'))
    else:
        for line in promoted:
            result.warnings.append(Warning(
                "requirement level", _short(line),
                f'The original lists "{_short(line)}" as preferred, but the rewrite makes it required.'))

    before_items = count_required(original) + count_optional(original)
    after_items = count_required(rewrite) + count_optional(rewrite)
    if before_items >= 5 and after_items < before_items * REQUIREMENTS_KEPT:
        result.warnings.append(Warning(
            "requirements", f"{before_items} → {after_items}",
            f"The original lists {before_items} qualifications; the rewrite lists {after_items}. "
            "Requirements should be moved or reworded, not deleted."))

    title = _title(rewrite)
    # Compare the core title, so "Associate — Palm Harbor, FL (Store #1169)" matches "Associate, Palm Harbor".
    core_title = re.split(r"\s+[—–|-]\s+|,|\(|\|", title)[0].strip() if title else ""
    if core_title and _norm(core_title) not in o:
        result.warnings.append(Warning(
            "job title", title,
            f'The rewrite uses the title "{title}", which doesn\'t appear in the original.',
            logged=any(title.lower() in c.get("replacement", "").lower() for c in changes)))

    already = " ".join(w.fact for w in result.warnings if w.category == "reporting line")
    for name, mentions in sorted(_names(original).items()):
        if mentions >= MIN_NAME_MENTIONS and name not in rewrite and name not in already:
            result.warnings.append(Warning(
                "names", name,
                f'"{name}" appears {mentions} times in the original but not in the rewrite.',
                logged=_logged(re.escape(name.lower()), changes)))

    if "reasonable accommodation" not in o:
        for raw in rewrite.splitlines():
            if "reasonable accommodation" in raw.lower() and NON_PHYSICAL.search(raw):
                short = raw.strip().lstrip("-* ").strip()
                short = short if len(short) <= 90 else short[:87] + "…"
                result.warnings.append(Warning(
                    "accommodation wording", short,
                    "Accommodation wording was added to a license, location or travel "
                    f'requirement, where it doesn\'t apply: "{short}".'))

    grade_before, grade_after = reading_grade(original), reading_grade(rewrite)
    if grade_after - grade_before > READABILITY_JUMP and grade_after >= READABILITY_CEILING:
        result.warnings.append(Warning(
            "readability", f"grade {grade_before} → {grade_after}",
            f"The rewrite is harder to read than the original (reading grade {grade_before} → "
            f"{grade_after}). Shorter sentences and plainer words would help."))

    for label, rx in ADDED_DETAILS:
        def terms(text):
            return {re.sub(r"[\s-]+", " ", m.group(0)) for m in re.finditer(rx, text)}
        found = sorted(terms(r) - terms(o))
        if found:
            result.warnings.append(Warning(
                "added details", ", ".join(found),
                f'The rewrite mentions {", ".join(repr(f) for f in found)} ({label}), which the '
                "original doesn't. Make sure it's accurate, or remove it."))

    o_words, r_words = len(o.split()), len(r.split())
    if o_words:
        result.length_change = r_words / o_words - 1
        if o_words >= MIN_WORDS_FOR_LENGTH_CHECK and abs(result.length_change) > LENGTH_TOLERANCE:
            result.warnings.append(Warning(
                "length", f"{result.length_change:+.0%}",
                f"The rewrite is {abs(result.length_change):.0%} "
                f"{'shorter' if result.length_change < 0 else 'longer'} than the original "
                f"({o_words} → {r_words} words). Check that nothing important was cut."))
    return result
