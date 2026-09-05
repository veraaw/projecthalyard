"""Tests for analysis/trace.py, checked against Harrowgate Health.

    python3 -m unittest tests.test_trace
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.trace import MISSED, OFFER, WARN, WORKED, Data, Trace, find_company  # noqa: E402

AS_OF = date(2026, 9, 5)


class HarrowgateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Data.load()
        cls.company = find_company(cls.data, "Harrowgate Health")
        cls.trace = Trace(cls.data, cls.company, AS_OF)
        cls.text = cls.trace.render()

    def test_lookup_by_id_alias_and_account(self):
        for q in ("C018", "A1050", "harrowgate health", "Harrowgate Health"):
            self.assertEqual(find_company(self.data, q)["company_id"], "C018", q)
        self.assertIsNone(find_company(self.data, "no such company"))

    def test_header_counts(self):
        reqs = self.trace.requests
        self.assertEqual(len(reqs), 9)
        self.assertEqual(len({r["requested_by"] for r in reqs}), 7)
        self.assertEqual(len({r["target_title"] for r in reqs}), 6)
        self.assertIn("9 requests from 7 people wanting 6 different titles", self.text)

    def test_disagreements(self):
        dis = "\n".join(self.trace.disagreements())
        self.assertIn('R1173: filed "Intro sent" but intro_outcomes.csv has no row', dis)
        self.assertIn('R1090: filed "Closed - no path" but supply_reach.csv has 11 paths', dis)
        self.assertIn("R1136: Elena Duvall offered", dis)

    def test_reach_sorted_by_strength(self):
        strengths = [float(p["strength"]) for p in self.trace.paths]
        self.assertEqual(strengths, sorted(strengths, reverse=True))
        self.assertEqual(self.trace.paths[0]["connector"], "Elena Duvall")

    def test_chronology(self):
        events = self.trace.events()
        self.assertTrue(40 <= len(events) <= 55, len(events))
        self.assertEqual({e.source for e in events},
                         {"intro_requests.csv", "slack_threads.jsonl", "intro_outcomes.csv", "crm_accounts.csv"})
        n_slack = sum(len(t["messages"]) for rid, t in self.data.threads.items() if rid in self.trace.request_ids)
        self.assertEqual(sum(e.source == "slack_threads.jsonl" for e in events), n_slack)
        marks = {e.mark for e in events}
        self.assertTrue({MISSED, WORKED, OFFER, WARN} <= marks)
        # within a request block the lines are oldest first
        for line_block in "\n".join(self.trace.chronology()).split("\n\n"):
            dates = [ln[3:13] for ln in line_block.splitlines() if ln[3:7].isdigit()]
            self.assertEqual(dates, sorted(dates))

    def test_next_steps(self):
        steps = self.trace.next_steps()
        self.assertEqual(len(steps), 5)
        self.assertEqual([s.order for s in steps], [1, 2, 3, 4, 5])
        elena, tomas = steps[0], steps[1]
        self.assertEqual(elena.who, "Elena Duvall")
        self.assertEqual(elena.request_ids, ["R1136"])
        self.assertEqual(tomas.who, "Tomás Beckett")
        self.assertEqual(tomas.why.count("said yes"), 2)
        self.assertEqual(set(tomas.request_ids) >= {"R1057", "R1157"}, True)
        self.assertEqual(steps[2].who, "Dana Whitfield")
        self.assertEqual(steps[3].who, "Imani Mkhize")
        reps = steps[4]
        self.assertIn("7 reps", reps.role)
        self.assertTrue(reps.who.startswith("Imani Mkhize (355 days)"), reps.who)
        self.assertTrue(reps.who.endswith("Curtis Hartigan (81 days)"), reps.who)
        self.assertEqual(reps.action, "tell them it's with Tomás Beckett")
        self.assertIn("the oldest has been waiting 355 days", reps.why)


class NoDisagreementTest(unittest.TestCase):
    def test_section_two_skipped_when_clean(self):
        data = Data.load()
        clean = [c for c in data.companies if int(c["total_requests"] or 0) and not Trace(data, c, AS_OF).disagreements()]
        self.assertTrue(clean, "expected at least one company with nothing to disagree about")
        self.assertNotIn("## 2.", Trace(data, clean[0], AS_OF).render())


if __name__ == "__main__":
    unittest.main()
