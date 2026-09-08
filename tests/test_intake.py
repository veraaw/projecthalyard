"""golden/intake.py: more live data, layered over dataset/ without touching it.

    python3 -m unittest tests.test_intake

Every test works in a scratch copy of dataset/ with its own intake/ ledger and
golden/current/, so nothing here writes into the repository. What is checked:

  1. the two readers: a CSV (BOM, CRLF, short rows) and a Slack export (JSONL,
     a JSON array, one object, {"threads": [...]}) parse; a header with a
     repeated name, a row wider than the header, a thread without request_id
     or messages, a message without ts/user/text are refused whole.
  2. the merge rules the preview reports: a key not on file is a new row, a key
     on file is overridden only where the upload has a non-empty differing
     cell (each one listed), columns the file lacks are added blank on old
     rows, a key repeated in one upload is counted and the last row wins, a
     thread on file gains only the messages it does not have yet.
  3. preview() writes nothing; add() writes the upload byte for byte and one
     ledger row; the same content twice is one upload; an upload that cannot be
     applied leaves no trace.
  4. materialize(): a file no upload touches is a byte-for-byte copy of the
     export, a touched file keeps its line ending and gains the rows in ledger
     order, a new connections_<surname>.csv appears, a stale file goes, the
     result is idempotent, and it refuses to write anywhere under dataset/.
  5. the Supabase read: rows land through the same add(), a row that cannot be
     applied is set aside in rejected.csv with the reason and the rest still
     land; no network (the fetch is a fake).
  6. the browser makes the same guess at the target, computes the same
     upload_id and shows the same summary (tests/lp_parity.js under node).
  7. build_golden.py after an accepted upload: the new request and the new
     Slack thread are in golden_requests.csv, dataset/ is byte-identical.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from golden import intake  # noqa: E402

NODE = shutil.which("node")

REQUEST_COLUMNS = ["request_id", "target_company_raw", "target_title_raw", "requested_by", "request_date", "raw_ask"]


def tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def csv_text(columns: list[str], rows: list[list[str]], eol: str = "\r\n") -> str:
    out = StringIO()
    csv.writer(out, lineterminator=eol).writerows([columns, *rows])
    return out.getvalue()


def thread(rid: str, *texts: str, channel: str = "#intros", **extra) -> dict:
    return {"request_id": rid, "channel": channel, **extra,
            "messages": [{"ts": f"2026-09-0{i + 1}T09:00:00Z", "user": "priya", "text": t} for i, t in enumerate(texts)]}


def jsonl(threads: list[dict]) -> str:
    return "".join(json.dumps(t) + "\n" for t in threads)


class ScratchTest(unittest.TestCase):
    """A copy of dataset/ plus an empty intake/ and golden/current/ of its own."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="halyard-intake-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.dataset = self.root / "dataset"
        shutil.copytree(ROOT / "dataset", self.dataset)
        self.files = self.root / "intake" / "files"
        self.ledger = self.root / "intake" / "uploads.csv"
        self.rejected = self.root / "intake" / "rejected.csv"
        self.current = self.root / "golden" / "current"
        self.before = tree_digest(self.dataset)
        self.requests_cols, self.requests = intake.read_csv_file(self.dataset / "intro_requests.csv")
        self.threads = intake.read_threads(self.dataset / "slack_threads.jsonl")

    def tearDown(self):
        self.assertEqual(tree_digest(self.dataset), self.before, "dataset/ was written")

    def kw(self) -> dict:
        return {"base": self.dataset, "files": self.files, "path": self.ledger}

    def preview(self, target: str, content: str) -> dict:
        return intake.preview(target, content, **self.kw())

    def add(self, target: str, content: str, **more):
        return intake.add(target, content, "tester", **more, **self.kw())

    def materialize(self) -> dict[str, int]:
        return intake.materialize(self.dataset, self.current, self.files, self.ledger)

    def request_row(self, rid: str, company: str, **cells: str) -> list[str]:
        r = {"request_id": rid, "target_company_raw": company, "target_title_raw": "CTO", "requested_by": "Live Router",
             "request_date": "2026-09-06", "raw_ask": f"intro to {company} please", **cells}
        return [r[c] for c in REQUEST_COLUMNS]

    def requests_upload(self, *rows: list[str], columns: list[str] | None = None, eol: str = "\r\n") -> str:
        return csv_text(columns or REQUEST_COLUMNS, list(rows), eol)


class ParseCsvTest(unittest.TestCase):
    def test_bom_crlf_and_short_rows(self):
        cols, rows = intake.parse_csv("\ufeffa,b,c\r\n1,2,3\r\n4,5\r\n\r\n")
        self.assertEqual(cols, ["a", "b", "c"])
        self.assertEqual(rows, [{"a": "1", "b": "2", "c": "3"}, {"a": "4", "b": "5", "c": ""}])

    def test_quoted_cells(self):
        cols, rows = intake.parse_csv('a,b\n"x, y","say ""hi""\nthere"\n')
        self.assertEqual(rows, [{"a": "x, y", "b": 'say "hi"\nthere'}])

    def test_refused(self):
        for text, why in [("", "no header"), ("\r\n\r\n", "no header"), ("a,,c\n1,2,3\n", "blank"),
                          ("a,b,a\n1,2,3\n", "repeated"), ("a,b\n1,2,3\n", "3 cells")]:
            with self.assertRaises(ValueError, msg=text) as cm:
                intake.parse_csv(text)
            self.assertIn(why, str(cm.exception))


