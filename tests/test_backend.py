"""Backend tests. Runs with `python -m unittest tests.test_backend` or pytest.
No network access and no API keys are needed."""

import asyncio
import os
import unittest
from unittest import mock

from backend import analyzer, scanner, truthguard
from backend.agent import DEMO_ANSWER_PREFIX, DEMO_LABEL, run_analysis, run_analysis_with_trace
from backend.scanner import ScanResult

ROOT_KEYS = ["brand", "visibility_score", "mention_rate", "competitors", "responses", "issues", "recommendations"]


def ok(query, answer, provider="openai"):
    return ScanResult(provider, query, answer=answer, ok=True)


def _timeout_wait(coro, timeout):
    coro.close()
    raise asyncio.TimeoutError


def run(coro):
    return asyncio.run(coro)


class TestNormalizationAndMatching(unittest.TestCase):
    def test_name_normalization(self):
        self.assertEqual(analyzer.normalize_name("  Hub-Spot, Inc. "), "hub spot inc")
        self.assertEqual(analyzer.normalize_name("Café"), "cafe")
        self.assertEqual(analyzer.normalize_name("AT&T"), "at and t")

    def test_variants(self):
        v = analyzer.brand_variants("Sales Force Inc.")
        self.assertIn("sales force", v)
        self.assertIn("salesforce", v)

    def test_case_insensitive_and_variant_match(self):
        self.assertTrue(analyzer.mentions_brand("We love ACME for this.", "Acme"))
        self.assertTrue(analyzer.mentions_brand("Try HubSpot today.", "Hub Spot"))
        self.assertTrue(analyzer.mentions_brand("Acme's pricing is fair.", "Acme"))
        self.assertTrue(analyzer.mentions_brand("Acme, Inc. is a vendor.", "Acme Inc"))

    def test_no_false_positive_substrings(self):
        self.assertFalse(analyzer.mentions_brand("The acmeology textbook", "Acme"))
        self.assertFalse(analyzer.mentions_brand("Pineapple sales rose", "Apple"))
        self.assertFalse(analyzer.mentions_brand("Zoho is great", "Zo"))

    def test_longer_tracked_name_wins(self):
        text = "Acme Pro is the best choice."
        hits = analyzer.detect_in_sentence(text, ["Acme", "Acme Pro"])
        self.assertEqual(hits, {"Acme Pro"})

    def test_evidence_is_exact_substring(self):
        text = "Intro line.\nAcme offers CRM tools. Other text."
        ev = analyzer.find_mentions(text, "Acme")
        self.assertEqual(ev, ["Acme offers CRM tools."])
        self.assertIn(ev[0], text)


class TestScoring(unittest.TestCase):
    def test_quality_levels(self):
        self.assertEqual(analyzer.score_mentions([]), 0)
        self.assertEqual(analyzer.score_mentions(["Also see Acme."]), 1)
        self.assertEqual(analyzer.score_mentions(["Acme offers solid reporting."]), 2)
        self.assertEqual(analyzer.score_mentions(["Acme is the best choice."]), 3)
        self.assertEqual(analyzer.score_mentions(["I would not recommend Acme."]), 1)

    def test_visibility_formula(self):
        self.assertEqual(analyzer.visibility_score([3, 0, 0]), 33.33)
        self.assertEqual(analyzer.visibility_score([3, 3]), 100.0)
        self.assertEqual(analyzer.visibility_score([1, 2, 0, 3]), 50.0)

    def test_mention_rate(self):
        self.assertEqual(analyzer.mention_rate([0, 1, 3, 0]), 50.0)

    def test_empty_never_divides_by_zero(self):
        self.assertEqual(analyzer.visibility_score([]), 0.0)
        self.assertEqual(analyzer.mention_rate([]), 0.0)

    def test_failed_requests_excluded_from_denominator(self):
        results = [
            ok("q1", "Acme is the best choice."),
            ScanResult("openai", "q2", error="timeout"),
            ScanResult("openai", "q3", answer="", ok=False, error="x"),
        ]
        a = analyzer.analyze_responses("Acme", [], results)
        self.assertEqual(a["successful"], 1)
        self.assertEqual(a["brand"]["visibility_score"], 100.0)
        self.assertEqual(len(a["failures"]), 2)

    def test_empty_responses(self):
        a = analyzer.analyze_responses("Acme", ["Beta"], [ok("q", "   "), ok("q", "")])
        self.assertEqual(a["successful"], 0)
        self.assertEqual(a["brand"]["visibility_score"], 0.0)
        self.assertEqual(a["competitors"][0]["visibility_score"], 0.0)


