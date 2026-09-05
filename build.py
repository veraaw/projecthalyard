#!/usr/bin/env python3
"""Regenerate every report and the dashboard, in dependency order.

    python3 build.py            # everything
    python3 build.py dashboard  # one step (any prefix of the names below)
    python3 build.py resolve    # company-string -> company ID tables under golden/

The dashboard reads analysis/joins/join_rates.md and analysis/profile/profile.md,
so those steps run before it.
"""
import runpy
import sys

STEPS = [
    ("resolve", "golden.resolve_dataset"),
    ("profile", "analysis.profile.profile_csvs"),
    ("joins", "analysis.joins.join_rates"),
    ("routing", "analysis.routing.routing_kpis"),
    ("slack", "analysis.slack.slack_threads_analysis"),
    ("integrity", "analysis.integrity.integrity_audit"),
    ("sankey", "dashboard.sankey_funnel"),
    ("dashboard", "dashboard.build_dashboard"),
]


def main(argv):
    wanted = argv or [name for name, _ in STEPS]
    steps = [(name, mod) for name, mod in STEPS if any(name.startswith(w) for w in wanted)]
    if not steps:
        sys.exit(f"no step matches {wanted}; known steps: {', '.join(n for n, _ in STEPS)}")
    for name, module in steps:
        print(f"--- {name} ({module})")
        try:
            runpy.run_module(module, run_name="__main__")
        except SystemExit as exc:  # a step that ends in sys.exit() is not a failure
            if exc.code:
                raise


if __name__ == "__main__":
    main(sys.argv[1:])