class ParseThreadsTest(unittest.TestCase):
    def test_every_shape(self):
        t = thread("R1", "hello")
        for text in (json.dumps(t) + "\n", json.dumps([t]), json.dumps({"threads": [t]}), "\ufeff" + json.dumps(t),
                     jsonl([t]).replace("\n", "\r\n")):
            self.assertEqual(intake.parse_threads(text), [t], text)

    def test_refused(self):
        bad = [("", "empty"), ("   \n", "empty"), ("[]", "no threads"), ('{"threads": []}', "no threads"),
               ('{"a": 1}\nnot json\n', "line 2"), (json.dumps({"messages": [{"ts": "t", "user": "u", "text": "x"}]}), "request_id"),
               (json.dumps({"request_id": " ", "messages": [{"ts": "t", "user": "u", "text": "x"}]}), "request_id"),
               (json.dumps({"request_id": "R1", "messages": []}), "messages"), (json.dumps({"request_id": "R1"}), "messages"),
               (json.dumps({"request_id": "R1", "messages": [{"ts": "t", "user": "u"}]}), "ts, user and text"),
               (json.dumps({"request_id": "R1", "messages": [{"ts": 1, "user": "u", "text": "x"}]}), "ts, user and text")]
        for text, why in bad:
            with self.assertRaises(ValueError, msg=text) as cm:
                intake.parse_threads(text)
            self.assertIn(why, str(cm.exception))


