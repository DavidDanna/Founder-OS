-- Persist codex git outputs for branch/commit/PR observability.

alter table if exists execution_runs
  add column if not exists commit_sha text;

alter table if exists execution_runs
  add column if not exists pr_url text;

alter table if exists execution_runs
  add column if not exists pr_number int;
