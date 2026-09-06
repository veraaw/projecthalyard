#!/usr/bin/env python3
"""Regenerate every report and the dashboard, in dependency order.

    python3 build.py               # everything
    python3 build.py dashboard     # one step (any prefix of the names below)
    python3 build.py --skip-tests  # everything but the tests, for a caller that
                                   # runs them itself against the regenerated docs/
    python3 build.py --as-of 2026-09-05   # freeze the build clock (default: today, UTC)

Every step reads the same date back through golden.clock.as_of() (it is exported
as HALYARD_AS_OF), so the traces, the CRM write-back, the integrity audit and the
dashboard all say "as of" the same day. golden/build_golden.py reads it too:
set HALYARD_AS_OF once and the allocation agrees with the pages built from it.

The trace step writes one company history per company with a request to
analysis/traces/ (`python3 analysis/trace.py "Harrowgate Health"` prints one).
The crm step writes what the CRM should learn from the routing data to
analysis/crm/ (crm_import.csv for the importer, crm_review.csv with every
recommendation) and prints the counts per group.

The dashboard reads analysis/joins/join_rates.md and analysis/profile/profile.md,
so those steps run before it. The tests run first (`python3 -m unittest
discover tests`): a failure exits non-zero and stops the build.
"""
import argparse
import os
import runpy
import sys
import unittest
from pathlib import Path

from analysis.crm.writeback import write_all as write_crm_writeback
from analysis.trace import write_all as write_traces
from golden import clock

ROOT = Path(__file__).resolve().parent


def run_tests():
    """python3 -m unittest discover tests"""
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        sys.exit(1)


STEPS = [
    ("tests", run_tests),
    ("profile", "analysis.profile.profile_csvs"),
    ("joins", "analysis.joins.join_rates"),
    ("routing", "analysis.routing.routing_kpis"),
    ("slack", "analysis.slack.slack_threads_analysis"),
    ("integrity", "analysis.integrity.integrity_audit"),
    ("repeat-companies", "analysis.profile.repeat_companies"),
    ("trace", write_traces),
    ("crm", write_crm_writeback),
    ("sankey", "dashboard.sankey_funnel"),
    ("dashboard", "dashboard.build_dashboard"),
]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("steps", nargs="*", help="steps to run, by any prefix of their names (default: all)")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--as-of", metavar="YYYY-MM-DD", help="the build clock; default HALYARD_AS_OF, else today (UTC)")
    args = ap.parse_args(argv)
    if args.as_of:
        os.environ[clock.ENV] = args.as_of
    today = clock.as_of()
    os.environ[clock.ENV] = today.isoformat()
    wanted = args.steps or [name for name, _ in STEPS]
    steps = [(name, mod) for name, mod in STEPS
             if any(name.startswith(w) for w in wanted) and not (args.skip_tests and name == "tests")]
    if not steps:
        sys.exit(f"no step matches {wanted}; known steps: {', '.join(n for n, _ in STEPS)}")
    print(f"as of {today.isoformat()}")
    for name, step in steps:
        print(f"--- {name} ({step if isinstance(step, str) else step.__doc__})")
        try:
            step() if callable(step) else runpy.run_module(step, run_name="__main__")
        except SystemExit as exc:  # a step that ends in sys.exit() is not a failure
            if exc.code:
                raise


if __name__ == "__main__":
    main(sys.argv[1:])