class MergeCsvTest(unittest.TestCase):
    BASE_COLS = ["request_id", "company", "title"]
    BASE = [{"request_id": "R1", "company": "Acme", "title": "CTO"}, {"request_id": "R2", "company": "Bolt", "title": "CFO"}]

    def merge(self, cols, rows):
        return intake.merge_csv(self.BASE_COLS, self.BASE, cols, rows, ["request_id"])

    def test_new_rows_appended_in_upload_order(self):
        cols, rows, s = self.merge(["request_id", "company"], [{"request_id": "R9", "company": "Zed"}, {"request_id": "R3", "company": "Cog"}])
        self.assertEqual(cols, self.BASE_COLS)
        self.assertEqual([r["request_id"] for r in rows], ["R1", "R2", "R9", "R3"])
        self.assertEqual(rows[2], {"request_id": "R9", "company": "Zed", "title": ""})
        self.assertEqual((s["rows"], s["new_rows"], s["changed_rows"], s["unchanged_rows"], s["duplicate_keys"]), (2, 2, 0, 0, 0))
        self.assertEqual(s["sample"], rows[2:])

    def test_override_only_non_empty_differing_cells(self):
        cols, rows, s = self.merge(self.BASE_COLS, [{"request_id": "R1", "company": "", "title": "CEO"},
                                                    {"request_id": "R2", "company": "Bolt", "title": "CFO"}])
        self.assertEqual(rows[0], {"request_id": "R1", "company": "Acme", "title": "CEO"})
        self.assertEqual(rows[1], self.BASE[1])
        self.assertEqual(s["changes"], [{"key": "R1", "column": "title", "from": "CTO", "to": "CEO"}])
        self.assertEqual((s["new_rows"], s["changed_rows"], s["unchanged_rows"]), (0, 1, 1))
        self.assertEqual(self.BASE[0]["title"], "CTO", "merge_csv mutated its input")

    def test_new_columns_blank_on_old_rows(self):
        cols, rows, s = self.merge(["request_id", "stage", "company"], [{"request_id": "R2", "stage": "warm", "company": ""},
                                                                        {"request_id": "R3", "stage": "cold", "company": "Cog"}])
        self.assertEqual(cols, ["request_id", "company", "title", "stage"])
        self.assertEqual(s["new_columns"], ["stage"])
        self.assertEqual(rows[0]["stage"], "")
        self.assertEqual(rows[1]["stage"], "warm")
        self.assertEqual(s["changes"], [{"key": "R2", "column": "stage", "from": "", "to": "warm"}])
        self.assertEqual(rows[2], {"request_id": "R3", "company": "Cog", "title": "", "stage": "cold"})

    def test_repeated_key_in_one_upload_last_wins(self):
        _, rows, s = self.merge(["request_id", "company"], [{"request_id": "R7", "company": "One"}, {"request_id": "R7", "company": "Two"}])
        self.assertEqual(rows[-1]["company"], "Two")
        self.assertEqual((len(rows), s["new_rows"], s["duplicate_keys"], s["unchanged_rows"]), (3, 1, 1, 0))
        # settled within the upload: nothing on file was replaced
        self.assertEqual((s["changes"], s["changed_rows"]), ([], 0))

    def test_repeated_key_on_file_reports_one_override_per_cell(self):
        _, rows, s = self.merge(["request_id", "company"], [{"request_id": "R1", "company": "Ant"}, {"request_id": "R1", "company": "Bee"}])
        self.assertEqual(rows[0]["company"], "Bee")
        self.assertEqual(s["changes"], [{"key": "R1", "column": "company", "from": "Acme", "to": "Ant"},
                                        {"key": "R1", "column": "company", "from": "Ant", "to": "Bee"}])
        self.assertEqual((s["changed_rows"], s["duplicate_keys"], s["unchanged_rows"]), (1, 1, 0))

    def test_composite_key(self):
        cols, rows, s = intake.merge_csv(["name", "company", "title"], [{"name": "A", "company": "X", "title": "t"}],
                                         ["name", "company", "title"], [{"name": "A", "company": "Y", "title": "u"}], ["name", "company"])
        self.assertEqual(len(rows), 2)
        self.assertEqual((s["new_rows"], s["sample"][0]["company"]), (1, "Y"))

    def test_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.merge(["company"], [{"company": "x"}])
        self.assertIn("request_id", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            self.merge(["request_id", "company"], [{"request_id": "R1", "company": "x"}, {"request_id": " ", "company": "y"}])
        self.assertEqual(str(cm.exception), "line 3: empty request_id")


class MergeThreadsTest(unittest.TestCase):
    def setUp(self):
        self.base = [thread("R1", "intro to Acme?", "on it"), thread("R2", "Bolt CFO please")]

    def test_new_and_extended_threads(self):
        up = [json.loads(json.dumps(self.base[0])), thread("R3", "Cog anyone?")]
        up[0]["messages"] = up[0]["messages"][1:] + [{"ts": "2026-09-03T09:00:00Z", "user": "priya", "text": "done - sent"}]
        threads, s = intake.merge_threads(self.base, up)
        self.assertEqual([t["request_id"] for t in threads], ["R1", "R2", "R3"])
        self.assertEqual([m["text"] for m in threads[0]["messages"]], ["intro to Acme?", "on it", "done - sent"])
        self.assertEqual((s["rows"], s["new_rows"], s["extended_threads"], s["new_messages"], s["changed_rows"], s["unchanged_rows"]),
                         (2, 1, 1, 1, 0, 0))
        self.assertEqual(s["sample"][0]["request_id"], "R3")
        self.assertEqual(s["sample"][0]["replies"], 0)
        self.assertEqual(len(self.base[0]["messages"]), 2, "merge_threads mutated its input")

    def test_same_messages_again_change_nothing(self):
        threads, s = intake.merge_threads(self.base, [json.loads(json.dumps(self.base[1]))])
        self.assertEqual(threads, self.base)
        self.assertEqual((s["new_rows"], s["extended_threads"], s["new_messages"], s["unchanged_rows"]), (0, 0, 0, 1))

    def test_field_override_and_new_field(self):
        threads, s = intake.merge_threads(self.base, [thread("R2", "Bolt CFO please", channel="#deals", priority="high"),
                                                      thread("R2", "Bolt CFO please", channel="#deals")])
        self.assertEqual(threads[1]["channel"], "#deals")
        self.assertEqual(threads[1]["priority"], "high")
        self.assertEqual(s["changes"], [{"key": "R2", "column": "channel", "from": "#intros", "to": "#deals"},
                                        {"key": "R2", "column": "priority", "from": "", "to": "high"}])
        self.assertEqual((s["changed_rows"], s["duplicate_keys"], s["new_columns"], s["unchanged_rows"]), (1, 1, ["priority"], 1))


class GuessTargetTest(unittest.TestCase):
    FILES = {"intro_requests.csv": REQUEST_COLUMNS, "intro_outcomes.csv": ["request_id", "outcome", "logged_by"],
             "crm_accounts.csv": ["account_id", "name"], "connector_roster.csv": ["name", "connections_file"],
             "investor_network.csv": ["person", "fund", "portfolio_company", "prior_employer"],
             "connections_trask.csv": ["name", "company", "title"], "connections_duvall.csv": ["name", "company", "title"],
             "slack_threads.jsonl": []}

    def guess(self, filename, columns):
        return intake.guess_target(filename, columns, self.FILES)

    def test_guesses(self):
        self.assertEqual(self.guess("threads.json", None), ("slack_threads.jsonl", "Slack threads"))
        self.assertEqual(self.guess("intro_requests.csv", REQUEST_COLUMNS)[0], "intro_requests.csv")
        self.assertEqual(self.guess("export (3).csv", REQUEST_COLUMNS[:2] + ["raw_ask"])[0], "intro_requests.csv")
        self.assertEqual(self.guess("x.csv", ["request_id", "outcome"])[0], "intro_outcomes.csv")
        self.assertEqual(self.guess("x.csv", ["request_id"]), ("", "could be intro_requests.csv or intro_outcomes.csv: pick one"))
        self.assertEqual(self.guess("Connections - Trask.csv", ["name", "company", "title"]), ("connections_trask.csv", "same file name"))
        self.assertEqual(self.guess("connections_new_guy.csv", ["name", "company"])[0], "connections_new_guy.csv")
        self.assertEqual(self.guess("Okonkwo.csv", ["name", "company", "title"])[0], "connections_okonkwo.csv")
        self.assertEqual(self.guess("Connections.csv", ["name", "company"])[0], "")
        self.assertEqual(self.guess("roster.csv", ["name", "connections_file"])[0], "connector_roster.csv")
        self.assertEqual(self.guess("x.csv", ["nothing", "here"]), ("", "no file on record has these columns"))

    def test_target_problem(self):
        self.assertIsNone(intake.target_problem("connections_new_guy.csv"))
        self.assertIsNone(intake.target_problem("slack_threads.jsonl"))
        for bad in ("", "../intro_requests.csv", "dataset/intro_requests.csv", ".hidden.csv", "notes.csv", "connections_Trask.csv"):
            self.assertIsNotNone(intake.target_problem(bad), bad)


class UploadIdTest(unittest.TestCase):
    def test_fnv1a_reference_values(self):
        self.assertEqual(intake.fnv1a(""), "cbf29ce484222325")
        self.assertEqual(intake.fnv1a("a"), "af63dc4c8601ec8c")
        self.assertEqual(intake.fnv1a("foobar"), "85944171f73967e8")

    def test_bom_and_target_stem(self):
        self.assertEqual(intake.upload_id("intro_requests.csv", "a,b\n"), intake.upload_id("intro_requests.csv", "\ufeffa,b\n"))
        self.assertTrue(intake.upload_id("slack_threads.jsonl", "{}").startswith("slack_threads-"))
        self.assertNotEqual(intake.upload_id("intro_requests.csv", "a,b\r\n"), intake.upload_id("intro_requests.csv", "a,b\n"))

    def test_generation_suffix_after_a_revert(self):
        self.assertEqual(intake.upload_id("intro_requests.csv", "a,b\n", 0), intake.upload_id("intro_requests.csv", "a,b\n"))
        self.assertEqual(intake.upload_id("intro_requests.csv", "a,b\n", 2), intake.upload_id("intro_requests.csv", "a,b\n") + "-g2")
        self.assertEqual(intake.revert_id("2026-09-07T12:00:00Z"), "revert-" + intake.fnv1a("2026-09-07T12:00:00Z"))


class PreviewAndAcceptTest(ScratchTest):
    def test_preview_writes_nothing(self):
        s = self.preview("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems")))
        self.assertEqual((s["rows"], s["new_rows"], s["changed_rows"], s["target"], s["new_file"]), (1, 1, 0, "intro_requests.csv", False))
        self.assertFalse((self.root / "intake").exists())
        self.assertFalse(self.current.exists())

    def test_preview_against_what_was_already_accepted(self):
        self.add("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems")))
        s = self.preview("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems", target_title_raw="CDO")))
        self.assertEqual((s["new_rows"], s["changed_rows"]), (0, 1))
        self.assertEqual(s["changes"], [{"key": "R9001", "column": "target_title_raw", "from": "CTO", "to": "CDO"}])

    def test_preview_of_a_refresh_of_the_whole_file(self):
        rows = [[r[c] for c in self.requests_cols] for r in self.requests]
        rows[3][self.requests_cols.index("requested_by")] = "Someone Else"
        rows.append([{"request_id": "R9002", "target_company_raw": "Halcyon Bio"}.get(c, "") for c in self.requests_cols])
        s = self.preview("intro_requests.csv", csv_text(self.requests_cols, rows))
        self.assertEqual((s["rows"], s["new_rows"], s["changed_rows"], s["unchanged_rows"]), (201, 1, 1, 199))
        self.assertEqual(s["changes"][0]["column"], "requested_by")

    def test_accept_writes_upload_verbatim_and_one_ledger_row(self):
        text = "\ufeff" + self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        row, s = self.add("intro_requests.csv", text, filename="Intro Requests.csv", note="from Priya", at="2026-09-06T10:00:00Z")
        uid = intake.upload_id("intro_requests.csv", text)
        self.assertEqual(row["upload_id"], uid)
        self.assertEqual(intake.read_verbatim(self.files / f"{uid}.csv"), text)
        self.assertEqual(intake.ledger(self.ledger), [{
            "upload_id": uid, "received_at": "2026-09-06T10:00:00Z", "received_by": "tester", "target": "intro_requests.csv",
            "filename": "Intro Requests.csv", "rows": "1", "new_rows": "1", "changed_rows": "0", "new_columns": "", "note": "from Priya"}])
        self.assertIn(b"\r\n", self.ledger.read_bytes())

    def test_same_content_twice_is_one_upload(self):
        text = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        first, _ = self.add("intro_requests.csv", text)
        again, s = self.add("intro_requests.csv", "\ufeff" + text)
        self.assertIsNotNone(first)
        self.assertIsNone(again)
        self.assertEqual(s["new_rows"], 0, "the second preview is against the first upload applied")
        self.assertEqual(len(intake.ledger(self.ledger)), 1)
        self.assertEqual(len(list(self.files.iterdir())), 1)

    def test_unapplicable_upload_leaves_no_trace(self):
        for target, text in [("intro_requests.csv", "company,title\r\nAcme,CTO\r\n"), ("intro_requests.csv", ""),
                             ("notes.csv", "a\r\n1\r\n"), ("slack_threads.jsonl", "[]"), ("../x.csv", "a\r\n1\r\n")]:
            with self.assertRaises(ValueError, msg=target):
                self.add(target, text)
        self.assertFalse((self.root / "intake").exists())

    def test_missing_key_column_is_named(self):
        with self.assertRaises(ValueError) as cm:
            self.preview("investor_network.csv", "person,fund\r\nA,F\r\n")
        self.assertEqual(str(cm.exception), "no portfolio_company, prior_employer column")

    def test_new_connections_file(self):
        s = self.preview("connections_okonkwo.csv", "name,company,title\r\nA B,Acme,CTO\r\n")
        self.assertTrue(s["new_file"])
        self.assertEqual((s["new_rows"], s["new_columns"]), (1, ["name", "company", "title"]))


