# Project Halyard

Where intro requests stall between Slack, the CRM and the people who can make the
introduction, and what to do about it next. Every number is rebuilt from the raw
exports; the result is a static dashboard built into `docs/` and published to GitHub Pages
by the rebuild workflow.

```
dataset/    raw exports, read-only: intro_requests, intro_outcomes, crm_accounts, connector_roster,
            connections_*.csv, investor_network.csv, slack_threads.jsonl
golden/     state derived from dataset/ (golden_*.csv, supply_reach, allocation history,
            completions.csv from the dashboard) and the code that derives it
analysis/   one folder per question (profile, joins, routing, slack, integrity, crm) with the
            script and the report it writes; traces/ (gitignored, rebuilt each run) holds
            one history per company, the same text docs/companytrace.html inlines
dashboard/  the static pages (build_dashboard.py, live_priorities.py/.js, batch_ask.py ...)
docs/       build output, gitignored: the site (index.html + every tab), routing_flow.png and
            docs/build_stamp.json; the workflow uploads it as the GitHub Pages artifact
config/     batch_ask_templates.json, supabase_schema.sql (the completions table)
tests/      python3 -m unittest discover tests (Node on PATH for the JS parity tests)
```

## Build

```
pip install -r requirements.txt
python3 golden/build_golden.py [--as-of YYYY-MM-DD]   # dataset/ -> golden/
python3 build.py [--as-of YYYY-MM-DD]                 # tests, analysis/, docs/, in dependency order
python3 build.py dashboard                            # one step
```

`--as-of` (or `HALYARD_AS_OF`) freezes the build clock so every page and report says
"as of" the same day. The scheduled workflow (`.github/workflows/rebuild.yml`) runs
every 15 minutes: pulls the Supabase `completions` table into `golden/completions.csv`,
rebuilds, tests, commits `golden/` and `analysis/` when they changed, and deploys `docs/` to
GitHub Pages (repo Settings -> Pages -> Source: GitHub Actions). A row the build cannot
apply is set aside in `golden/completions_rejected.csv` rather than stopping the run.

The Live Priorities tab posts completions with the publishable key in `SUPABASE_URL` /
`SUPABASE_ANON_KEY`; the build reads them back with `SUPABASE_SERVICE_KEY`. All three
come from the environment or a gitignored `.env`; without them the pages still build,
with Submit disabled. Every module's docstring explains its part in more depth.
