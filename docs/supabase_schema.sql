-- The Supabase table the Live Priorities tab's Submit writes to, for reference.
-- Matches the live table's column list and types as reported by its REST
-- schema (PostgREST OpenAPI) on 2026-09-06; the policy block is the intent
-- the anon role is verified against (insert only: a SELECT with the anon key
-- answers 401 / 42501 "permission denied for table completions").
--
-- One row per thing someone did from the dashboard. completion_id is built by
-- the browser as <request_id>:<action>:<YYYY-MM-DD> (company_id in place of
-- request_id for account_created), so resubmitting the same tick on the
-- same day hits the primary key and lands nothing new. The build pulls the
-- table into golden/completions.csv (python3 golden/build_golden.py
-- --completions supabase) and reads that file; the table is an input to the
-- build, not a dependency of it.

create table if not exists public.completions (
  completion_id text primary key,
  completed_at  timestamptz not null default now(),
  completed_by  text not null,
  action        text not null check (action in ('ask_sent', 'nudged', 'account_created')),
  request_id    text,            -- R1234; empty for account_created
  company_id    text,            -- C001; the account created, or the request's company
  connector     text,            -- who was asked / nudged; empty for account_created
  note          text             -- what the row was on the page, for a human reading the table
);

alter table public.completions enable row level security;

-- the dashboard (anon / publishable key): insert only
grant insert on public.completions to anon;
create policy "dashboard can record a completion"
  on public.completions for insert to anon with check (true);
-- no select / update / delete policy for anon: the browser cannot read the table back.
-- The build reads it with the service role key, which bypasses RLS.
