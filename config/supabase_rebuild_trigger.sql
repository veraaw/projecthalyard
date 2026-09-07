-- Rebuild the site the moment a completion or an accepted upload lands.
--
-- The rebuild workflow (.github/workflows/rebuild.yml) listens for a GitHub
-- repository_dispatch event of type `completion`; this trigger posts one from
-- Postgres with pg_net whenever an insert into public.completions lands a row.
-- The same function is the trigger on public.intake_uploads (supabase_schema.sql
-- attaches it): it reads only the statement's transition table, so it does not
-- care which table fired it, and one event type is enough - the workflow pulls
-- both tables every run.
-- The 15-minute cron stays as a backstop: GitHub runs schedules best-effort and
-- a */15 cron fires every hour or two in practice.
--
-- Run once in the Supabase SQL editor (Dashboard -> SQL Editor), in order.
--
-- 1. A GitHub token that may fire the dispatch. github.com -> Settings ->
--    Developer settings -> Personal access tokens -> Fine-grained tokens ->
--    Generate: Repository access "Only select repositories" -> projecthalyard;
--    Permissions -> Repository -> Contents: Read and write (what the
--    dispatches endpoint asks for). Nothing else. Then store it in Vault so it
--    is neither in this file nor readable by the anon role:
--
--      select vault.create_secret('github_pat_...', 'github_rebuild_token',
--                                 'fine-grained PAT: repository_dispatch on veraaw/projecthalyard');
--
--    To rotate: update vault.secrets set secret = 'github_pat_...' where name = 'github_rebuild_token';
--
-- 2. The rest of this file.

create extension if not exists pg_net;

create or replace function public.request_site_rebuild()
returns trigger
language plpgsql
security definer            -- runs as the owner: the anon insert cannot read Vault itself
set search_path = ''
as $$
declare
  token text;
begin
  -- a statement that landed nothing (every row hit the primary key) is not a change
  if not exists (select 1 from inserted) then
    return null;
  end if;
  select decrypted_secret into token
    from vault.decrypted_secrets
   where name = 'github_rebuild_token';
  if token is null then
    raise warning 'request_site_rebuild: no github_rebuild_token in vault; the cron will pick this up';
    return null;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/veraaw/projecthalyard/dispatches',
    body    := jsonb_build_object('event_type', 'completion'),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || token,
      'Accept',        'application/vnd.github+json',
      'Content-Type',  'application/json',
      'User-Agent',    'halyard-supabase-trigger'
    )
  );
  return null;
end
$$;

revoke all on function public.request_site_rebuild() from public, anon, authenticated;

-- once per insert statement, not per row: Submit is one statement, one rebuild
drop trigger if exists completions_request_site_rebuild on public.completions;
create trigger completions_request_site_rebuild
  after insert on public.completions
  referencing new table as inserted
  for each statement
  execute function public.request_site_rebuild();

-- Check the token without touching the table (a test row would be pulled into
-- golden/completions.csv by the very rebuild it triggers, and rows on file stay):
--
--   select net.http_post(
--     url     := 'https://api.github.com/repos/veraaw/projecthalyard/dispatches',
--     body    := '{"event_type": "completion"}'::jsonb,
--     headers := jsonb_build_object(
--       'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'github_rebuild_token'),
--       'Accept', 'application/vnd.github+json', 'Content-Type', 'application/json', 'User-Agent', 'halyard-supabase-trigger'));
--
-- then, a few seconds later, the response (204 is success; 401/404 is a token
-- without access to the repo; 422 is a malformed body):
--
--   select created, status_code, content from net._http_response order by created desc limit 5;
--
-- and a run titled "rebuild" with event `repository_dispatch` at
-- https://github.com/veraaw/projecthalyard/actions/workflows/rebuild.yml.
-- After that, every Submit or Accept from the Live Priorities tab does the same.
