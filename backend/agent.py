"""Autonomous GEO agent: Scan -> Analyze -> Compare -> Investigate -> Recommend.

Plain Python, no agent framework. Every step consumes the previous step's real output;
recommendations quote evidence found in the scanned responses.

    from backend.agent import run_analysis
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import analyzer, scanner, truthguard

DEMO_LABEL = "[DEMO DATA]"
DEMO_ANSWER_PREFIX = "[DEMO - synthetic data, not a live API response] "
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ----------------------------------------------------------------------------
# Demo data (deterministic, synthetic, clearly labelled)
# ----------------------------------------------------------------------------
def _alter_number(fact: str) -> str | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", fact)
    if not m:
        return None
    raw = m.group(0).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    new = int(val) + 3 if val == int(val) else round(val + 3, 1)
    return fact[: m.start()] + str(new) + fact[m.end():]


def demo_scan(brand: str, competitors: list[str], queries: list[str], verified_facts: list[str]) -> list[scanner.ScanResult]:
    """Synthetic answers built from templates. No randomness, no network."""
    comps = analyzer.clean_names(brand, competitors)
    c0 = comps[0] if comps else None
    c1 = comps[1] if len(comps) > 1 else c0
    altered = next((a for a in (_alter_number(f) for f in verified_facts or []) if a), None)
    results = []
    for i, q in enumerate(queries):
        variant = i % 3
        if variant == 0 or c0 is None:
            body = f"{brand} is a top choice for this need and is highly recommended by many buyers."
            if c0:
                body += f" {c0} is also a solid option worth considering."
        elif variant == 1:
            body = f"For this, {c0} is the best option and is widely recommended."
            if c1 and c1 != c0:
                body += f" {c1} offers a good alternative with strong features."
        else:
            body = f"Several tools exist, including {c1} and {c0}. {brand} is also mentioned."
        if i == 0 and altered:
            body += f" According to some sources, {brand}: {altered}."
        results.append(scanner.ScanResult("demo", q, answer=DEMO_ANSWER_PREFIX + body, ok=True))
    return results


# ----------------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------------
@dataclass
class Candidate:
    kind: str  # misinformation | uncertain_claim | visibility_gap | low_visibility | scan_error
    severity: str
    description: str
    data: dict


def _quote(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _compare(analysis: dict, brand: str) -> dict:
    """Compare step: rank brand against competitors using the computed scores."""
    comps = sorted(analysis["competitors"], key=lambda c: -c["visibility_score"])
    ahead = [c for c in comps if c["visibility_score"] > analysis["brand"]["visibility_score"]]
    return {"leader": comps[0] if comps else None, "ahead_of_brand": ahead}


def _build_candidates(brand, analysis, gaps, findings, comparison) -> list[Candidate]:
    cands: list[Candidate] = []
    n = analysis["successful"]

    for f in findings:
        if f.kind == "contradiction":
            cands.append(Candidate(
                "misinformation", "high",
                f"{f.provider} answer to \"{f.query}\" says: \"{_quote(f.claim)}\" - this conflicts with verified fact: \"{_quote(f.fact)}\".",
                {"finding": f},
            ))
        else:
            cands.append(Candidate(
                "uncertain_claim", "low",
                f"Uncertain claim in {f.provider} answer to \"{f.query}\": \"{_quote(f.claim)}\" ({f.reason}) Verified fact: \"{_quote(f.fact)}\". Needs human review.",
                {"finding": f},
            ))

    for g in gaps:
        ev = g["evidence"][0] if g["evidence"] else None
        desc = (
            f"{brand} was absent in {g['gap_responses']} of {g['total_responses']} response(s) to \"{g['query']}\" "
            f"while {', '.join(g['competitors'])} appeared."
        )
        if ev:
            desc += f" Evidence ({ev['provider']}): \"{_quote(ev['sentence'])}\""
        cands.append(Candidate("visibility_gap", g["severity"], desc, {"gap": g}))

    if n and analysis["brand"]["mention_rate"] < 25:
        cands.append(Candidate(
            "low_visibility", "high" if analysis["brand"]["mention_rate"] == 0 else "medium",
            f"{brand} was mentioned in only {analysis['brand']['mention_rate']:.0f}% of {n} successful response(s) "
            f"(visibility score {analysis['brand']['visibility_score']:.1f}/100).",
            {},
        ))

    failures = analysis["failures"]
    if failures:
        reasons = sorted({f"{f.provider}: {f.error or 'no usable answer'}" for f in failures})
        cands.append(Candidate(
            "scan_error", "high" if n == 0 else "medium",
            f"{len(failures)} scan request(s) failed and were excluded from scoring. " + "; ".join(reasons)[:400],
            {"failures": failures},
        ))
    return cands


def _rank(c: Candidate) -> tuple:
    type_rank = {"misinformation": 0, "visibility_gap": 1, "low_visibility": 2, "scan_error": 3, "uncertain_claim": 4}
    return (SEVERITY_ORDER[c.severity], type_rank[c.kind])


def _investigate(c: Candidate, brand: str, analysis: dict) -> dict:
    """Investigate step: pull the supporting evidence for the chosen problem."""
    if c.kind in ("misinformation", "uncertain_claim"):
        f = c.data["finding"]
        return {"kind": c.kind, "fact": f.fact, "claim": f.claim, "provider": f.provider, "query": f.query}
    if c.kind == "visibility_gap":
        g = c.data["gap"]
        sources = sorted({e["provider"] for e in g["evidence"]})
        return {"kind": c.kind, "gap": g, "providers": sources}
    return {"kind": c.kind}


def _recommendation(c: Candidate, brand: str, evidence: dict, demo: bool) -> dict:
    tag = f"{DEMO_LABEL} " if demo else ""
    if c.kind == "misinformation":
        f = evidence
        return {
            "title": f"Correct the inaccurate claim about {brand}",
            "reason": f"{tag}{f['provider']} stated \"{_quote(f['claim'])}\" but the verified fact is \"{_quote(f['fact'])}\".",
            "action": "Publish the verified fact on an authoritative, crawlable page (about/press/FAQ) with Organization structured data, "
                      "and correct the same figure on third-party profiles (Wikipedia/Wikidata, directories, review sites) that models may learn from.",
        }
    if c.kind == "uncertain_claim":
        f = evidence
        return {
            "title": f"Review the unverified claim about {brand}",
            "reason": f"{tag}{f['provider']} said \"{_quote(f['claim'])}\", which may differ from the verified fact \"{_quote(f['fact'])}\" but could not be confirmed automatically.",
            "action": "Have someone check this claim by hand; if it is wrong, treat it as a correction case, otherwise add a clearer public statement of the fact.",
        }
    if c.kind == "visibility_gap":
        g = evidence["gap"]
        ev = g["evidence"][0] if g["evidence"] else None
        why = f"{tag}{brand} was absent in {g['gap_responses']} of {g['total_responses']} response(s) to \"{g['query']}\" while {', '.join(g['competitors'])} appeared"
        why += f" (e.g. \"{_quote(ev['sentence'])}\")." if ev else "."
        return {
            "title": f"Close the visibility gap for \"{_quote(g['query'], 80)}\"",
            "reason": why,
            "action": f"Create content that directly answers this buyer question (comparison page, FAQ, use-case guide naming {brand}), "
                      f"and earn mentions on the third-party sources where {g['competitors'][0]} is cited.",
        }
    if c.kind == "low_visibility":
        return {
            "title": f"Raise baseline visibility of {brand}",
            "reason": f"{tag}{c.description}",
            "action": "Build entity clarity: consistent brand name and description across your site, directories and review platforms, plus topical content for your core buyer questions.",
        }
    return {
        "title": "Fix scan configuration and re-run",
        "reason": f"{tag}{c.description}",
        "action": "Check API keys (OPENAI_API_KEY etc.), model names, network access and timeouts, then run the analysis again before trusting any scores.",
    }


def _filler(brand: str, analysis: dict, comparison: dict, queries: list[str], facts: list[str], demo: bool) -> list[dict]:
    tag = f"{DEMO_LABEL} " if demo else ""
    n = analysis["successful"]
    b = analysis["brand"]
    pool = []
    leader = comparison["leader"]
    if n and leader and leader["visibility_score"] > b["visibility_score"]:
        pool.append({
            "title": f"Study why {leader['name']} outranks {brand}",
            "reason": f"{tag}{leader['name']} scored {leader['visibility_score']:.1f} vs {brand} at {b['visibility_score']:.1f} across {n} response(s).",
            "action": f"Read the answers that recommend {leader['name']} and note the attributes and sources cited; mirror those proof points in your own content.",
        })
    elif n:
        pool.append({
            "title": f"Defend {brand}'s current visibility lead",
            "reason": f"{tag}{brand} scored {b['visibility_score']:.1f} with a {b['mention_rate']:.0f}% mention rate across {n} response(s), with no competitor ahead.",
            "action": "Keep the sources that support this fresh and re-scan regularly to catch regressions.",
        })
    if not facts:
        pool.append({
            "title": "Supply verified company facts for TruthGuard",
            "reason": f"{tag}No verified facts were provided, so no claim about {brand} could be checked for accuracy.",
            "action": "Add facts such as founding year, headcount, pricing and key capabilities, then re-run the analysis.",
        })
    if len(queries) < 5:
        pool.append({
            "title": "Broaden buyer-intent query coverage",
            "reason": f"{tag}Only {len(queries)} query/queries were scanned, which limits how reliable the visibility score is.",
            "action": "Add more neutral buyer questions (comparisons, best-for-use-case, pricing, alternatives) and re-scan.",
        })
    pool.append({
        "title": "Re-scan on a schedule and track the trend",
        "reason": f"{tag}Model answers change over time; this result is a snapshot of {n} successful response(s).",
        "action": "Run the same query set weekly and compare visibility score and mention rate to see whether changes are working.",
    })
    pool.append({
        "title": "Add more AI providers to the scan",
        "reason": f"{tag}Different assistants answer differently; coverage here is limited to the providers that succeeded.",
        "action": "Enable additional providers via GEO_PROVIDERS (e.g. anthropic, gemini) with their API keys.",
    })
    return pool


def run_analysis_with_trace(brand, competitors, queries, verified_facts, demo_mode=False) -> tuple[dict, list[str]]:
    """Run the workflow; returns (result, human-readable step trace)."""
    brand = (brand or "").strip()
    if not brand:
        raise ValueError("brand must be a non-empty string")
    competitors = [c for c in (competitors or []) if isinstance(c, str)]
    queries = [q.strip() for q in (queries or []) if isinstance(q, str) and q.strip()]
    facts = [f for f in (verified_facts or []) if isinstance(f, str) and f.strip()]
    trace: list[str] = []

    # 1. SCAN
    if demo_mode:
        results = demo_scan(brand, competitors, queries, facts)
        trace.append(f"Scan: generated {len(results)} synthetic demo response(s) (no API calls).")
    else:
        results = scanner.run_scan(queries) if queries else []
        trace.append(f"Scan: {sum(r.ok for r in results)}/{len(results)} live request(s) succeeded.")

    # 2. ANALYZE
    analysis = analyzer.analyze_responses(brand, competitors, results)
    findings = truthguard.check_responses(brand, analysis["per_response"], facts)
    trace.append(f"Analyze: {analysis['successful']} usable response(s); brand score {analysis['brand']['visibility_score']}.")

    # 3. COMPARE
    gaps = analyzer.find_visibility_gaps(brand, competitors, analysis["per_response"])
    comparison = _compare(analysis, brand)
    trace.append(f"Compare: {len(gaps)} visibility gap(s); {len(comparison['ahead_of_brand'])} competitor(s) ahead.")

    # 4. INVESTIGATE
    cands = sorted(_build_candidates(brand, analysis, gaps, findings, comparison), key=_rank)
    if not queries:
        cands.append(Candidate("scan_error", "high", "No queries were provided, so nothing was scanned.", {"failures": []}))
        cands.sort(key=_rank)
    top = cands[0] if cands else None
    trace.append(f"Investigate: top problem = {top.kind + ' (' + top.severity + ')' if top else 'none found'}.")

    # 5. RECOMMEND (3, prioritized; each from a distinct finding where possible)
    recs: list[dict] = []
    seen_titles = set()
    for c in cands:
        rec = _recommendation(c, brand, _investigate(c, brand, analysis), demo_mode)
        if rec["title"] not in seen_titles:
            seen_titles.add(rec["title"])
            recs.append(rec)
        if len(recs) == 3:
            break
    for rec in _filler(brand, analysis, comparison, queries, facts, demo_mode):
        if len(recs) == 3:
            break
        if rec["title"] not in seen_titles:
            seen_titles.add(rec["title"])
            recs.append(rec)
    trace.append(f"Recommend: {len(recs)} recommendation(s).")

    tag = f"{DEMO_LABEL} " if demo_mode else ""
    result = {
        "brand": brand,
        "visibility_score": analysis["brand"]["visibility_score"],
        "mention_rate": analysis["brand"]["mention_rate"],
        "competitors": [{"name": c["name"], "score": c["visibility_score"]} for c in analysis["competitors"]],
        "responses": [
            {"provider": p["provider"], "query": p["query"], "answer": p["answer"], "mentions": p["mentions"]}
            for p in analysis["per_response"]
        ],
        "issues": [{"type": c.kind, "severity": c.severity, "description": tag + c.description} for c in cands],
        "recommendations": recs,
    }
    return result, trace


def run_analysis(
    brand: str,
    competitors: list[str],
    queries: list[str],
    verified_facts: list[str],
    demo_mode: bool = False,
) -> dict:
    """Public entry point. See module docstring for the returned structure."""
    result, _ = run_analysis_with_trace(brand, competitors, queries, verified_facts, demo_mode)
    return result