class RevertTest(ScratchTest):
    """"Revert to Sep Raw Data State": a ledger row after which no earlier upload applies."""

    def revert(self, at="2026-09-07T12:00:00Z", **more):
        return intake.revert("tester", at=at, path=self.ledger, **more)

    def test_revert_keeps_the_history_and_current_is_the_export_again(self):
        text = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        first, _ = self.add("intro_requests.csv", text)
        self.add("slack_threads.jsonl", jsonl([thread("R9001", "Vireo?")]))
        self.assertEqual(self.materialize(), {"intro_requests.csv": 1, "slack_threads.jsonl": 1})
        row = self.revert(note="bad export")
        self.assertEqual(row, {"upload_id": intake.revert_id("2026-09-07T12:00:00Z"), "received_at": "2026-09-07T12:00:00Z", "received_by": "tester",
                               "target": "revert", "filename": "", "rows": "", "new_rows": "", "changed_rows": "", "new_columns": "", "note": "bad export"})
        rows = intake.ledger(self.ledger)
        self.assertEqual([r["target"] for r in rows], ["intro_requests.csv", "slack_threads.jsonl", "revert"])
        self.assertEqual((intake.active(rows), intake.generation(rows)), ([], 1))
        self.assertEqual(len(list(self.files.iterdir())), 2, "the files stay")
        self.assertEqual(self.materialize(), {})
        self.assertEqual(tree_digest(self.current), self.before)
        self.assertEqual(intake.existing_targets(self.dataset, self.ledger), intake.existing_targets(self.dataset, self.root / "none.csv"))
        s = self.preview("intro_requests.csv", text)
        self.assertEqual((s["new_rows"], s["changed_rows"]), (1, 0), "the preview is against the export again")

    def test_same_file_accepted_again_after_a_revert_is_a_new_upload(self):
        text = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        first, _ = self.add("intro_requests.csv", text)
        self.revert()
        again, s = self.add("intro_requests.csv", text)
        self.assertEqual(again["upload_id"], first["upload_id"] + "-g1")
        self.assertEqual(s["new_rows"], 1)
        self.assertIsNone(self.add("intro_requests.csv", text)[0], "but twice in the same generation is once")
        self.assertEqual(self.materialize(), {"intro_requests.csv": 1})
        _, rows = intake.read_csv_file(self.current / "intro_requests.csv")
        self.assertEqual(rows[-1]["request_id"], "R9001")
        self.assertEqual(len(rows), len(self.requests) + 1)
        self.revert(at="2026-09-07T13:00:00Z")
        self.assertEqual(self.add("intro_requests.csv", text)[0]["upload_id"], first["upload_id"] + "-g2")

    def test_revert_is_idempotent_and_recorded_even_with_nothing_to_revert(self):
        self.assertIsNotNone(self.revert())
        self.assertIsNone(self.revert(), "the same revert twice is one row")
        self.assertEqual(len(intake.ledger(self.ledger)), 1)
        self.assertEqual(self.materialize(), {})
        self.assertEqual(tree_digest(self.current), self.before)

    def test_revert_from_the_table(self):
        good = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        table = [{"upload_id": "u-1", "received_at": "2026-09-06 10:00:00+00", "received_by": "priya", "target": "intro_requests.csv",
                  "filename": "x.csv", "content": good, "rows": 1, "new_rows": 1, "changed_rows": 0, "new_columns": "", "note": None},
                 {"upload_id": "revert-abc", "received_at": "2026-09-06 11:00:00+00", "received_by": "priya", "target": "revert",
                  "filename": "", "content": "", "rows": None, "new_rows": None, "changed_rows": None, "new_columns": "", "note": "oops"},
                 {"upload_id": "u-1-g1", "received_at": "2026-09-06 12:00:00+00", "received_by": "priya", "target": "intro_requests.csv",
                  "filename": "x.csv", "content": good, "rows": 1, "new_rows": 1, "changed_rows": 0, "new_columns": "", "note": None}]
        added, already, rejected = intake.apply_table_rows(table, self.dataset, self.files, self.ledger, self.rejected)
        self.assertEqual((added, already, rejected), (3, 0, []))
        rows = intake.ledger(self.ledger)
        self.assertEqual([(r["upload_id"], r["target"], r["received_at"]) for r in rows],
                         [("u-1", "intro_requests.csv", "2026-09-06T10:00:00Z"), ("revert-abc", "revert", "2026-09-06T11:00:00Z"),
                          ("u-1-g1", "intro_requests.csv", "2026-09-06T12:00:00Z")])
        self.assertEqual([r["upload_id"] for r in intake.active(rows)], ["u-1-g1"])
        self.assertEqual(intake.apply_table_rows(table, self.dataset, self.files, self.ledger, self.rejected), (0, 3, []))
        self.assertEqual(self.materialize(), {"intro_requests.csv": 1})


