"""Brand detection, visibility scoring and competitor-gap detection.

Pure functions, no network. Every number is derived from the response text.

Quality scale per (brand, response):
    0 absent
    1 mentioned in passing
    2 credible option
    3 strongly recommended
"""

from __future__ import annotations

import re
import unicodedata

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "gmbh", "ag", "sa", "sas",
    "srl", "bv", "nv", "plc", "corp", "corporation", "co", "company", "se", "oy", "ab", "spa",
}

_STRONG = re.compile(
    r"\b(best|top[- ]?(pick|choice|rated|tier)|highly recommend\w*|i recommend|we recommend|"
    r"recommended|leading|market leader|number one|go-to|ideal|excellent|outstanding|"
    r"my pick|first choice|standout|best-in-class|#1)\b|#1",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(not recommended|would not recommend|wouldn'?t recommend|don'?t recommend|"
    r"do not recommend|avoid|worst|unreliable|not a good|poor choice)\b",
    re.I,
)
_CREDIBLE = re.compile(
    r"\b(popular|good|great|solid|strong|reliable|well[- ]known|widely used|offers?|provides?|"
    r"known for|option|alternative|features?|suitable|robust|capable|trusted|"
    r"worth considering|consider|used by|supports?)\b",
    re.I,
)
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_TOP_RANK = re.compile(r"^\s*(?:1[.)]|#1\b)")


# ----------------------------- normalization -----------------------------
def normalize_text(text: str) -> str:
    """Lowercase, strip accents, map symbols, collapse non-alphanumerics to single spaces."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ").replace("+", " plus ").replace("#", " sharp ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def normalize_name(name: str) -> str:
    """Normalized canonical form of a brand name ('  Hub-Spot, Inc.' -> 'hub spot inc')."""
    return normalize_text(name)


def brand_variants(name: str) -> list[str]:
    """Normalized variants used for matching: full form, no-space form, legal-suffix-stripped."""
    base = normalize_name(name)
    if not base:
        return []
    variants = [base]
    tokens = base.split()
    stripped = list(tokens)
    while len(stripped) > 1 and stripped[-1] in LEGAL_SUFFIXES:
        stripped.pop()
    if stripped != tokens:
        variants.append(" ".join(stripped))
    for v in list(variants):
        joined = v.replace(" ", "")
        if joined != v and len(joined) >= 4:
            variants.append(joined)
    out: list[str] = []
    for v in variants:
        if v and v not in out:
            out.append(v)
    return out


# ------------------------------- detection -------------------------------
def split_sentences(text: str) -> list[str]:
    """Split into sentence/clause/list-item chunks that are exact substrings of the text."""
    parts = re.split(r"(?<=[.!?])\s+|\n+|;\s+|,\s+but\s+", text or "")
    return [p for p in (s.strip() for s in parts) if p]


def _spans(norm_text: str, variants: list[str]) -> list[tuple[int, int]]:
    padded = f" {norm_text} "
    found = []
    for v in variants:
        for m in re.finditer(rf"(?<= ){re.escape(v)}(?= )", padded):
            found.append((m.start(), m.end()))
    return found


def _tracked_names(names: list[str]) -> list[tuple[str, list[str]]]:
    return [(n, brand_variants(n)) for n in names if brand_variants(n)]


def detect_in_sentence(sentence: str, names: list[str]) -> set[str]:
    """Names mentioned in one sentence, with word-boundary matching.

    A match nested inside a longer tracked name's match is ignored, so brand 'Acme' is
    not credited when the text says 'Acme Pro' and 'Acme Pro' is a tracked competitor.
    """
    norm = normalize_text(sentence)
    all_spans = []  # (start, end, name)
    for name, variants in _tracked_names(names):
        for s, e in _spans(norm, variants):
            all_spans.append((s, e, name))
    hits = set()
    for s, e, name in all_spans:
        nested = any(
            o_name != name and o_s <= s and e <= o_e and (o_e - o_s) > (e - s)
            for o_s, o_e, o_name in all_spans
        )
        if not nested:
            hits.add(name)
    return hits


def find_mentions(text: str, name: str, all_names: list[str] | None = None) -> list[str]:
    """Exact response sentences mentioning `name` (evidence, unmodified)."""
    names = list(all_names or [])
    if name not in names:
        names.append(name)
    return [s for s in split_sentences(text) if name in detect_in_sentence(s, names)]


def mentions_brand(text: str, name: str) -> bool:
    return bool(find_mentions(text, name))


def score_mentions(evidence: list[str]) -> int:
    """Quality 0-3 from the sentences that mention a brand."""
    if not evidence:
        return 0
    if any(_NEGATIVE.search(s) for s in evidence):
        return 1
    if any(_STRONG.search(s) or _TOP_RANK.match(s) for s in evidence):
        return 3
    if len(evidence) >= 2 or any(_CREDIBLE.search(s) or _LIST_ITEM.match(s) for s in evidence):
        return 2
    return 1


# ------------------------------- aggregation -------------------------------
def visibility_score(scores: list[int]) -> float:
    """100 * sum(quality) / (3 * successful responses); 0.0 if no responses."""
    n = len(scores)
    if n == 0:
        return 0.0
    return round(100.0 * sum(scores) / (3 * n), 2)


def mention_rate(scores: list[int]) -> float:
    """100 * responses mentioning the brand / successful responses; 0.0 if none."""
    n = len(scores)
    if n == 0:
        return 0.0
    return round(100.0 * sum(1 for s in scores if s > 0) / n, 2)


def clean_names(brand: str, competitors: list[str]) -> list[str]:
    """Deduplicated, non-blank competitor names excluding the target brand itself."""
    seen = {normalize_name(brand)}
    out = []
    for c in competitors or []:
        key = normalize_name(c)
        if key and key not in seen:
            seen.add(key)
            out.append(str(c).strip())
    return out


def analyze_responses(brand: str, competitors: list[str], results: list) -> dict:
    """Analyze scan results (objects with provider/query/answer/ok/error).

    Failed or empty results are excluded from every denominator.
    """
    competitors = clean_names(brand, competitors)
    names = [brand] + competitors
    per_response = []
    failures = []
    for r in results:
        if not getattr(r, "ok", False) or not (getattr(r, "answer", "") or "").strip():
            failures.append(r)
            continue
        evidence = {n: find_mentions(r.answer, n, names) for n in names}
        scores = {n: score_mentions(evidence[n]) for n in names}
        per_response.append(
            {
                "provider": r.provider,
                "query": r.query,
                "answer": r.answer,
                "scores": scores,
                "evidence": evidence,
                "mentions": [n for n in names if scores[n] > 0],
            }
        )

    def stats(name: str) -> dict:
        sc = [p["scores"][name] for p in per_response]
        return {
            "name": name,
            "scores": sc,
            "visibility_score": visibility_score(sc),
            "mention_rate": mention_rate(sc),
        }

    return {
        "successful": len(per_response),
        "failures": failures,
        "per_response": per_response,
        "brand": stats(brand),
        "competitors": [stats(c) for c in competitors],
    }


# ------------------------------- competitor gaps -------------------------------
def find_visibility_gaps(brand: str, competitors: list[str], per_response: list[dict]) -> list[dict]:
    """Queries where competitors appear but the brand does not, grounded in evidence."""
    competitors = clean_names(brand, competitors)
    by_query: dict[str, list[dict]] = {}
    for p in per_response:
        by_query.setdefault(p["query"], []).append(p)

    gaps = []
    for query, items in by_query.items():
        gap_items = [
            p for p in items
            if p["scores"].get(brand, 0) == 0 and any(p["scores"].get(c, 0) > 0 for c in competitors)
        ]
        if not gap_items:
            continue
        brand_absent_everywhere = all(p["scores"].get(brand, 0) == 0 for p in items)
        comp_names: list[str] = []
        evidence = []
        max_score = 0
        for p in gap_items:
            for c in competitors:
                sc = p["scores"].get(c, 0)
                if sc > 0:
                    if c not in comp_names:
                        comp_names.append(c)
                    max_score = max(max_score, sc)
                    if p["evidence"][c]:
                        evidence.append(
                            {"provider": p["provider"], "competitor": c, "score": sc, "sentence": p["evidence"][c][0]}
                        )
        evidence.sort(key=lambda e: -e["score"])
        if brand_absent_everywhere and max_score >= 2:
            severity = "high"
        elif brand_absent_everywhere or max_score >= 2:
            severity = "medium"
        else:
            severity = "low"
        gaps.append(
            {
                "query": query,
                "competitors": comp_names,
                "max_competitor_score": max_score,
                "gap_responses": len(gap_items),
                "total_responses": len(items),
                "brand_absent_everywhere": brand_absent_everywhere,
                "severity": severity,
                "evidence": evidence,
            }
        )
    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (order[g["severity"]], -g["max_competitor_score"], -len(g["competitors"])))
    return gaps
