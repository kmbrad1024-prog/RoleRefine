"""Deterministic scoring for job descriptions.

These metrics are computed in code (not by the LLM) so before/after numbers
are consistent and reproducible.

Gender-coded word stems are based on Gaucher, Friesen & Kay (2011),
"Evidence That Gendered Wording in Job Advertisements Exists and Sustains
Gender Inequality", Journal of Personality and Social Psychology, and the
open-source adaptation by Kat Matfield (Gender Decoder).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MASCULINE_STEMS = [
    "active", "adventurous", "aggress", "ambitio", "analy", "assert", "athlet",
    "autonom", "battle", "boast", "challeng", "champion", "compet", "confident",
    "courag", "decid", "decision", "decisive", "defend", "determin", "domina",
    "driven", "fearless", "fight", "force", "greedy", "headstrong",
    "hierarch", "hostil", "impulsive", "independen", "individual", "intellect",
    "lead", "logic", "objective", "opinion", "outspoken", "persist",
    "principle", "reckless", "self-confiden", "self-relian", "self-sufficien",
    "stubborn", "superior", "unreasonab",
]

FEMININE_STEMS = [
    "agree", "affectionate", "child", "cheer", "collab", "commit", "communal",
    "compassion", "connect", "considerate", "cooperat", "co-operat", "depend",
    "emotiona", "empath", "feel", "flatterable", "gentle", "honest",
    "interpersonal", "interdependen", "inter-personal", "inter-dependen",
    "kind", "kinship", "loyal", "modesty", "nag", "nurtur", "pleasant",
    "polite", "quiet", "respon", "sensitiv", "submissive", "support", "sympath",
    "tender", "together", "trust", "understand", "warm", "whin", "enthusias",
    "inclusive", "yield", "share", "sharing",
]

# Phrases outside the Gaucher lists that commonly signal exclusion.
# Each maps to a category used in the UI.
OTHER_FLAGS = {
    r"\brock ?stars?\b": "jargon",
    r"\bninjas?\b": "jargon",
    r"\bgurus?\b": "jargon",
    r"\bcrush(ing)?\b": "jargon",
    r"\bkiller\b": "jargon",
    r"\bwork hard,? play hard\b": "exclusionary_language",
    r"\bhit the ground running\b": "exclusionary_language",
    r"\bculture fit\b": "exclusionary_language",
    r"\bguys\b": "exclusionary_language",
    r"\bmanpower\b": "exclusionary_language",
    r"\bhe/she\b|\bhis/her\b|\bs/he\b": "exclusionary_language",
    r"\bdigital natives?\b": "age",
    r"\byoung\b": "age",
    r"\brecent (college )?grad(uate)?s?\b": "age",
    r"\bfresh\b": "age",
    r"\bable to lift\b|\bstand for long periods\b|\bmust (be able to )?drive\b": "ability",
}

REQUIREMENT_HEADINGS = re.compile(
    r"(requirement|qualification|what you('ll| will) need|must[- ]have|"
    r"what we('re| are) looking for|you have|who you are|skills|"
    r"you('ll| will)? bring|what we expect|your background|"
    r"your experience|you should have|you're a great fit|great fit if)",
    re.IGNORECASE,
)
NICE_TO_HAVE_HEADINGS = re.compile(
    r"(nice[- ]to[- ]have|preferred|bonus|plus)", re.IGNORECASE
)
BULLET = re.compile(r"^\s*([-*•●▪◦]|\d+[.)])\s+")

WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# Business terms that match a coded stem but don't carry the coded meaning
# (e.g. sales "leads", an email "response", a "connect rate"). They're removed
# before coded words are counted. Real coded uses ("leader", "responsive",
# "connect with customers") still count.
FALSE_POSITIVES = re.compile(
    r"\b(lead(s)? (research|quality|list|lists|generation|gen|prioriti[sz]ation|scoring|source|sources|flow)"
    r"|leads\b"
    r"|(team|tech|technical|delivery|project|product|design|engineering|sales|account|content|data|qa|test) lead\b"
    r"|connect(ion)? rates?"
    r"|responsibilit(y|ies)"
    r"|respon(se|ses|ding|d|ds) (time|times|rate|rates|within)"
    r"|responses?\b"
    r"|analytics"
    r"|customer support|support (team|ticket|tickets|engineer|specialist|agent)"
    r"|(hiring |final )?decisions are (ultimately )?made by humans"
    r"|(generally accepted )?accounting principles"
    r"|(ai|data)-driven)",
    re.IGNORECASE,
)

@dataclass
class Score:
    masculine: list[str] = field(default_factory=list)
    feminine: list[str] = field(default_factory=list)
    other_flags: list[tuple[str, str]] = field(default_factory=list)
    required_count: int = 0
    reading_grade: float = 0.0
    word_count: int = 0

    @property
    def masculine_count(self) -> int:
        return len(self.masculine)

    @property
    def feminine_count(self) -> int:
        return len(self.feminine)

    @property
    def other_count(self) -> int:
        return len(self.other_flags)

    @property
    def balance_label(self) -> str:
        """Balance label that accounts for posting length.

        Two views must agree: the raw gap between masculine and feminine counts,
        and the gap per 100 words. A long posting with a small raw gap, or a
        short one with a 1-2 word gap, reads as balanced or only slightly coded.
        """
        diff = self.masculine_count - self.feminine_count
        per_100 = abs(diff) / max(self.word_count, 1) * 100
        level_raw = 2 if abs(diff) >= 4 else 1 if abs(diff) >= 2 else 0
        level_density = 2 if per_100 >= 1.0 else 1 if per_100 >= 0.5 else 0
        level = min(level_raw, level_density)
        if level == 0:
            return "Balanced"
        strength = "Strongly" if level == 2 else "Slightly"
        side = "masculine" if diff > 0 else "feminine"
        return f"{strength} {side}-coded"


def _coded_words(words: list[str], stems: list[str]) -> list[str]:
    """Words starting with a coded stem. Hyphenated words also check each part,
    so "results-driven" counts as "driven"."""
    hits = []
    for w in words:
        lw = w.lower()
        candidates = [lw] + (lw.split("-") if "-" in lw else [])
        if any(c.startswith(stem) for c in candidates for stem in stems):
            hits.append(lw)
    return hits


def _looks_like_heading(line: str) -> bool:
    """Short title-style lines ("What You Have", "Requirements:") are headings.

    Copying a posting from a web page usually drops bullet symbols, so list
    items and headings have to be told apart by their shape instead.
    """
    if BULLET.match(line) or len(line) >= 60:
        return False
    if line.startswith("#") or line.endswith(":") or line.isupper():
        return True
    if line[-1] in ".;,!?":
        return False
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", line) if len(w) > 3]
    return bool(words) and len(line.split()) <= 8 and \
        sum(w[0].isupper() for w in words) / len(words) >= 0.6


def count_required(text: str) -> int:
    """Count the items listed under a 'requirements'-style heading.

    Each line in the section counts as one item, whether or not it kept its
    bullet symbol. Stops at the next heading or a 'nice to have' section.
    Returns 0 if the JD has no recognizable requirements section.
    """
    count = 0
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _looks_like_heading(line):
            if NICE_TO_HAVE_HEADINGS.search(line):
                in_section = False
            else:
                in_section = REQUIREMENT_HEADINGS.search(line) is not None
            continue
        if in_section:
            count += 1
    return count


def _syllables(word: str) -> int:
    """Approximate English syllable count (vowel-group heuristic)."""
    w = word.lower().strip("'")
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade level.

    Bullet points and headings are treated as sentences, since job
    descriptions rarely end list items with a period.
    """
    units = [u for u in re.split(r"[.!?]+|\n+", text) if WORD.search(u)]
    words = WORD.findall(text)
    if not words or not units:
        return 0.0
    syllables = sum(_syllables(w) for w in words)
    grade = 0.39 * len(words) / len(units) + 11.8 * syllables / len(words) - 15.59
    return round(max(grade, 0.0), 1)


def score(text: str) -> Score:
    words = WORD.findall(text)
    coded_words = WORD.findall(FALSE_POSITIVES.sub(" ", text))
    s = Score()
    s.word_count = len(words)
    s.masculine = _coded_words(coded_words, MASCULINE_STEMS)
    s.feminine = _coded_words(coded_words, FEMININE_STEMS)
    for pattern, category in OTHER_FLAGS.items():
        for m in re.finditer(pattern, text, re.IGNORECASE):
            s.other_flags.append((m.group(0), category))
    s.required_count = count_required(text)
    s.reading_grade = reading_grade(text)
    return s
