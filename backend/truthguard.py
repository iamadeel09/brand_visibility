"""TruthGuard: compare AI claims about the brand with user-supplied verified facts.

Deliberately conservative - it only flags what the response text actually says:
  * "contradiction": the answer states a number (year, %, money, count) about the same
    topic as a verified fact, and that number differs from every number in the fact.
  * "uncertain": a hedged numeric conflict, or an affirmative/negated mismatch on the
    same topic. These need human review and are NOT presented as confirmed falsehoods.
Missing information is never flagged. Facts without a checkable number or polarity are
never used to invent a problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .analyzer import normalize_text, split_sentences, detect_in_sentence

STOPWORDS = set(
    "a an the and or of in on at to for with by from as is are was were be been being it its this that "
    "these those has have had do does did not no we our their they he she you your can will would "
    "also than then into over per about more most very which who whom whose".split()
)
_HEDGE = re.compile(
    r"\b(approximately|approx|around|roughly|about|reportedly|allegedly|may|might|possibly|"
    r"perhaps|i think|i believe|estimated|some say|unclear|not sure|as of (?:my|last))\b",
    re.I,
)
_NEGATION = re.compile(
    r"\b(not|no|never|without|doesn'?t|does not|don'?t|do not|isn'?t|is not|aren'?t|are not|"
    r"lacks?|cannot|can'?t|unable)\b",
    re.I,
)
_NUM = re.compile(
    r"(?P<cur>[$€£])?\s?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?"
    r"(?P<mult>k|m|bn|million|billion|thousand)?\b\s?(?P<pct>%|percent|per cent)?\s*(?P<next>[a-z]+)?",
    re.I,
)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


@dataclass
class Finding:
    kind: str  # "contradiction" | "uncertain"
    provider: str
    query: str
    fact: str
    claim: str
    reason: str


def _content_words(text: str) -> set[str]:
    words = set()
    for w in normalize_text(text).split():
        if w in STOPWORDS or w.isdigit() or len(w) < 3:
            continue
        words.add(w[:6])  # crude stemming: 'employees' ~ 'employ'
    return words


def extract_numbers(text: str) -> list[tuple[str, float]]:
    """Return (kind, value) pairs. kind is year / percent / currency / noun-stem / plain."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        mult = (m.group("mult") or "").lower()
        if mult in _MULT:
            val *= _MULT[mult]
        nxt = (m.group("next") or "").lower()
        if m.group("pct"):
            kind = "percent"
        elif m.group("cur"):
            kind = "currency"
        elif not mult and re.fullmatch(r"(1[89]|20)\d\d", raw):
            kind = "year"
        elif nxt and nxt not in STOPWORDS:
            kind = nxt[:5]
        else:
            kind = "plain"
        out.append((kind, val))
    return out


def _numeric_conflict(fact: str, sentence: str) -> bool:
    fact_nums = extract_numbers(fact)
    sent_nums = extract_numbers(sentence)
    if not fact_nums or not sent_nums:
        return False
    for kind in {k for k, _ in fact_nums if k != "plain"}:
        f_vals = [v for k, v in fact_nums if k == kind]
        s_vals = [v for k, v in sent_nums if k == kind]
        if s_vals and not any(abs(s - f) < 1e-9 for s in s_vals for f in f_vals):
            return True
    return False


def _topic_overlap(fact: str, sentence: str, brand: str) -> int:
    brand_words = _content_words(brand)
    return len((_content_words(fact) - brand_words) & (_content_words(sentence) - brand_words))


def check_answer(brand: str, answer: str, facts: list[str], provider: str = "", query: str = "") -> list[Finding]:
    """Check one answer against verified facts. Only sentences that mention the brand count."""
    findings: list[Finding] = []
    facts = [f.strip() for f in (facts or []) if isinstance(f, str) and f.strip()]
    if not facts or not answer:
        return findings
    seen = set()
    for sentence in split_sentences(answer):
        if brand not in detect_in_sentence(sentence, [brand]):
            continue
        for fact in facts:
            overlap = _topic_overlap(fact, sentence, brand)
            key = (sentence, fact)
            if overlap < 1 or key in seen:
                continue
            hedged = bool(_HEDGE.search(sentence))
            if _numeric_conflict(fact, sentence):
                if not hedged:  # overlap >= 1 shared topic word is already required above
                    kind, why = "contradiction", "States a figure that differs from the verified fact."
                else:
                    kind, why = "uncertain", "Figure differs from the verified fact but the claim is hedged, so it is uncertain."
            elif overlap >= 2 and bool(_NEGATION.search(sentence)) != bool(_NEGATION.search(fact)):
                kind, why = "uncertain", "Statement polarity (affirmed vs. denied) differs from the verified fact; needs human review."
            else:
                continue
            seen.add(key)
            findings.append(Finding(kind, provider, query, fact, sentence, why))
    return findings


def check_responses(brand: str, per_response: list[dict], facts: list[str]) -> list[Finding]:
    out: list[Finding] = []
    for p in per_response:
        out.extend(check_answer(brand, p["answer"], facts, p["provider"], p["query"]))
    return out