class TestCompetitorComparison(unittest.TestCase):
    def setUp(self):
        self.results = [
            ok("best crm?", "Beta is the best CRM. Gamma offers a good alternative."),
            ok("cheap crm?", "Acme is a top choice for budgets."),
            ok("crm for startups?", "Gamma is popular with startups."),
        ]
        self.a = analyzer.analyze_responses("Acme", ["Beta", "Gamma", "acme"], self.results)

    def test_scores_use_same_system(self):
        comp = {c["name"]: c["visibility_score"] for c in self.a["competitors"]}
        self.assertEqual(set(comp), {"Beta", "Gamma"})  # brand duplicate removed
        self.assertEqual(comp["Beta"], 33.33)  # 3 / 9
        self.assertEqual(comp["Gamma"], 44.44)  # (2 + 2) / 9

    def test_gaps(self):
        gaps = analyzer.find_visibility_gaps("Acme", ["Beta", "Gamma"], self.a["per_response"])
        queries = [g["query"] for g in gaps]
        self.assertIn("best crm?", queries)
        self.assertNotIn("cheap crm?", queries)
        top = gaps[0]
        self.assertEqual(top["severity"], "high")
        self.assertTrue(top["evidence"])
        self.assertIn(top["evidence"][0]["sentence"], self.results[0].answer + self.results[2].answer)


class TestScanner(unittest.TestCase):
    def test_missing_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = run(scanner.scan_one("openai", "q"))
        self.assertFalse(r.ok)
        self.assertIn("OPENAI_API_KEY", r.error)
        self.assertEqual(r.answer, "")

    def test_api_failure_does_not_leak_key(self):
        async def boom(query, key, timeout):
            raise RuntimeError(f"401 bad key {key}")

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-secret-123456789"}, clear=True), \
                mock.patch.dict(scanner._PROVIDER_FUNCS, {"openai": boom}):
            r = run(scanner.scan_one("openai", "q"))
        self.assertFalse(r.ok)
        self.assertNotIn("sk-secret-123456789", r.error)
        self.assertIn("RuntimeError", r.error)

    def test_timeout(self):
        async def slow(query, key, timeout):
            await asyncio.sleep(5)

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k" * 10, "GEO_TIMEOUT": "1"}, clear=True), \
                mock.patch.dict(scanner._PROVIDER_FUNCS, {"openai": slow}), \
                mock.patch("backend.scanner.asyncio.wait_for", side_effect=_timeout_wait):
            r = run(scanner.scan_one("openai", "q"))
        self.assertFalse(r.ok)
        self.assertIn("timed out", r.error)

    def test_success_and_sanitization(self):
        async def good(query, key, timeout):
            return "  Acme is great.\x00\x07  "

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k" * 10}, clear=True), \
                mock.patch.dict(scanner._PROVIDER_FUNCS, {"openai": good}):
            r = run(scanner.scan_one("openai", "q"))
        self.assertTrue(r.ok)
        self.assertEqual(r.answer, "Acme is great.")

    def test_concurrent_scan_mixed(self):
        async def flaky(query, key, timeout):
            if "bad" in query:
                raise ConnectionError("down")
            return f"answer to {query}"

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k" * 10}, clear=True), \
                mock.patch.dict(scanner._PROVIDER_FUNCS, {"openai": flaky}):
            res = run(scanner.scan_queries(["good one", "bad one"], ["openai"]))
        self.assertEqual([r.ok for r in res], [True, False])

    def test_providers_config(self):
        with mock.patch.dict(os.environ, {"GEO_PROVIDERS": "OpenAI, gemini ,bogus"}, clear=True):
            self.assertEqual(scanner.configured_providers(), ["openai", "gemini"])


class TestTruthGuard(unittest.TestCase):
    FACTS = ["Acme was founded in 2012", "Acme has 500 employees", "Acme offers a free plan"]

    def test_verified_contradiction_number(self):
        f = truthguard.check_answer("Acme", "Acme was founded in 2015 in Berlin.", self.FACTS)
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].kind, "contradiction")
        self.assertEqual(f[0].fact, "Acme was founded in 2012")

    def test_matching_fact_not_flagged(self):
        self.assertEqual(truthguard.check_answer("Acme", "Acme was founded in 2012.", self.FACTS), [])

    def test_hedged_is_uncertain(self):
        f = truthguard.check_answer("Acme", "Acme reportedly has about 300 employees.", self.FACTS)
        self.assertEqual([x.kind for x in f], ["uncertain"])

    def test_polarity_mismatch_is_uncertain_not_verified(self):
        f = truthguard.check_answer("Acme", "Acme does not offer a free plan.", self.FACTS)
        self.assertEqual([x.kind for x in f], ["uncertain"])

    def test_missing_information_not_flagged(self):
        self.assertEqual(truthguard.check_answer("Acme", "Acme is a software company.", self.FACTS), [])
        self.assertEqual(truthguard.check_answer("Acme", "Acme is based in a European city.", self.FACTS), [])

    def test_ignores_other_brands_and_unrelated_numbers(self):
        self.assertEqual(truthguard.check_answer("Acme", "Beta was founded in 2015.", self.FACTS), [])
        self.assertEqual(truthguard.check_answer("Acme", "Acme won 3 awards.", self.FACTS), [])

    def test_no_facts(self):
        self.assertEqual(truthguard.check_answer("Acme", "Acme was founded in 2015.", []), [])

    def test_unit_conversion(self):
        nums = truthguard.extract_numbers("raised $2 million and 15% growth, 1,200 customers")
        self.assertIn(("currency", 2_000_000.0), nums)
        self.assertIn(("percent", 15.0), nums)
        self.assertIn(("custo", 1200.0), nums)


