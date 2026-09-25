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
    r"what we('re| are) looking for|you have|who you are|skills)",
    re.IGNORECASE,
)
NICE_TO_HAVE_HEADINGS = re.compile(
    r"(nice[- ]to[- ]have|preferred|bonus|plus)", re.IGNORECASE
)
BULLET = re.compile(r"^\s*([-*•●▪◦]|\d+[.)])\s+")

WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


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
        diff = self.masculine_count - self.feminine_count
        if diff >= 4:
            return "Strongly masculine-coded"
        if diff >= 2:
            return "Slightly masculine-coded"
        if diff <= -4:
            return "Strongly feminine-coded"
        if diff <= -2:
            return "Slightly feminine-coded"
        return "Balanced"


def _coded_words(words: list[str], stems: list[str]) -> list[str]:
    hits = []
    for w in words:
        lw = w.lower()
        if any(lw.startswith(stem) for stem in stems):
            hits.append(lw)
    return hits


def count_required(text: str) -> int:
    """Count bullet points under a 'requirements'-style heading.

    Stops at the next heading or a 'nice to have' section. Falls back to 0
    if the JD has no recognizable requirements section.
    """
    count = 0
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_bullet = bool(BULLET.match(line))
        looks_like_heading = (
            not is_bullet
            and len(line) < 60
            and (line.startswith("#") or line.endswith(":") or line.isupper()
                 or REQUIREMENT_HEADINGS.search(line) is not None)
        )
        if looks_like_heading:
            if NICE_TO_HAVE_HEADINGS.search(line):
                in_section = False
            else:
                in_section = REQUIREMENT_HEADINGS.search(line) is not None
            continue
        if in_section and is_bullet:
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
    s = Score()
    s.word_count = len(words)
    s.masculine = _coded_words(words, MASCULINE_STEMS)
    s.feminine = _coded_words(words, FEMININE_STEMS)
    for pattern, category in OTHER_FLAGS.items():
        for m in re.finditer(pattern, text, re.IGNORECASE):
            s.other_flags.append((m.group(0), category))
    s.required_count = count_required(text)
    s.reading_grade = reading_grade(text)
    return s
