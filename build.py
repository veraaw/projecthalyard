#!/usr/bin/env python3
"""Regenerate every report and the dashboard, in dependency order.

    python3 build.py            # everything
    python3 build.py dashboard  # one step (any prefix of the names below)

The trace step writes one company history per company with a request to
analysis/traces/ (`python3 analysis/trace.py "Harrowgate Health"` prints one).
The crm step writes what the CRM should learn from the routing data to
analysis/crm/ (crm_import.csv for the importer, crm_review.csv with every
recommendation) and prints the counts per group.

The dashboard reads analysis/joins/join_rates.md and analysis/profile/profile.md,
so those steps run before it. The tests run first (`python3 -m unittest
discover tests`): a failure exits non-zero and stops the build.
"""
import runpy
import sys
import unittest
from pathlib import Path

from analysis.crm.writeback import write_all as write_crm_writeback
from analysis.trace import write_all as write_traces

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
    wanted = argv or [name for name, _ in STEPS]
    steps = [(name, mod) for name, mod in STEPS if any(name.startswith(w) for w in wanted)]
    if not steps:
        sys.exit(f"no step matches {wanted}; known steps: {', '.join(n for n, _ in STEPS)}")
    for name, step in steps:
        print(f"--- {name} ({step if isinstance(step, str) else step.__doc__})")
        try:
            step() if callable(step) else runpy.run_module(step, run_name="__main__")
        except SystemExit as exc:  # a step that ends in sys.exit() is not a failure
            if exc.code:
                raise


if __name__ == "__main__":
    main(sys.argv[1:])
