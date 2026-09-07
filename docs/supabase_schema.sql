-- The Supabase table the Live Priorities tab's Submit writes to, for reference.
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
-- rejects that action, so delete them first (or the scheduled rebuild stops).
--   delete from public.completions where action = 'account_created';
alter table public.completions drop constraint completions_action_check;
alter table public.completions
  add constraint completions_action_check
  check (action in ('ask_sent', 'nudged', 'chased', 'checked_in'));

alter table public.completions enable row level security;

-- the dashboard (anon / publishable key): insert only
grant insert on public.completions to anon;
create policy "dashboard can record a completion"
  on public.completions for insert to anon with check (true);
-- no select / update / delete policy for anon: the browser cannot read the table back.
-- The build reads it with the service role key, which bypasses RLS.
