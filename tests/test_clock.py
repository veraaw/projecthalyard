"""One build date for every step: golden/clock.py and build.py --as-of.

    python3 -m unittest tests.test_clock

Three steps used to read their own clock (the allocator date.today(), the
dashboard date.today() at import, the integrity audit a date typed into the
source), so one build could print three different "as of" dates. Now the date
lives in HALYARD_AS_OF and every default reads it back.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis import trace  # noqa: E402
from dashboard import live_priorities as lp  # noqa: E402
from golden import clock  # noqa: E402
from tests.test_rebuild import ScratchRootTest, read_csv  # noqa: E402

FROZEN = "2026-10-05"


class ClockTest(ScratchRootTest):
    def test_unset_is_today_utc(self):
        with mock.patch.dict(os.environ, {clock.ENV: ""}):
            self.assertEqual(clock.as_of(), datetime.now(timezone.utc).date())

    def test_set_is_that_date(self):
        with mock.patch.dict(os.environ, {clock.ENV: FROZEN}):
            self.assertEqual(clock.as_of(), date(2026, 10, 5))
        with mock.patch.dict(os.environ, {clock.ENV: "2026-13-01"}), self.assertRaises(SystemExit) as died:
            clock.as_of()
        self.assertIn(clock.ENV, str(died.exception))

    def test_every_default_reads_the_clock(self):
        with mock.patch.dict(os.environ, {clock.ENV: FROZEN}):
            self.assertEqual(lp.payload()["as_of"], FROZEN)
            self.assertEqual({t["as_of"] for t in trace.all_traces()}, {FROZEN})

    def test_build_golden_reads_the_clock(self):
        """No --as-of on the command line: the allocator's cycle is the build's."""
        env = {**os.environ, clock.ENV: FROZEN}
        proc = self.run_build(env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cycles = {a["cycle"] for a in read_csv(self.allocation)}
        self.assertIn(FROZEN[:7], cycles)
        decided = {a["decided_at"][:10] for a in read_csv(self.allocation) if a["cycle"] == FROZEN[:7]}
        self.assertEqual(decided, {FROZEN})

    def test_build_rejects_a_malformed_date(self):
        proc = subprocess.run([sys.executable, str(ROOT / "build.py"), "--as-of", "yesterday", "no-such-step"],
                              capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a YYYY-MM-DD date", proc.stderr)
