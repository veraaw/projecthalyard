"""Tests for analysis/crm/writeback.py, the two CRM exports.

    python3 -m unittest tests.test_writeback

Every group is re-derived here from golden/ and dataset/crm_accounts.csv and
compared with what the module produced; counts are never fixed, because the
request file grows on every merge.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.crm import writeback  # noqa: E402
from analysis.crm.writeback import (  # noqa: E402
    CREATE, DEFAULT_STAGE, GROUPS, IMPORT_COLUMNS, MERGE, OWNERS, REOPEN, REVIEW_COLUMNS, STALE,
    STALE_TOUCH_DAYS, STATUS, Writeback, split_bar,
)
from golden.build_golden import OPEN_STATUSES  # noqa: E402

AS_OF = date(2026, 9, 5)
G = ROOT / "golden"
D = ROOT / "dataset"


def rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class WritebackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wb = Writeback(AS_OF)
        cls.review = cls.wb.review_rows()
        cls.imports = cls.wb.import_rows()
        cls.companies = {c["company_id"]: c for c in rows(G / "golden_companies.csv") if int(c["total_requests"] or 0)}
        cls.accounts = {a["account_id"]: a for a in rows(D / "crm_accounts.csv")}
        cls.requests = rows(G / "golden_requests.csv")

    def by_group(self, group: str) -> list:
        return [r for r in self.review if r.group == group]

    def live(self, cid: str) -> list[dict]:
        return [r for r in self.requests if r["company_id"] == cid and r["status_as_filed"] in OPEN_STATUSES]

    # -- the five groups, re-derived ------------------------------------------
    def test_create_is_every_requested_company_without_an_account(self):
        expected = {cid for cid, c in self.companies.items() if not c["crm_account_ids"]}
        self.assertTrue(expected)
        self.assertEqual({r.company_id for r in self.by_group(CREATE)}, expected)
        self.assertEqual({r["account_name"] for r in self.imports}, {self.companies[c]["company_name"] for c in expected})

    def test_merge_is_every_duplicate_and_owners_the_disagreeing_subset(self):
        dups = {cid for cid, c in self.companies.items() if c["duplicate_accounts"] != "no"}
        disagree = {cid for cid in dups if len(split_bar(self.companies[cid]["owner"])) > 1}
        self.assertTrue(dups > disagree, "need at least one same-owner duplicate to tell the groups apart")
        self.assertEqual({r.company_id for r in self.by_group(MERGE)}, dups)
        self.assertEqual({r.company_id for r in self.by_group(OWNERS)}, disagree)
        for r in self.by_group(MERGE):
            survivor = r.action.split(" into ")[-1]
            self.assertFalse(survivor.startswith("A9"), r.action)
            self.assertIn(survivor, split_bar(r.crm_account_ids))

    def test_reopen_is_live_requests_against_closed_lost(self):
        expected = {cid for cid, c in self.companies.items() if c["stage"] == "Closed Lost" and self.live(cid)}
        closed_but_quiet = [cid for cid, c in self.companies.items() if c["stage"] == "Closed Lost" and not self.live(cid)]
        self.assertTrue(closed_but_quiet, "need a Closed Lost account with nothing live to prove the filter")
        self.assertEqual({r.company_id for r in self.by_group(REOPEN)}, expected)
        for r in self.by_group(REOPEN):
            self.assertIn("reopen", r.action)
            self.assertIn("close", r.action)
            self.assertEqual(r.value_at_stake_usd, sum(int(q["value_usd"] or 0) for q in self.live(r.company_id)))

    def test_stale_is_open_requests_and_no_touch_in_90_days(self):
        expected = set()
        for cid, c in self.companies.items():
            touches = [self.accounts[a]["last_touch_date"] for a in split_bar(c["crm_account_ids"]) if a in self.accounts]
            if not touches or c["stage"] == "Closed Lost" or not self.live(cid):
                continue
            if (AS_OF - date.fromisoformat(max(touches))).days >= STALE_TOUCH_DAYS:
                expected.add(cid)
        self.assertEqual({r.company_id for r in self.by_group(STALE)}, expected)
        # as of the day before the oldest touch turns 90, nothing is stale yet
        oldest = date.fromisoformat(min(a["last_touch_date"] for a in self.accounts.values()))
        self.assertEqual(Writeback(oldest + timedelta(days=STALE_TOUCH_DAYS - 1)).stale(), [])

    # -- rows and ordering ------------------------------------------------------
    def test_every_row_is_a_recommendation_with_its_evidence(self):
        for r in self.review:
            self.assertEqual(r.status, STATUS)
            self.assertEqual(r.executed_on, "")
            self.assertTrue(r.action and r.why and r.evidence, r)
            self.assertTrue(r.request_ids, r)
            for rid in split_bar(r.request_ids):
                self.assertTrue(rid.startswith("R"), rid)

    def test_groups_sorted_by_cost_creation_first_staleness_last(self):
        ranks = [r.rank for r in self.review]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(self.review[0].group, CREATE)
        self.assertEqual(self.review[-1].group, STALE)
        for g in GROUPS:
            values = [r.value_at_stake_usd for r in self.by_group(g)]
            self.assertEqual(values, sorted(values, reverse=True), g)

    # -- the two files ----------------------------------------------------------
    def test_import_file_shape(self):
        self.assertEqual(len(self.imports), len(self.by_group(CREATE)))
        for row in self.imports:
            self.assertEqual(list(row), IMPORT_COLUMNS)
            self.assertEqual(row["stage"], DEFAULT_STAGE)
            cid = next(cid for cid, c in self.companies.items() if c["company_name"] == row["account_name"])
            reqs = sorted((r for r in self.requests if r["company_id"] == cid), key=lambda r: (r["request_date"], r["request_id"]))
            self.assertEqual(row["owner"], reqs[0]["requested_by"], "owner is the rep who asked first")
            self.assertEqual(row["blocked_requests"], len(self.live(cid)))
            self.assertEqual(row["requested_value_usd"], sum(int(r["value_usd"] or 0) for r in self.live(cid)))

    def test_merges_and_owner_changes_never_reach_the_import_file(self):
        import_names = {r["account_name"] for r in self.imports}
        for r in self.review:
            if r.group in (MERGE, OWNERS):
                self.assertNotIn(r.company_name, import_names)

    def test_write_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with mock.patch.object(writeback, "CRM", out), \
                    mock.patch.object(writeback, "IMPORT_OUT", out / "crm_import.csv"), \
                    mock.patch.object(writeback, "REVIEW_OUT", out / "crm_review.csv"):
                imports, review = writeback.write_all(AS_OF)
            got_import = rows(out / "crm_import.csv")
            got_review = rows(out / "crm_review.csv")
        self.assertEqual(list(got_import[0]), IMPORT_COLUMNS)
        self.assertEqual(list(got_review[0]), REVIEW_COLUMNS)
        self.assertEqual(len(got_import), len(imports))
        self.assertEqual(len(got_review), sum(r.group != CREATE for r in review))
        self.assertEqual({r["group"] for r in got_review}, set(GROUPS) - {CREATE})
        self.assertTrue(all(r["status"] == STATUS and not r["executed_on"] for r in got_review))


if __name__ == "__main__":
    unittest.main()
