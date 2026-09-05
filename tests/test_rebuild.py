"""What happens on the second run of golden/build_golden.py.

    python3 -m unittest tests.test_rebuild

golden/ is the state, dataset/ is read-only input. Each test copies golden/ and
dataset/ into a scratch root, edits one side, rebuilds there and checks:

  1. dataset/ is never written.
  2. a rebuild merges: a request filed only in golden_requests.csv (a live
     route) or dropped from a refreshed export is still there afterwards, and
     the run reports how many were carried forward.
  3. facts are frozen, conclusions are recomputed: an export that now states a
     different requested_by / raw_ask does not touch the filed row, while a CRM
     account created for a company that was only ever requested collapses every
     historical row for that company onto one company_id with a CRM record.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LIVE_ROUTE = {
    "request_id": "R9001", "company_id": "", "company_as_written": "Vireo Systems",
    "target_title": "Chief Data Officer", "requested_by": "Live Router", "request_date": "2026-09-01",
    "raw_ask": "routed live from Slack: Vireo Systems, Chief Data Officer", "value_usd": "300000",
    "urgency_declared": "High", "status_as_filed": "Routed", "routed_to": "Priya Raghunathan",
    "routed_on": "2026-09-01", "route_score": "0.500", "route_reason": "live route",
    "asked_date": "2026-09-01", "responded": "", "intro_sent": "", "meeting_booked": "", "opportunity_usd": "",
    "offer_in_thread": "N", "thread_replies": "0", "thread_all_noise": "no replies", "resolved_by": "",
    "needs_review": "", "contradicts_log": "", "blocked_reason": "",
}
DROPPED_FROM_EXPORT = "R1199"  # a Vireo Systems request the refreshed export no longer has
NEW_CRM_ACCOUNT = {
    "account_id": "A1999", "account_name": "Vireo Systems", "domain": "vireosystems.com",
    "owner": "Sloane Fairweather", "stage": "Prospect", "arr_potential_usd": "1200000",
    "industry": "Technology", "employee_count": "900", "hq": "Austin", "last_touch_date": "2026-09-01",
}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class RebuildTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="halyard-rebuild-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copytree(ROOT / "dataset", self.root / "dataset")
        (self.root / "golden").mkdir()
        for p in (ROOT / "golden").iterdir():
            if p.suffix in (".py", ".csv"):
                shutil.copy(p, self.root / "golden" / p.name)
        self.requests = self.root / "golden" / "golden_requests.csv"
        self.companies = self.root / "golden" / "golden_companies.csv"
        self.export = self.root / "dataset" / "intro_requests.csv"
        self.crm = self.root / "dataset" / "crm_accounts.csv"
        self.baseline = read_csv(self.requests)

    def build(self) -> str:
        proc = subprocess.run([sys.executable, str(self.root / "golden" / "build_golden.py")],
                              capture_output=True, text=True, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def by_id(self) -> dict[str, dict]:
        return {r["request_id"]: r for r in read_csv(self.requests)}

    def test_dataset_is_never_written(self):
        before = tree_digest(self.root / "dataset")
        self.build()
        self.assertEqual(tree_digest(self.root / "dataset"), before)

    def test_rebuild_is_idempotent(self):
        first = self.build()
        bytes_after_first = self.requests.read_bytes()
        second = self.build()
        self.assertEqual(self.requests.read_bytes(), bytes_after_first)
        self.assertIn("0 appended", first)
        self.assertIn("0 with recomputed", second)

    def test_rebuild_merges_and_carries_forward(self):
        write_csv(self.requests, self.baseline + [LIVE_ROUTE])
        write_csv(self.export, [r for r in read_csv(self.export) if r["request_id"] != DROPPED_FROM_EXPORT])

        out = self.build()

        rows = self.by_id()
        self.assertEqual(len(rows), len(self.baseline) + 1)
        self.assertIn("2 not in dataset/intro_requests.csv and carried forward", out)
        self.assertIn(DROPPED_FROM_EXPORT, rows, "a request dropped from a refreshed export must survive")
        self.assertEqual(rows[DROPPED_FROM_EXPORT], {r["request_id"]: r for r in self.baseline}[DROPPED_FROM_EXPORT])
        live = rows["R9001"]
        for fact in ("requested_by", "request_date", "raw_ask", "company_as_written", "status_as_filed",
                     "routed_to", "routed_on", "route_reason", "target_title"):
            self.assertEqual(live[fact], LIVE_ROUTE[fact], fact)
        self.assertEqual(live["company_id"], rows[DROPPED_FROM_EXPORT]["company_id"],
                         "the live route resolves to the same company as the filed Vireo Systems rows")
        self.assertEqual(live["resolved_by"], "new-company")
        self.assertEqual(live["blocked_reason"], "", "a routed request is not blocked")
        company = {c["company_id"]: c for c in read_csv(self.companies)}[live["company_id"]]
        self.assertEqual(int(company["total_requests"]),
                         sum(1 for r in rows.values() if r["company_id"] == live["company_id"]))

        # and again: still there on the third run
        self.build()
        self.assertIn("R9001", self.by_id())

    def test_facts_are_frozen(self):
        export = read_csv(self.export)
        target = next(r for r in export if r["request_id"] == "R1001")
        target["requested_by"] = "Someone Else"
        target["raw_ask"] = "a completely rewritten ask"
        target["status"] = "Closed - won"
        write_csv(self.export, export)

        out = self.build()

        filed = {r["request_id"]: r for r in self.baseline}["R1001"]
        now = self.by_id()["R1001"]
        for fact in ("requested_by", "raw_ask", "status_as_filed", "company_as_written", "request_date"):
            self.assertEqual(now[fact], filed[fact], fact)
        self.assertIn("R1001: source now differs on requested_by, raw_ask, status_as_filed (kept filed)", out)

    def test_conclusions_are_recomputed_when_crm_catches_up(self):
        write_csv(self.requests, self.baseline + [LIVE_ROUTE])
        self.build()
        before = self.by_id()
        vireo_ids = {r["request_id"] for r in before.values() if r["company_as_written"] == "Vireo Systems"}
        self.assertIn("R9001", vireo_ids)
        old_company_id = {before[rid]["company_id"] for rid in vireo_ids}
        self.assertEqual(len(old_company_id), 1)
        self.assertTrue(all(before[rid]["resolved_by"].endswith("new-company") for rid in vireo_ids))
        self.assertTrue(all("no CRM account" in before[rid]["needs_review"] for rid in vireo_ids))

        write_csv(self.crm, read_csv(self.crm) + [NEW_CRM_ACCOUNT])
        out = self.build()

        after = self.by_id()
        self.assertEqual({after[rid]["company_id"] for rid in vireo_ids}, old_company_id,
                         "one company_id for every Vireo Systems row, pinned to the id already filed")
        for rid in vireo_ids:
            self.assertTrue(after[rid]["resolved_by"].endswith("crm-name"), f"{rid} {after[rid]['resolved_by']}")
            self.assertNotIn("no CRM account", after[rid]["needs_review"], rid)
            self.assertNotEqual(after[rid]["blocked_reason"], "company has no CRM record", rid)
            for fact in ("requested_by", "request_date", "raw_ask", "company_as_written", "status_as_filed",
                         "routed_to", "routed_on", "route_reason"):
                self.assertEqual(after[rid][fact], before[rid][fact], f"{rid} {fact}")
        same_company = [rid for rid, r in before.items() if r["company_id"] in old_company_id]
        self.assertIn(f"{len(same_company)} with recomputed", out)
        company = {c["company_id"]: c for c in read_csv(self.companies)}[next(iter(old_company_id))]
        self.assertEqual(company["crm_account_ids"], "A1999")
        self.assertEqual(company["domain"], "vireosystems.com")
        self.assertEqual(sum(1 for c in read_csv(self.companies) if "Vireo" in c["company_name"]), 1,
                         "the company must not split into a requested one and a CRM one")


if __name__ == "__main__":
    unittest.main()