class MaterializeTest(ScratchTest):
    def test_no_uploads_is_a_byte_copy(self):
        self.assertEqual(self.materialize(), {})
        self.assertEqual(tree_digest(self.current), self.before)

    def test_csv_upload_applied_with_the_files_line_ending(self):
        self.add("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems"), eol="\n"))
        self.add("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems", target_title_raw="CDO"),
                                                            self.request_row("R9002", "Halcyon Bio"), eol="\n"))
        applied = self.materialize()
        self.assertEqual(applied, {"intro_requests.csv": 2})
        cols, rows = intake.read_csv_file(self.current / "intro_requests.csv")
        self.assertEqual(cols, self.requests_cols)
        self.assertEqual(len(rows), len(self.requests) + 2)
        self.assertEqual(rows[:-2], self.requests)
        self.assertEqual((rows[-2]["request_id"], rows[-2]["target_title_raw"], rows[-1]["request_id"]), ("R9001", "CDO", "R9002"))
        text = self.current.joinpath("intro_requests.csv").read_bytes()
        self.assertIn(b"\r\n", text)
        self.assertNotIn(b"\n\n", text.replace(b"\r\n", b"\n") + b"x")
        untouched = {k: v for k, v in tree_digest(self.current).items() if k != "intro_requests.csv"}
        self.assertEqual(untouched, {k: v for k, v in self.before.items() if k != "intro_requests.csv"})

    def test_new_column_and_new_file_and_stale_file(self):
        self.add("crm_accounts.csv", "account_id,tier\r\nACC-NEW,gold\r\n")
        self.add("connections_okonkwo.csv", "name,company,title\r\nA B,Acme,CTO\r\n")
        self.materialize()
        cols, rows = intake.read_csv_file(self.current / "crm_accounts.csv")
        self.assertEqual(cols[-1], "tier")
        self.assertEqual(rows[-1]["account_id"], "ACC-NEW")
        self.assertTrue(all(r["tier"] == "" for r in rows[:-1]))
        self.assertEqual(intake.read_verbatim(self.current / "connections_okonkwo.csv"), "name,company,title\r\nA B,Acme,CTO\r\n")
        (self.current / "leftover.csv").write_text("x")
        self.materialize()
        self.assertFalse((self.current / "leftover.csv").exists())

    def test_slack_upload_new_and_extended(self):
        rid = self.threads[0]["request_id"]
        up = [thread(rid, "following up - any luck?"), thread("R9003", "anyone know someone at Cog Labs?", "I do", channel="#intros")]
        row, s = self.add("slack_threads.jsonl", json.dumps({"threads": up}), filename="slack.json")
        self.assertEqual((s["new_rows"], s["extended_threads"], s["new_messages"]), (1, 1, 1))
        self.assertEqual(self.materialize(), {"slack_threads.jsonl": 1})
        threads = intake.read_threads(self.current / "slack_threads.jsonl")
        self.assertEqual(len(threads), len(self.threads) + 1)
        self.assertEqual(threads[0]["messages"][-1]["text"], "following up - any luck?")
        self.assertEqual(threads[0]["messages"][:-1], self.threads[0]["messages"])
        self.assertEqual(threads[-1]["request_id"], "R9003")
        raw = self.current.joinpath("slack_threads.jsonl").read_bytes()
        self.assertEqual(raw.count(b"\n"), len(threads))
        self.assertNotIn(b"\r\n", raw)

    def test_idempotent(self):
        self.add("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems")))
        self.add("slack_threads.jsonl", jsonl([thread("R9001", "Vireo?")]))
        self.materialize()
        digest = tree_digest(self.current)
        self.materialize()
        self.assertEqual(tree_digest(self.current), digest)

    def test_refuses_to_write_under_dataset(self):
        with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
            intake.materialize(self.dataset, self.dataset / "current", self.files, self.ledger)
        with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
            intake.materialize(self.dataset, self.dataset, self.files, self.ledger)
        with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
            intake._write(intake.DATASET / "uploads.csv", intake.LEDGER_COLUMNS, [])
        self.assertFalse((intake.DATASET / "uploads.csv").exists())


