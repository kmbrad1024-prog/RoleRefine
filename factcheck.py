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
    r"|\d+\s?%"                                                       # 30%
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
    return " ".join(re.findall(r"\d+", s.replace(",", "")))


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
    seen = set()
    for m in NUMBER_FACT.finditer(o):
        core = _number_core(m.group(0))
        if not core or core in seen or core in rewrite_numbers:
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