class TestAgentAndDemo(unittest.TestCase):
    QUERIES = ["What is the best CRM?", "Which CRM is cheapest?", "CRM for startups?"]
    FACTS = ["Acme was founded in 2012"]

    def demo(self):
        return run_analysis("Acme", ["Beta", "Gamma"], self.QUERIES, self.FACTS, demo_mode=True)

    def test_exact_schema(self):
        r = self.demo()
        self.assertEqual(list(r.keys()), ROOT_KEYS)
        self.assertIsInstance(r["visibility_score"], float)
        self.assertIsInstance(r["mention_rate"], float)
        for c in r["competitors"]:
            self.assertEqual(set(c), {"name", "score"})
        for x in r["responses"]:
            self.assertEqual(set(x), {"provider", "query", "answer", "mentions"})
        for i in r["issues"]:
            self.assertEqual(set(i), {"type", "severity", "description"})
        for rec in r["recommendations"]:
            self.assertEqual(set(rec), {"title", "reason", "action"})

    def test_demo_deterministic_and_labelled(self):
        self.assertEqual(self.demo(), self.demo())
        r = self.demo()
        self.assertTrue(all(x["provider"] == "demo" for x in r["responses"]))
        self.assertTrue(all(x["answer"].startswith(DEMO_ANSWER_PREFIX) for x in r["responses"]))
        self.assertTrue(all(i["description"].startswith(DEMO_LABEL) for i in r["issues"]))
        self.assertTrue(all(rec["reason"].startswith(DEMO_LABEL) for rec in r["recommendations"]))

    def test_demo_works_without_keys_and_no_network(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("backend.scanner.run_scan", side_effect=AssertionError("network used")):
            r = self.demo()
        self.assertEqual(len(r["responses"]), 3)

    def test_demo_uses_real_analysis(self):
        r = self.demo()
        self.assertGreater(r["visibility_score"], 0)
        self.assertEqual(len(r["recommendations"]), 3)
        self.assertTrue(any(i["type"] == "visibility_gap" for i in r["issues"]))
        self.assertTrue(any(i["type"] == "misinformation" for i in r["issues"]))  # synthetic wrong year

    def test_live_without_keys_is_honest(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = run_analysis("Acme", ["Beta"], self.QUERIES, self.FACTS)
        self.assertEqual(r["responses"], [])
        self.assertEqual(r["visibility_score"], 0.0)
        self.assertEqual(r["mention_rate"], 0.0)
        self.assertEqual(r["issues"][0]["type"], "scan_error")
        self.assertEqual(len(r["recommendations"]), 3)
        self.assertIn("OPENAI_API_KEY", r["issues"][0]["description"])
        self.assertNotIn(DEMO_LABEL, str(r))

    def test_live_workflow_with_mocked_provider(self):
        async def fake(query, key, timeout):
            if "cheapest" in query:
                raise TimeoutError("slow")
            if "startups" in query:
                return "Beta is the best option."
            return "Acme is a top choice. Acme was founded in 2020."

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k" * 10}, clear=True), \
                mock.patch.dict(scanner._PROVIDER_FUNCS, {"openai": fake}):
            r, trace = run_analysis_with_trace("Acme", ["Beta"], self.QUERIES, self.FACTS)
        self.assertEqual(len(r["responses"]), 2)  # failed request excluded
        types = [i["type"] for i in r["issues"]]
        self.assertEqual(types[0], "misinformation")  # most significant first
        self.assertIn("scan_error", types)
        self.assertIn("visibility_gap", types)
        self.assertIn("2012", r["recommendations"][0]["reason"])
        self.assertEqual(len(trace), 5)
        self.assertNotIn("k" * 10, str(r))

    def test_blank_brand_rejected(self):
        with self.assertRaises(ValueError):
            run_analysis("  ", [], ["q"], [], demo_mode=True)

    def test_no_queries(self):
        r = run_analysis("Acme", ["Beta"], [], [], demo_mode=True)
        self.assertEqual(r["responses"], [])
        self.assertEqual(r["visibility_score"], 0.0)
        self.assertEqual(len(r["recommendations"]), 3)


if __name__ == "__main__":
    unittest.main()