class SupabaseRowsTest(ScratchTest):
    def table_row(self, uid, target, content, **more):
        return {"upload_id": uid, "received_at": "2026-09-06 10:00:00+00", "received_by": "priya", "target": target,
                "filename": "x", "content": content, "rows": 1, "new_rows": 1, "changed_rows": 0, "new_columns": "", "note": None, **more}

    def apply(self, rows):
        return intake.apply_table_rows(rows, self.dataset, self.files, self.ledger, self.rejected)

    def test_good_rows_land_bad_rows_are_set_aside(self):
        good = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        rows = [self.table_row("u-good", "intro_requests.csv", good),
                self.table_row("u-bad-key", "intro_requests.csv", "company\r\nAcme\r\n"),
                self.table_row("u-bad-target", "../secrets.csv", good),
                self.table_row("u bad id", "intro_requests.csv", good),
                self.table_row("u-slack", "slack_threads.jsonl", jsonl([thread("R9001", "Vireo?")])),
                self.table_row("", "intro_requests.csv", good)]
        added, already, rejected = self.apply(rows)
        self.assertEqual((added, already), (2, 0))
        self.assertEqual([(r["upload_id"], r["problem"]) for r in rejected],
                         [("u-bad-key", "no request_id column"), ("u-bad-target", "target '../secrets.csv' is not a plain file name"),
                          ("u bad id", "upload_id is not a plain token")])
        self.assertEqual([r["upload_id"] for r in intake.ledger(self.ledger)], ["u-good", "u-slack"])
        self.assertEqual(intake.ledger(self.ledger)[0]["received_at"], "2026-09-06T10:00:00Z")
        self.assertEqual([r["upload_id"] for r in intake._read(self.rejected)], ["u-bad-key", "u-bad-target", "u bad id"])
        added, already, rejected = self.apply(rows)
        self.assertEqual((added, already, rejected), (0, 5, []))
        self.assertEqual(len(intake._read(self.rejected)), 3)

    def test_fetch_pages_with_the_service_key(self):
        calls = []

        class Resp:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(self.body).encode()

        def opener(req, timeout):
            calls.append((req.full_url, req.get_header("Authorization"), req.get_header("Range")))
            start = int(req.get_header("Range").split("-")[0])
            n = intake.SUPABASE_PAGE if start == 0 else 3
            return Resp([{"upload_id": f"u{start + i}"} for i in range(n)])

        rows = intake.fetch_supabase_uploads("https://x.supabase.co", "service-key", opener)
        self.assertEqual(len(rows), intake.SUPABASE_PAGE + 3)
        self.assertEqual(calls[0][0], "https://x.supabase.co/rest/v1/intake_uploads?select=*&order=received_at.asc,upload_id.asc")
        self.assertEqual(calls[0][1], "Bearer service-key")
        self.assertEqual([c[2] for c in calls], [f"0-{intake.SUPABASE_PAGE - 1}", f"{intake.SUPABASE_PAGE}-{2 * intake.SUPABASE_PAGE - 1}"])

    def test_pull_goes_on_without_the_table_but_not_past_any_other_failure(self):
        def http(code):
            def fetch(url, key):
                raise urllib.error.HTTPError(url, code, "x", {}, None)
            return fetch

        env = {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"}
        with mock.patch.dict("os.environ", env), mock.patch.object(intake, "LEDGER", self.ledger), \
                redirect_stderr(StringIO()) as err:
            intake.pull("supabase", fetch=http(404))
        self.assertIn("no Supabase intake_uploads table yet", err.getvalue())
        self.assertIn("config/supabase_schema.sql", err.getvalue())
        for fetch in (http(401), lambda url, key: (_ for _ in ()).throw(OSError("no route"))):
            with mock.patch.dict("os.environ", env), self.assertRaises(SystemExit) as died:
                intake.pull("supabase", fetch=fetch)
            self.assertIn("could not read the Supabase intake_uploads table", str(died.exception))
            self.assertIn("--add FILE", str(died.exception))


@unittest.skipUnless(NODE, "node is not installed")
class BrowserParityTest(ScratchTest):
    """live_priorities.js sees what the tab's payload gives it and must show the same summary."""

    def payload(self) -> dict:
        self.materialize()
        files = {}
        for name in intake.existing_targets(self.dataset, self.ledger):
            src = self.current / name
            if intake.format_of(name) == "jsonl":
                files[name] = {"format": "jsonl", "keys": ["request_id"], "threads": intake.read_threads(src)}
            else:
                cols, rows = intake.read_csv_file(src)
                files[name] = {"format": "csv", "keys": intake.schema_of(name)["keys"], "columns": cols,
                               "rows": [[r.get(c, "") for c in cols] for r in rows]}
        rows = intake.ledger(self.ledger)
        return {"files": files, "schemas": [{"pattern": p, "keys": s["keys"], "family": bool(s.get("family")), "format": s.get("format", "csv")}
                                            for p, s in intake.SCHEMAS.items()],
                "ledger": rows, "ids": [r["upload_id"] for r in rows], "generation": intake.generation(rows), "rejected": []}

    def run_node(self, uploads: list[dict], at: str = "") -> dict:
        proc = subprocess.run([NODE, str(ROOT / "tests" / "lp_parity.js")],
                              input=json.dumps({"intake": {"payload": self.payload(), "uploads": uploads, "at": at}}),
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def python_side(self, filename: str, text: str, target: str = "") -> dict:
        columns = None
        body = text.lstrip("\ufeff").strip()
        if not filename.lower().endswith((".json", ".jsonl")) and not body.startswith(("{", "[")):
            try:
                columns = intake.parse_csv(text)[0]
            except ValueError:
                columns = []
        guess, why = intake.guess_target(filename, columns, intake.columns_on_file(**self.kw()))
        target = target or guess
        r = {"guess": guess, "why": why, "target": target,
             "upload_id": intake.upload_id(target, text, intake.generation(intake.ledger(self.ledger))) if target else ""}
        try:
            s = self.preview(target, text)
            r["summary"] = {k: s[k] for k in ("rows", "new_rows", "changed_rows", "unchanged_rows", "duplicate_keys", "new_columns", "changes",
                                              "columns", "extended_threads", "new_messages") if k in s}
        except ValueError as e:
            r["error"] = str(e)
        return r

    def test_same_guess_id_and_summary(self):
        rid = self.threads[0]["request_id"]
        self.add("intro_requests.csv", self.requests_upload(self.request_row("R9001", "Vireo Systems")))
        refresh = [[r[c] for c in self.requests_cols] for r in self.requests[:5]]
        refresh[2][self.requests_cols.index("requested_by")] = "Someone Else"
        uploads = [
            {"filename": "intro_requests (2).csv", "text": "\ufeff" + self.requests_upload(
                self.request_row("R9001", "Vireo Systems", target_title_raw="CDO"), self.request_row("R9002", "Halcyon Bio"),
                self.request_row("R9002", "Halcyon Bio", requested_by="Kim"))},
            {"filename": "refresh.csv", "text": csv_text(self.requests_cols, refresh, "\n")},
            {"filename": "crm.csv", "text": "account_id,tier\r\nACC-NEW,gold\r\n"},
            {"filename": "Connections - Okonkwo.csv", "text": 'name,company,title\r\n"Ada Okonkwo",Acme,CTO\r\n'},
            {"filename": "Connections.csv", "text": "name,company,title\r\nA,Acme,CTO\r\n"},
            {"filename": "Connections.csv", "text": "name,company,title\r\nA,Acme,CTO\r\n", "target": "connections_trask.csv"},
            {"filename": "slack.json", "text": json.dumps({"threads": [thread(rid, "following up?"), thread("R9003", "Cog Labs?", "I do", priority="high")]})},
            {"filename": "slack.jsonl", "text": jsonl([{**self.threads[0], "messages": self.threads[0]["messages"][:1]}])},
            {"filename": "bad.csv", "text": "company\r\nAcme\r\n", "target": "intro_requests.csv"},
            {"filename": "bad.json", "text": "{}"},
            {"filename": "wide.csv", "text": "request_id,company_as_written\r\nR1,Acme,extra\r\n", "target": "intro_requests.csv"},
        ]
        js = self.run_node(uploads)["intake"]
        for u, got in zip(uploads, js):
            want = self.python_side(u["filename"], u["text"], u.get("target", ""))
            if not want["target"]:  # each side words "pick a target" its own way
                self.assertIn("error", got)
                got.pop("error"), want.pop("error")
            self.assertEqual(got, want, u["filename"])
        self.assertEqual((js[0]["summary"]["changed_rows"], js[0]["summary"]["new_rows"], js[0]["summary"]["duplicate_keys"]), (1, 1, 1))
        self.assertEqual(js[3]["target"], "connections_okonkwo.csv")
        self.assertEqual(js[4]["target"], "")
        self.assertEqual(js[6]["summary"]["extended_threads"], 1)
        self.assertEqual(js[7]["summary"]["unchanged_rows"], 1)
        self.assertIn("error", js[8])
        self.assertIn("error", js[9])
        self.assertIn("error", js[10])

    def test_same_view_of_the_ledger_after_a_revert(self):
        text = self.requests_upload(self.request_row("R9001", "Vireo Systems"))
        self.add("intro_requests.csv", text)
        self.add("slack_threads.jsonl", jsonl([thread("R9001", "Vireo?")]))
        intake.revert("tester", at="2026-09-07T12:00:00Z", path=self.ledger)
        after, _ = self.add("crm_accounts.csv", "account_id,tier\r\nACC-NEW,gold\r\n")
        uploads = [{"filename": "intro_requests.csv", "text": text}]
        js = self.run_node(uploads, at="2026-09-07T12:00:00Z")
        rows = intake.ledger(self.ledger)
        self.assertEqual(js["ledger"], {"active": [r["upload_id"] for r in intake.active(rows)], "revert_id": intake.revert_id("2026-09-07T12:00:00Z")})
        self.assertEqual(js["ledger"]["active"], [after["upload_id"]])
        want = self.python_side("intro_requests.csv", text)
        self.assertEqual(js["intake"][0], want)
        self.assertTrue(want["upload_id"].endswith("-g1"))
        self.assertEqual((want["summary"]["new_rows"], want["summary"]["changed_rows"]), (1, 0), "previewed against the export again")


class RebuildWithUploadsTest(unittest.TestCase):
    """golden/build_golden.py in a scratch root, after one CSV and one Slack upload were accepted."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="halyard-intake-build-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copytree(ROOT / "dataset", self.root / "dataset")
        (self.root / "golden").mkdir()
        for p in (ROOT / "golden").iterdir():
            if p.suffix in (".py", ".csv") and p.name != "completions.csv":
                shutil.copy(p, self.root / "golden" / p.name)
        self.before = tree_digest(self.root / "dataset")

    def run_in_root(self, *cmd: str) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def test_accepted_uploads_reach_golden_requests(self):
        up = self.root / "up.csv"
        up.write_bytes(csv_text(REQUEST_COLUMNS, [["R9001", "Vireo Systems", "Chief Data Officer", "Live Router", "2026-09-01",
                                                   "Can anyone intro us to the CDO at Vireo Systems?"]]).encode())
        sl = self.root / "slack.jsonl"
        sl.write_text(jsonl([thread("R9003", "Anyone close to the CTO at Halcyon Bio (halcyonbio.com)?", "I can - on it")]))
        out = self.run_in_root("golden/intake.py", "--add", str(up), "--by", "tester").stdout
        self.assertIn("target                intro_requests.csv", out)
        self.assertIn("1 new", out)
        self.run_in_root("golden/intake.py", "--add", str(sl), "--target", "slack_threads.jsonl")
        self.assertEqual(len(intake._read(self.root / "intake" / "uploads.csv")), 2)
        digest = tree_digest(self.root / "dataset")
        self.run_in_root("golden/intake.py", "--preview", str(up))
        self.assertEqual(len(intake._read(self.root / "intake" / "uploads.csv")), 2, "--preview must not accept")
        build = self.run_in_root("golden/build_golden.py").stdout
        self.assertIn("intro_requests.csv +1 upload, slack_threads.jsonl +1 upload", build)
        with open(self.root / "golden" / "golden_requests.csv", newline="", encoding="utf-8-sig") as f:
            rows = {r["request_id"]: r for r in csv.DictReader(f)}
        self.assertIn("R9001", rows)
        self.assertEqual(rows["R9001"]["company_as_written"], "Vireo Systems")
        self.assertIn("R9003", rows, "a Slack thread with a new request_id becomes a request")
        self.assertIn("halcyon", rows["R9003"]["company_as_written"].lower())
        current = self.root / "golden" / "current"
        self.assertEqual(len(intake.read_csv_file(current / "intro_requests.csv")[1]), 201)
        self.assertEqual(len(intake.read_threads(current / "slack_threads.jsonl")), 201)
        self.assertEqual(tree_digest(self.root / "dataset"), digest)
        self.assertEqual(digest, self.before)
        self.run_in_root("golden/intake.py", "--add", str(up), "--by", "tester")
        self.assertEqual(len(intake._read(self.root / "intake" / "uploads.csv")), 2, "the same file twice is one upload")

    def golden_requests(self) -> dict[str, dict]:
        with open(self.root / "golden" / "golden_requests.csv", newline="", encoding="utf-8-sig") as f:
            return {r["request_id"]: r for r in csv.DictReader(f)}

    def test_revert_takes_the_requests_an_upload_brought_out_of_golden(self):
        raw = self.golden_requests()
        up = self.root / "up.csv"
        up.write_bytes(csv_text(REQUEST_COLUMNS, [["R9001", "Vireo Systems", "CDO", "Live Router", "2026-09-01", "Intro to Vireo?"],
                                                   [next(iter(raw)), "", "", "", "", ""]]).encode())  # one new, one on file already
        sl = self.root / "slack.jsonl"
        sl.write_text(jsonl([thread("R9003", "Anyone close to the CTO at Halcyon Bio (halcyonbio.com)?", "I can - on it")]))
        self.run_in_root("golden/intake.py", "--add", str(up), "--by", "tester")
        self.run_in_root("golden/intake.py", "--add", str(sl), "--target", "slack_threads.jsonl")
        self.run_in_root("golden/build_golden.py")
        self.assertEqual(set(self.golden_requests()) - set(raw), {"R9001", "R9003"})
        with open(self.root / "golden" / "golden_allocation.csv", newline="", encoding="utf-8-sig") as f:
            self.assertIn("R9003", {a["request_id"] for a in csv.DictReader(f)})
        out = self.run_in_root("golden/intake.py", "--revert", "--by", "tester").stdout
        self.assertIn("reverted to dataset/", out)
        self.assertEqual(intake.reverted_request_ids(self.root / "dataset", self.root / "intake" / "files", self.root / "intake" / "uploads.csv"),
                         {"R9001", "R9003"}, "the request already on file is not the upload's to take away")
        self.assertEqual(tree_digest(self.root / "golden" / "current"), self.before)
        build = self.run_in_root("golden/build_golden.py").stdout
        self.assertIn("2 request(s) dropped from golden_requests.csv", build)
        dataset_ids = {r["request_id"] for r in intake.read_csv_file(self.root / "dataset" / "intro_requests.csv")[1]}
        carried = sum(rid not in dataset_ids for rid in raw)
        self.assertIn(f"{len(raw)} rows ({len(raw)} kept, of which {carried} not in dataset/intro_requests.csv and carried forward", build)
        after = self.golden_requests()
        self.assertEqual(set(after), set(raw))
        self.assertEqual({k: v["raw_ask"] for k, v in after.items()}, {k: v["raw_ask"] for k, v in raw.items()})
        with open(self.root / "golden" / "golden_allocation.csv", newline="", encoding="utf-8-sig") as f:
            self.assertNotIn("R9003", {a["request_id"] for a in csv.DictReader(f)})
        self.assertEqual(len(intake._read(self.root / "intake" / "uploads.csv")), 3, "the ledger keeps the history")
        self.assertEqual(tree_digest(self.root / "dataset"), self.before)
        # accepted again after the revert: back in, under a new upload_id
        out = self.run_in_root("golden/intake.py", "--add", str(up), "--by", "tester").stdout
        self.assertIn("-g1", out)
        self.run_in_root("golden/build_golden.py")
        self.assertIn("R9001", self.golden_requests())


if __name__ == "__main__":
    unittest.main()
