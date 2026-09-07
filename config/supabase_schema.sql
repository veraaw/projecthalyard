-- The Supabase table the Live Priorities tab's Submit writes to, for reference
-- (not part of the published site: docs/ is build output).
-- Matches the live table's column list and types as reported by its REST
-- schema (PostgREST OpenAPI) on 2026-09-06; the policy block is the intent
-- the anon role is verified against (insert only: a SELECT with the anon key
-- answers 401 / 42501 "permission denied for table completions").
--
-- One row per thing someone did from the dashboard. completion_id is built by
-- the browser as <request_id>:<action>:<YYYY-MM-DD> (company_id in place of
-- request_id for checked_in), so resubmitting the same tick on the
-- same day hits the primary key and lands nothing new. The build pulls the
-- table into golden/completions.csv (python3 golden/build_golden.py
-- --completions supabase) and reads that file; the table is an input to the
-- build, not a dependency of it.

create table if not exists public.completions (
  completion_id text primary key,
  completed_at  timestamptz not null default now(),
  completed_by  text not null,
  -- ask_sent: Top priorities / a connector's top list; nudged: Core bottlenecks or a
  -- connector's "already sitting on" row they replied to; chased: a sitting-on row
  -- they never replied to; checked_in: Overdue a check-in (company-level)
  action        text not null check (action in ('ask_sent', 'nudged', 'chased', 'checked_in')),
  request_id    text,            -- R1234; empty for checked_in
  company_id    text,            -- C001; the company checked in on, or the request's company
  connector     text,            -- who was asked / nudged / chased; empty for checked_in
  note          text             -- what the row was on the page, for a human reading the table
);

-- Migration for a table created with the earlier action list
-- ('ask_sent', 'nudged', 'account_created'); run once in the SQL editor.
-- Any account_created rows already in the table are left alone: the build
-- sets that row aside in golden/completions_rejected.csv, so delete them:
--   delete from public.completions where action = 'account_created';
alter table public.completions drop constraint completions_action_check;
alter table public.completions
  add constraint completions_action_check
  check (action in ('ask_sent', 'nudged', 'chased', 'checked_in'));

-- What the build needs of a row (golden/build_golden.py completion_problem),
-- enforced where the row is written: the publishable key is public, so
-- anyone can insert, and a row the build cannot apply is set aside in
-- golden/completions_rejected.csv. Run once in the SQL editor.
alter table public.completions
  add constraint completions_completed_by_check
  check (completed_by <> '');
alter table public.completions
  add constraint completions_request_kinds_check
  check (action = 'checked_in'
         or (coalesce(request_id, '') <> '' and coalesce(connector, '') <> ''));
alter table public.completions
  add constraint completions_checked_in_check
  check (action <> 'checked_in' or coalesce(company_id, '') <> '');

alter table public.completions enable row level security;

-- the dashboard (anon / publishable key): insert only
grant insert on public.completions to anon;
create policy "dashboard can record a completion"
  on public.completions for insert to anon with check (true);
-- no select / update / delete policy for anon: the browser cannot read the table back.
-- The build reads it with the service role key, which bypasses RLS.


-- The table "Intake: Add More Live Data" Accept writes to. One row per accepted
-- upload: the file as dropped (content), which dataset/ file it updates
-- (target), and the summary the person accepted. upload_id is built by the
-- browser as <target stem>-<FNV-1a 64 of the content>, so accepting the same
-- file twice hits the primary key and lands nothing new. The build pulls the
-- table into intake/ (python3 golden/build_golden.py --intake supabase, or
-- golden/intake.py --pull supabase): the file goes to intake/files/, the row to
-- intake/uploads.csv, and golden/current/ is rebuilt as dataset/ + every
-- accepted upload in order. dataset/ itself is never written. A row the build
-- cannot apply (unknown target, no key column, malformed CSV / JSON) is set
-- aside in intake/rejected.csv with the reason, never applied.

create table if not exists public.intake_uploads (
  upload_id    text primary key,
  received_at  timestamptz not null default now(),
  received_by  text not null check (received_by <> ''),
  -- intro_requests.csv, connections_trask.csv, slack_threads.jsonl, ...; or 'revert': the tab's
  -- "Revert to Sep Raw Data State", a row with no file after which no earlier upload applies
  target       text not null check (target ~ '^[a-z0-9_\-]+\.(csv|jsonl)$' or target = 'revert'),
  filename     text,                        -- the name of the file as dropped, for a human reading the table
  content      text not null check (content <> '' or target = 'revert'),  -- the file, verbatim (UTF-8; CSV or Slack JSON / JSONL)
  rows         integer,                     -- the summary shown when it was accepted: rows in the upload,
  new_rows     integer,                     -- keys not on file,
  changed_rows integer,                     -- rows on file with a value overridden,
  new_columns  text,                        -- columns the file lacked, ';'-joined
  note         text
);

alter table public.intake_uploads enable row level security;

-- the dashboard (anon / publishable key): insert only; the browser cannot read uploads back
grant insert on public.intake_uploads to anon;
create policy "dashboard can accept an upload"
  on public.intake_uploads for insert to anon with check (true);

-- rebuild the site the moment an upload is accepted (same function as completions;
-- config/supabase_rebuild_trigger.sql must have been run first)
drop trigger if exists intake_uploads_request_site_rebuild on public.intake_uploads;
create trigger intake_uploads_request_site_rebuild
  after insert on public.intake_uploads
  referencing new table as inserted
  for each statement
  execute function public.request_site_rebuild();
