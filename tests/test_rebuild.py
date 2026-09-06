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
  4. golden_allocation.csv is the connector history, keyed on (cycle,
     request_id): a rebuild in a new cycle appends and leaves every prior
     cycle byte-identical; a rebuild in the same cycle replaces only that
     cycle's rows; an ask allocated in one cycle with no outcome logged is
     flagged in the next, not proposed again.
  5. golden/completions.csv is the third fact source: an `ask_sent` row takes
     its request out of the next allocation and files the ask on it; the same
     completion_id twice (in one file, or applied twice) is one completion; the
     frozen fact columns never move; the Supabase read is merged into the CSV
     and a bad row fails before anything is written. No test touches the
     network: the Supabase read is a fake opener.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import golden.build_golden as bg  # noqa: E402
from golden.build_golden import ASKED, COMPLETION_COLUMNS, FACT_COLUMNS, NUDGED, STALE_ASK  # noqa: E402

CYCLE_1, CYCLE_2 = "2026-09-05", "2026-10-05"

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


class ScratchRootTest(unittest.TestCase):
    """A copy of dataset/ and golden/ to rebuild in."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="halyard-rebuild-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copytree(ROOT / "dataset", self.root / "dataset")
        (self.root / "golden").mkdir()
        # completions.csv is left out: these tests state what one completion
        # does, from a queue nobody has ticked anything off yet
        for p in (ROOT / "golden").iterdir():
            if p.suffix in (".py", ".csv") and p.name != "completions.csv":
                shutil.copy(p, self.root / "golden" / p.name)
        self.requests = self.root / "golden" / "golden_requests.csv"
        self.companies = self.root / "golden" / "golden_companies.csv"
        self.export = self.root / "dataset" / "intro_requests.csv"
        self.crm = self.root / "dataset" / "crm_accounts.csv"
        self.allocation = self.root / "golden" / "golden_allocation.csv"
        self.completions = self.root / "golden" / "completions.csv"
        self.baseline = read_csv(self.requests)

    def run_build(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(self.root / "golden" / "build_golden.py"), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=self.root, env=env)

    def build(self, as_of: str | None = None, *args: str) -> str:
        proc = self.run_build(*(["--as-of", as_of] if as_of else []), *args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def by_id(self) -> dict[str, dict]:
        return {r["request_id"]: r for r in read_csv(self.requests)}

    def cycle_lines(self, cycle: str) -> tuple[bytes, list[bytes]]:
        """(header, the raw lines of one cycle) as they sit in golden_allocation.csv."""
        header, *lines = self.allocation.read_bytes().split(b"\r\n")
        return header, [ln for ln in lines if ln.startswith(f"{cycle},".encode())]

    def cycle_rows(self, cycle: str) -> list[dict]:
        return [a for a in read_csv(self.allocation) if a["cycle"] == cycle]


class RebuildTest(ScratchRootTest):
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

    def test_unchanged_rebuild_leaves_every_golden_file_byte_identical(self):
        # what the 15-minute Action relies on: nothing new means nothing to commit
        self.build(CYCLE_1)
        digest = tree_digest(self.root / "golden")
        self.build(CYCLE_1)
        self.assertEqual(tree_digest(self.root / "golden"), digest)
        self.assertEqual(len({a["decided_at"] for a in self.cycle_rows("2026-09")}), 1)

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

    # -- 4. golden_allocation.csv is the connector history ------------------
    def test_new_cycle_appends_and_leaves_prior_cycles_byte_identical(self):
        first = self.build(CYCLE_1)
        header, sep = self.cycle_lines("2026-09")
        self.assertEqual(len(read_csv(self.allocation)), len(sep), "first run: the file is one cycle")
        self.assertIn("in 1 cycles (0 rows from 0 prior cycles carried forward", first)

        second = self.build(CYCLE_2)

        rows = read_csv(self.allocation)
        self.assertEqual({a["cycle"] for a in rows}, {"2026-09", "2026-10"}, "two runs, two cycles")
        self.assertEqual(self.cycle_lines("2026-09"), (header, sep), "prior cycle byte-identical, same order")
        self.assertEqual([a["cycle"] for a in rows], sorted(a["cycle"] for a in rows), "appended after it")
        oct_rows = self.cycle_rows("2026-10")
        self.assertTrue(oct_rows)
        self.assertIn(f"in 2 cycles ({len(sep)} rows from 1 prior cycles carried forward", second)
        self.assertIn(f"cycle 2026-10: {len(oct_rows)} rows written, 0 replaced", second)
        self.assertEqual(len(rows), len(sep) + len(oct_rows))
        self.assertEqual(len({(a["cycle"], a["request_id"]) for a in rows}), len(rows), "keyed on (cycle, request_id)")
        self.assertEqual(len({a["decided_at"] for a in oct_rows}), 1)
        self.assertTrue(all(a["decided_at"].startswith("2026-10-05T") for a in oct_rows), "decided_at is the build timestamp")
        self.assertLess(max(a["decided_at"] for a in self.cycle_rows("2026-09")), min(a["decided_at"] for a in oct_rows))

    def test_same_cycle_rerun_replaces_only_that_cycles_rows(self):
        self.build(CYCLE_1)
        self.build(CYCLE_2)
        sep = self.cycle_lines("2026-09")
        oct_before = self.cycle_rows("2026-10")
        # a request live in both cycles is closed before the October rerun: it
        # leaves October's allocation and stays in September's as filed
        closed = next(a["request_id"] for a in oct_before if a["allocated_to"])
        self.assertIn(closed, {a["request_id"] for a in self.cycle_rows("2026-09")})
        requests = read_csv(self.requests)
        next(r for r in requests if r["request_id"] == closed)["status_as_filed"] = "Closed - lost"
        write_csv(self.requests, requests)

        out = self.build(CYCLE_2)

        rows = read_csv(self.allocation)
        self.assertEqual({a["cycle"] for a in rows}, {"2026-09", "2026-10"}, "still two cycles")
        self.assertEqual(self.cycle_lines("2026-09"), sep, "September untouched")
        oct_after = self.cycle_rows("2026-10")
        self.assertEqual(len(oct_after), len(oct_before) - 1)
        self.assertNotIn(closed, {a["request_id"] for a in oct_after})
        self.assertIn(closed, {a["request_id"] for a in self.cycle_rows("2026-09")})
        self.assertIn(f"cycle 2026-10: {len(oct_after)} rows written, {len(oct_before)} replaced", out)
        self.assertIn(f"{len(sep[1])} rows from 1 prior cycles carried forward", out)
        self.assertEqual(len({a["decided_at"] for a in oct_after}), 1, "one decided_at per run")
        self.assertGreaterEqual(min(a["decided_at"] for a in oct_after), max(a["decided_at"] for a in oct_before))
        self.assertEqual(len({(a["cycle"], a["request_id"]) for a in rows}), len(rows))

    def test_an_ask_with_no_outcome_is_flagged_next_cycle_not_reallocated(self):
        self.build(CYCLE_1)
        sep = self.cycle_rows("2026-09")
        proposed = [a for a in sep if a["allocated_to"]]
        self.assertTrue(proposed)
        asked = {o["request_id"] for o in read_csv(self.root / "dataset" / "intro_outcomes.csv")}
        self.assertFalse({a["request_id"] for a in proposed} & asked, "nothing proposed in September was ever logged as asked")

        self.build(CYCLE_2)

        oct_by_rid = {a["request_id"]: a for a in self.cycle_rows("2026-10")}
        oct_pairs = {(a["allocated_to"], a["company_id"]) for a in oct_by_rid.values() if a["allocated_to"]}
        sep_pairs = {(a["allocated_to"], a["company_id"]) for a in proposed}
        self.assertEqual(sep_pairs & oct_pairs, set(), "no (connector, company) September proposed is proposed again")
        for a in proposed:
            with self.subTest(request_id=a["request_id"]):
                again = oct_by_rid[a["request_id"]]
                self.assertEqual(again["allocated_to"], "", "not silently re-allocated")
                self.assertEqual(again["batch_id"], "")
                self.assertEqual(again["exception_reason"], f"{STALE_ASK}: {a['allocated_to']} in 2026-09")
                self.assertTrue(again["best_path_if_unbudgeted"], "the path it would take is still named")
        # another request to a company a connector was already proposed is flagged too, naming them
        for again in oct_by_rid.values():
            if again["exception_reason"].startswith(STALE_ASK) and again["request_id"] not in {p["request_id"] for p in proposed}:
                connector, cycle = again["exception_reason"][len(STALE_ASK) + 2:].rsplit(" in ", 1)
                self.assertEqual(cycle, "2026-09")
                self.assertIn((connector, again["company_id"]), sep_pairs, again["request_id"])
        self.assertEqual(sep, self.cycle_rows("2026-09"), "the September proposal stands as filed")
        # the headroom the flagged asks leave goes to requests September could not place
        newly = [a for a in oct_by_rid.values() if a["allocated_to"] and a["request_id"] not in {p["request_id"] for p in proposed}]
        self.assertTrue(newly, "October still allocates something")


def completion(action: str, key: str, day: str, connector: str = "", who: str = "vera", **more) -> dict:
    """A row as the dashboard posts it: completion_id = <request_id or company_id>:<action>:<date>."""
    row = {c: "" for c in COMPLETION_COLUMNS}
    row.update({"completion_id": f"{key}:{action}:{day}", "completed_at": f"{day}T10:15:00+00:00",
                "completed_by": who, "action": action, "connector": connector,
                "company_id" if action == bg.CRM_CREATED else "request_id": key})
    row.update(more)
    return row


class FakeSupabase:
    """Stands in for urllib.request.urlopen: serves `table` a page at a time,
    honouring the Range header, and records every request it saw."""

    def __init__(self, table: list[dict]):
        self.table, self.requests = table, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        start, end = (int(x) for x in req.get_header("Range").split("-"))
        body = json.dumps(self.table[start:end + 1]).encode("utf-8")
        return io.BytesIO(body)


class CompletionsTest(ScratchRootTest):
    """5. golden/completions.csv, the third fact source."""

    def setUp(self):
        super().setUp()
        self.build(CYCLE_1)
        self.first = self.cycle_rows("2026-09")
        # a request September allocated, and the connector it went to
        self.target = next(a for a in self.first if a["allocated_to"])
        self.rid, self.connector = self.target["request_id"], self.target["allocated_to"]
        self.day = "2026-09-06"
        self.ask = completion(ASKED, self.rid, self.day, self.connector, note="asked in Slack")

    def write_completions(self, rows: list[dict], path: Path | None = None) -> Path:
        path = path or self.completions
        write_csv(path, rows)
        return path

    def test_a_completion_drops_its_request_from_the_next_allocation(self):
        dataset_before = tree_digest(self.root / "dataset")
        self.write_completions([self.ask])

        out = self.build(CYCLE_1)

        self.assertIn("completions.csv       1 rows applied: 1 ask_sent", out)
        again = {a["request_id"] for a in self.cycle_rows("2026-09")}
        self.assertNotIn(self.rid, again, "asked, so no longer live for allocation")
        self.assertEqual(len(again), len(self.first) - 1, "only the asked request left the cycle")
        row = self.by_id()[self.rid]
        self.assertEqual((row["routed_to"], row["asked_date"], row["responded"], row["intro_sent"]),
                         (self.connector, self.day, "N", "N"), "the ask is filed on the request, nothing back yet")
        self.assertEqual(tree_digest(self.root / "dataset"), dataset_before, "dataset/ is still never written")
        # the next cycle has no row for it either (asked, so not live), so it is
        # never flagged as a proposal with no outcome
        self.build(CYCLE_2)
        self.assertNotIn(self.rid, {a["request_id"] for a in self.cycle_rows("2026-10")})
        self.assertEqual(self.by_id()[self.rid]["asked_date"], self.day, "still filed")

    def test_the_same_completion_id_twice_is_one_completion(self):
        # once inside the file: two rows, one id
        self.write_completions([self.ask, dict(self.ask, completed_by="someone else", note="ticked again")])
        out = self.build(CYCLE_1)
        self.assertIn("completions.csv       1 rows applied: 1 ask_sent", out)
        requests_bytes, alloc_bytes = self.requests.read_bytes(), self.allocation.read_bytes()
        self.assertEqual(self.by_id()[self.rid]["asked_date"], self.day)

        # and once across runs: --apply of the same rows again adds nothing and changes nothing
        again = self.write_completions([self.ask], self.root / "again.csv")
        out = self.build(CYCLE_1, "--apply", str(again))
        self.assertIn("completions.csv       0 rows added from again.csv, 2 on file", out)
        self.assertEqual(self.requests.read_bytes(), requests_bytes)
        self.assertEqual(self.allocation.read_bytes(), alloc_bytes)
        self.assertEqual(len(read_csv(self.completions)), 2, "the file keeps what it had, nothing appended")

    def test_apply_merges_a_file_by_hand(self):
        nudge = completion(NUDGED, self.first[1]["request_id"], self.day, self.first[1]["allocated_to"] or "Marcus Aldridge")
        by_hand = self.write_completions([nudge], self.root / "by_hand.csv")
        self.assertFalse(self.completions.exists())

        out = self.build(CYCLE_1, "--apply", str(by_hand))

        self.assertIn("completions.csv       1 rows added from by_hand.csv, 1 on file", out)
        self.assertEqual([r["completion_id"] for r in read_csv(self.completions)], [nudge["completion_id"]])
        self.assertEqual(list(read_csv(self.completions)[0]), COMPLETION_COLUMNS)
        self.assertEqual(self.by_id()[nudge["request_id"]]["nudged_on"], self.day)
        self.assertIn(nudge["request_id"], {a["request_id"] for a in self.cycle_rows("2026-09")},
                      "a nudge does not spend the request: it is still live")
        proc = self.run_build("--apply", str(self.root / "missing.csv"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no such file", proc.stderr)

    def test_frozen_facts_never_move(self):
        crm_id = self.by_id()[self.rid]["company_id"]
        self.write_completions([
            self.ask,
            completion(NUDGED, self.first[1]["request_id"], self.day, self.first[1]["allocated_to"] or "Marcus Aldridge"),
            completion(bg.CRM_CREATED, crm_id, self.day),
        ])
        before = self.by_id()

        self.build(CYCLE_1)
        self.build(CYCLE_2)
        after = self.by_id()

        self.assertEqual(set(after), set(before), "no request appears or disappears")
        for rid, row in before.items():
            for fact in FACT_COLUMNS:
                self.assertEqual(after[rid][fact], row[fact], f"{rid} {fact}")

    def test_a_bad_row_fails_the_build_before_anything_is_written(self):
        digest = tree_digest(self.root / "golden")
        self.write_completions([dict(self.ask, action="asked")])
        proc = self.run_build("--as-of", CYCLE_1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("action 'asked' is not one of ask_sent, nudged, account_created", proc.stderr)
        self.assertIn("nothing written", proc.stderr)
        self.completions.unlink()
        self.assertEqual(tree_digest(self.root / "golden"), digest, "no golden file moved")

    # -- the Supabase read, without the network ------------------------------
    def supabase_rows(self) -> list[dict]:
        """Rows as PostgREST returns them: timestamptz, JSON null for the empty optionals."""
        return [
            {"completion_id": self.ask["completion_id"], "completed_at": f"{self.day}T10:15:00.123456+00:00",
             "completed_by": "vera", "action": ASKED, "request_id": self.rid, "company_id": None,
             "connector": self.connector, "note": None},
            {"completion_id": f"{self.first[1]['request_id']}:nudged:{self.day}", "completed_at": f"{self.day}T11:00:00+00:00",
             "completed_by": "vera", "action": NUDGED, "request_id": self.first[1]["request_id"], "company_id": None,
             "connector": self.first[1]["allocated_to"] or "Marcus Aldridge", "note": "pinged"},
        ]

    def test_supabase_read_is_paged_with_the_service_key_and_never_the_network(self):
        table = [dict(self.supabase_rows()[0], completion_id=f"R{i:04d}:ask_sent:{self.day}", request_id=f"R{i:04d}")
                 for i in range(bg.SUPABASE_PAGE + 3)]
        fake = FakeSupabase(table)

        rows = bg.fetch_supabase_completions("https://x.supabase.co/rest/v1/", "service-key", opener=fake)

        self.assertEqual(rows, table)
        self.assertEqual(len(fake.requests), 2, "1003 rows is two pages")
        req = fake.requests[0]
        self.assertTrue(req.full_url.startswith("https://x.supabase.co/rest/v1/completions?select=*"), req.full_url)
        self.assertEqual(req.get_header("Apikey"), "service-key")
        self.assertEqual(req.get_header("Authorization"), "Bearer service-key")
        self.assertEqual([r.get_header("Range") for r in fake.requests], ["0-999", "1000-1999"])
        self.assertEqual(bg.supabase_rest("https://x.supabase.co"), "https://x.supabase.co/rest/v1")

    def test_completions_supabase_writes_the_csv_then_the_build_reads_it(self):
        table = self.supabase_rows()
        fetched = []

        def fetch(url, key):
            fetched.append((url, key))
            return table

        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "service-key"}), \
                redirect_stdout(io.StringIO()) as out:
            bg.pull_completions("supabase", None, self.completions, fetch=fetch)
        self.assertEqual(fetched, [("https://x.supabase.co", "service-key")])
        self.assertIn("2 rows added from supabase (2 in the table), 2 on file", out.getvalue())
        on_file = read_csv(self.completions)
        self.assertEqual([r["completion_id"] for r in on_file], [r["completion_id"] for r in table], "oldest first")
        self.assertEqual(on_file[0]["company_id"], "", "JSON null lands as an empty cell")
        self.assertEqual(on_file[0]["completed_at"], f"{self.day}T10:15:00.123456+00:00", "the timestamp is kept as sent")
        csv_bytes = self.completions.read_bytes()

        # the build itself is offline: the same table again is a no-op, and the CSV drives the build
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "service-key"}), \
                redirect_stdout(io.StringIO()) as out:
            bg.pull_completions("supabase", None, self.completions, fetch=fetch)
        self.assertIn("0 rows added from supabase (2 in the table), 2 on file", out.getvalue())
        self.assertEqual(self.completions.read_bytes(), csv_bytes)
        out = self.build(CYCLE_1)
        self.assertIn("completions.csv       2 rows applied: 1 ask_sent, 1 nudged", out)
        self.assertNotIn(self.rid, {a["request_id"] for a in self.cycle_rows("2026-09")})
        self.assertEqual(self.by_id()[self.rid]["asked_date"], self.day, "the date part of the timestamptz")

    def test_a_bad_supabase_row_leaves_the_csv_alone(self):
        self.write_completions([self.ask])
        csv_bytes = self.completions.read_bytes()
        table = self.supabase_rows() + [dict(self.supabase_rows()[0], completion_id="R0001:asked:x", action="asked")]
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"}), \
                self.assertRaises(SystemExit) as died:
            bg.pull_completions("supabase", None, self.completions, fetch=lambda url, key: table)
        self.assertIn("action 'asked' is not one of", str(died.exception))
        self.assertIn("completions.csv not touched", str(died.exception))
        self.assertEqual(self.completions.read_bytes(), csv_bytes)

    def test_completions_supabase_without_credentials_stops_before_the_network(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SUPABASE_")}
        env["PATH"] = os.environ.get("PATH", "")
        proc = self.run_build("--completions", "supabase", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("needs SUPABASE_URL and SUPABASE_SERVICE_KEY", proc.stderr)
        self.assertFalse(self.completions.exists())
        # an unreadable table is one message and the manual path is named
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"}), \
                self.assertRaises(SystemExit) as died:
            bg.pull_completions("supabase", None, self.completions, fetch=lambda url, key: (_ for _ in ()).throw(OSError("no route")))
        self.assertIn("could not read the Supabase completions table: no route", str(died.exception))
        self.assertIn("--apply FILE", str(died.exception))


if __name__ == "__main__":
    unittest.main()
