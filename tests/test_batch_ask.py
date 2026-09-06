"""The batched-ask composer (dashboard/batch_ask.py).

    python3 -m unittest tests.test_batch_ask

Against the golden files on disk: one message per (cycle, connector) holding an
allocation, every allocated request id on exactly one record, no message over the
connector's stated capacity, one block per company, nothing in the text that the
spec forbids ($, route scores, request ids, urgency), deterministic output, and
the offerer template for an off-roster connector asked over an offer path.
"""
from __future__ import annotations

import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dashboard import batch_ask  # noqa: E402
from golden import build_golden as bg  # noqa: E402

RID = re.compile(r"R1\d{3}")
URGENCY = ("high", "medium", "low", "urgent")


def block(message: str, company_name: str) -> list[str]:
    """The lines of one company's block: its header line through the blank line that ends it."""
    lines = message.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(company_name))
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return lines[start:end]


class ComposerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allocation = bg.read_allocation(batch_ask.ALLOCATION)
        cls.requests = bg.read_csv(batch_ask.REQUESTS)
        cls.roster = bg.load_roster()
        cls.templates = batch_ask.load_templates()
        cls.records = batch_ask.compose(cls.allocation, cls.requests, cls.roster, cls.templates)
        cls.allocated = [a for a in cls.allocation if a["allocated_to"]]
        cls.by_key = {(m["cycle"], m["connector"]): m for m in cls.records}

    def test_one_message_per_cycle_connector(self):
        expected = {(a["cycle"], a["allocated_to"]) for a in self.allocated}
        self.assertTrue(expected, "the golden allocation holds at least one allocated row")
        self.assertEqual(Counter((m["cycle"], m["connector"]) for m in self.records), Counter(expected))
        for m in self.records:
            self.assertTrue(m["message"].strip(), f"{m['cycle']} {m['connector']}: empty message")

    def test_every_allocated_request_id_on_exactly_one_record(self):
        seen = Counter(rid for m in self.records for rid in m["request_ids"])
        self.assertEqual(seen, Counter(a["request_id"] for a in self.allocated))
        self.assertEqual(set(seen.values()), {1})
        for m in self.records:  # the nested company/title blocks carry the same ids, none dropped
            nested = [rid for c in m["companies"] for g in c["contacts"] for t in g["titles"] for rid in t["request_ids"]]
            self.assertEqual(Counter(nested), Counter(m["request_ids"]), m["connector"])
            self.assertEqual(m["request_count"], len(m["request_ids"]))

    def test_no_message_over_stated_capacity(self):
        checked = 0
        for m in self.records:
            r = self.roster.get(m["connector"])
            if r is None:
                self.assertIsNone(m["capacity"])
                continue
            checked += 1
            self.assertEqual(m["capacity"], int(r["stated_monthly_capacity"]))
            self.assertLessEqual(m["request_count"], int(r["stated_monthly_capacity"]),
                                 f"{m['cycle']} {m['connector']} covers {m['request_count']} requests")
        self.assertGreater(checked, 0, "at least one roster connector holds an allocation")

    def test_companies_with_multiple_requests_collapse_to_one_block(self):
        multi = 0
        for m in self.records:
            per_company = Counter(a["company_id"] for a in self.allocated
                                  if a["cycle"] == m["cycle"] and a["allocated_to"] == m["connector"])
            self.assertEqual([c["company_id"] for c in m["companies"]], list(dict.fromkeys(
                [c["company_id"] for c in m["companies"]])), f"{m['connector']}: a company appears in two blocks")
            self.assertEqual(set(per_company), {c["company_id"] for c in m["companies"]})
            for c in m["companies"]:
                self.assertEqual(len(c["request_ids"]), per_company[c["company_id"]])
                self.assertEqual(m["message"].count(c["company_name"] + " —"), 1 if len(c["contacts"]) == 1 else 0)
                self.assertGreaterEqual(m["message"].count(c["company_name"]), 1)
                if per_company[c["company_id"]] > 1:
                    multi += 1
        self.assertGreater(multi, 0, "the golden allocation has a connector with two requests for one company")

    def test_duplicate_title_renders_once_with_a_count(self):
        # Two live requests for one (company, title) may land in different batches;
        # route the second down the first's path so one batch asks twice.
        by_title = {}
        allocation = [dict(a) for a in self.allocation]
        for a in allocation:
            if a["allocated_to"]:
                first = by_title.setdefault((a["company_id"], a["target_title"]), a)
                for k in ("allocated_to", "batch_id", "path_type", "contact_name"):
                    a[k] = first[k]
        records = batch_ask.compose(allocation, self.requests, self.roster, self.templates)
        hits = 0
        for m in records:
            for c in m["companies"]:
                for g in c["contacts"]:
                    for t in g["titles"]:
                        line = [ln for ln in block(m["message"], c["company_name"]) if ln.strip().startswith(f"- {t['target_title']} (")]
                        self.assertEqual(len(line), 1, f"{m['connector']} / {c['company_name']} / {t['target_title']}")
                        if t["count"] == 2:
                            self.assertTrue(line[0].endswith(", asked twice"), line[0])
                            hits += 1
                        elif t["count"] > 2:
                            self.assertTrue(line[0].endswith(f", asked {t['count']}x"), line[0])
                            hits += 1
                        else:
                            self.assertNotIn(", asked", line[0])
                            self.assertEqual(len(t["request_ids"]), 1)
        self.assertGreater(hits, 0, "the golden allocation has two live requests for one (company, title)")

    def test_message_body_carries_no_value_score_request_id_or_urgency(self):
        for m in self.records:
            body = m["message"]
            self.assertNotIn("$", body, m["connector"])
            self.assertIsNone(RID.search(body), m["connector"])
            for q in m["requests"]:
                if q["route_score"]:
                    self.assertNotIn(str(q["route_score"]), body, f"{m['connector']}: route score in the text")
                if q["value_usd"]:
                    self.assertNotIn(str(q["value_usd"]), body, f"{m['connector']}: value in the text")
            for word in URGENCY:
                self.assertIsNone(re.search(rf"\b{word}\b", body, re.I), f"{m['connector']}: urgency label {word!r}")

    def test_same_golden_state_renders_identically(self):
        again = batch_ask.compose(self.allocation, self.requests, self.roster, self.templates)
        self.assertEqual([m["message"] for m in again], [m["message"] for m in self.records])
        self.assertEqual(again, self.records)
        fresh = batch_ask.compose()
        self.assertEqual([m["message"] for m in fresh], [m["message"] for m in self.records])

    def test_offer_path_batch_to_non_roster_connector_selects_offerer_template(self):
        offerers = [m for m in self.records if not m["on_roster"] and all(q["path_type"] == "offer" for q in m["requests"])]
        self.assertTrue(offerers, "the golden allocation asks someone off the roster over an offer")
        for m in offerers:
            self.assertEqual(m["template"], batch_ask.OFFERER_TEMPLATE)
            self.assertIn("you offered on", m["message"])
            self.assertIn("these asks are still open", m["message"])
            self.assertTrue(m["offers"], m["connector"])
            for o in m["offers"]:
                self.assertRegex(o["date"], r"^\d{4}-\d{2}-\d{2}$", f"{m['connector']}: offer date missing")
                self.assertIn(f"{o['company_name']} in the thread on {o['date']}", m["message"])
        for m in self.records:
            if m["on_roster"]:
                self.assertEqual(m["template"], batch_ask.ROSTER_TEMPLATE)
                self.assertIn("here is what routes to you this cycle, reply with what you can take", m["message"])

    def test_paths_render_as_specified(self):
        for m in self.records:
            for c in m["companies"]:
                for g in c["contacts"]:
                    if g["path_type"] == "direct":
                        self.assertEqual(g["path"], f"via {g['contact_name']}")
                    elif g["path_type"] in ("investor", "board"):
                        self.assertEqual(g["path"], "via the board / exec team")
                    elif g["path_type"] == "offer":
                        self.assertIn(g["offer_date"], g["path"])
                    self.assertIn(g["path"], m["message"])

    def test_blocks_ordered_by_the_batch_highest_route_score(self):
        for m in self.records:
            scores = [max(batch_ask.score(q["route_score"]) for q in m["requests"] if q["company_id"] == c["company_id"])
                      for c in m["companies"]]
            self.assertEqual(scores, sorted(scores, reverse=True), m["connector"])
            positions = [m["message"].index(c["company_name"]) for c in m["companies"]]
            self.assertEqual(positions, sorted(positions), f"{m['connector']}: blocks out of order in the text")

    def test_retry_line_names_the_intro_that_fizzled(self):
        """A company the allocator routed afresh after an earlier intro went nowhere
        carries one retry line under its block header: who introduced whom, on
        what date; 'you' when the connector being asked sent that intro."""
        outcomes = bg.read_csv(batch_ask.OUTCOMES)
        intros = batch_ask.prior_intros(outcomes, self.requests)
        hits = own = 0
        for m in self.records:
            for c in m["companies"]:
                intro = intros.get(c["company_id"])
                expect = intro if intro and intro["date"][:7] < m["cycle"] else None
                self.assertEqual(c["retry"], expect, c["company_name"])
                lines = block(m["message"], c["company_name"])
                retry_lines = [ln for ln in lines if ln.startswith("  retry:")]
                if not expect:
                    self.assertEqual(retry_lines, [], c["company_name"])
                    continue
                hits += 1
                self.assertEqual(lines[1], c["retry_line"], "the retry line sits right under the company header")
                self.assertEqual(len(retry_lines), 1)
                self.assertIn(expect["date"], lines[1])
                self.assertIn(expect["requester"], lines[1])
                if expect["connector"] == m["connector"]:
                    own += 1
                    self.assertIn("you introduced", lines[1])
                    self.assertNotIn(m["connector"], lines[1])
                else:
                    self.assertIn(expect["connector"], lines[1])
        self.assertGreater(hits, 0, "the golden allocation retries at least one fizzled intro")
        self.assertGreater(own, 0, "at least one retry goes back to the connector who sent the intro")

    def test_templates_live_in_config_and_no_names_in_source(self):
        self.assertTrue(batch_ask.TEMPLATES.is_relative_to(ROOT / "config"))
        src = (ROOT / "dashboard" / "batch_ask.py").read_text(encoding="utf-8")
        for m in self.records:
            self.assertNotIn(m["connector"], src)
            for c in m["companies"]:
                self.assertNotIn(c["company_name"], src)
            for q in m["requests"]:
                if q["requested_by"]:
                    self.assertNotIn(q["requested_by"], src)
        for t in ("roster", "offerer"):
            self.assertIn(t, self.templates)


if __name__ == "__main__":
    unittest.main()
