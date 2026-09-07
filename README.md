# Project Halyard

Where intro requests stall between Slack, the CRM and the people who can make the
introduction, and what to do about it next. Every number is rebuilt from the raw
exports; the result is a static dashboard built into `docs/` and published to GitHub Pages
by the rebuild workflow.

```
dataset/    raw exports, read-only and never written: intro_requests, intro_outcomes, crm_accounts,
            connector_roster, connections_*.csv, investor_network.csv, slack_threads.jsonl
intake/     more live data accepted since (golden/intake.py): uploads.csv is the ledger, files/ the
            uploads byte for byte, rejected.csv the ones the build could not apply
golden/     state derived from dataset/ (golden_*.csv, supply_reach, allocation history,
            completions.csv from the dashboard) and the code that derives it; current/ is
            dataset/ with the accepted uploads applied - what every reader below reads
analysis/   one folder per question (profile, joins, routing, slack, integrity, crm) with the
            script and the report it writes; traces/ (gitignored, rebuilt each run) holds
            one history per company, the same text docs/companytrace.html inlines
dashboard/  the static pages (build_dashboard.py, live_priorities.py/.js, batch_ask.py ...)
docs/       build output, gitignored: the site (index.html + every tab), routing_flow.png and
            docs/build_stamp.json; the workflow uploads it as the GitHub Pages artifact
config/     batch_ask_templates.json, supabase_schema.sql (the completions and intake_uploads
            tables), supabase_rebuild_trigger.sql (rebuild the site when a row lands in either)
tests/      python3 -m unittest discover tests (Node on PATH for the JS parity tests)
```

## Build

```
pip install -r requirements.txt
python3 golden/build_golden.py [--as-of YYYY-MM-DD]   # dataset/ + intake/ -> golden/current/ -> golden/
python3 build.py [--as-of YYYY-MM-DD]                 # tests, analysis/, docs/, in dependency order
python3 build.py dashboard                            # one step
python3 golden/intake.py --preview FILE [--target NAME]   # what accepting FILE would change; writes nothing
python3 golden/intake.py --add FILE [--target NAME] [--by WHO]  # accept it by hand (what the tab's Accept does)
python3 golden/intake.py --revert [--by WHO]              # back to the September export (the tab's Revert button)
```

`--as-of` (or `HALYARD_AS_OF`) freezes the build clock so every page and report says
"as of" the same day. The rebuild workflow (`.github/workflows/rebuild.yml`) runs on
every Submit or Accept from the Live Priorities tab (a Postgres trigger on the `completions`
and `intake_uploads` tables, `config/supabase_rebuild_trigger.sql`, fires a
`repository_dispatch`) and every 15 minutes as a backstop: pulls the Supabase `completions`
table into `golden/completions.csv` and `intake_uploads` into `intake/`, rebuilds, tests,
commits `golden/`, `intake/` and `analysis/` when they changed, and deploys `docs/` to
GitHub Pages (repo Settings -> Pages -> Source: GitHub Actions). A row the build cannot
apply is set aside in `golden/completions_rejected.csv` / `intake/rejected.csv` rather than
stopping the run.

## More live data

`dataset/` is the September export and stays as it is. New data - a fresh export of any of
its CSVs, new rows for one, a Slack export of threads - goes in through the Live Priorities
tab, **Intake: Add More Live Data**: drop a CSV or a Slack JSON/JSONL file, check the file it
will update (guessed from the name and columns, changeable), and read what accepting it
would change - new rows, new columns, every existing value it would override, keys repeated
within the file - before clicking Accept. Nothing is written until then. Accept posts the
file to the `intake_uploads` table; the next rebuild pulls it into `intake/`, writes
`golden/current/` (`dataset/` with every accepted upload applied, in order) and every
analysis and page is rebuilt from that. Rows are matched on each file's key (`request_id`,
`account_id`, `name`, ...): a new key is a new row, a key on file is updated where the
upload has a non-empty differing cell, new columns are added blank on old rows; a Slack
thread already on file gains only the messages it lacks, and a thread for a request_id not
in `intro_requests.csv` becomes a request. The same file accepted twice is one upload.
Without Supabase, Accept offers the file to download plus the `golden/intake.py --add`
command that does the same thing locally. Until the `intake_uploads` section of
`config/supabase_schema.sql` has been run, the rebuild notes the missing table and goes on
without it (the site still publishes); any other failure to read the table stops it.
**Revert to Sep Raw Data State** (same band) files a revert row instead of a file: nothing
is deleted from `intake/`, but from the next
rebuild no upload accepted before it applies, so `golden/current/` is `dataset/` again and
a request those uploads were the only source of leaves `golden_requests.csv` (the one
exception to that file being append-only); uploads accepted afterwards apply on top of
that. `golden/intake.py`'s docstring has the
details.

The Live Priorities tab posts completions and uploads with the publishable key in
`SUPABASE_URL` / `SUPABASE_ANON_KEY`; the build reads them back with
`SUPABASE_SERVICE_KEY`. All three come from the environment or a gitignored `.env`; without
them the pages still build, with Submit disabled. Every module's docstring explains its
part in more depth.
