"""Readability scoring for the patient-facing summary.

The patient summary is a headline feature, so its reading level is a testable
property, not a hope. Flesch-Kincaid grade level = school grade needed to read the
text. Bulleted lines are treated as sentence units so the metric is fair on the
summary's list format. Unavoidable medical nouns (pneumothorax, effusion) inflate
the score, so the gate is set to a realistic patient-material band, not 6th grade,
and the ACTUAL grade is always reported."""
import re

_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    count = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and count > 1:
        count -= 1  # silent trailing 'e'
    return max(1, count)


def flesch_kincaid_grade(text: str) -> float:
    # Sentence units: end punctuation OR line breaks (bullets have no periods).
    units = [u for u in re.split(r"[.!?\n]+", text) if u.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not units or not words:
        return 0.0
    syllables = sum(_syllables(w) for w in words)
    n_words, n_units = len(words), len(units)
    grade = 0.39 * (n_words / n_units) + 11.8 * (syllables / n_words) - 15.59
    return round(grade, 1)
