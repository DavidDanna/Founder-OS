-- Founder OS Execution Worker baseline schema

create table if not exists build_packets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  task_id uuid references tasks(id) on delete set null,
  packet_title text not null,
  packet_body text not null,
  target_repo text not null,
  base_branch text not null default 'main',
  status text not null default 'queued', -- queued | running | completed | failed
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  codex_branch text,
  validation_commands jsonb not null default '[]'::jsonb,
  last_error text
);

create table if not exists execution_runs (
  id uuid primary key default gen_random_uuid(),
  build_packet_id uuid not null references build_packets(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  task_id uuid references tasks(id) on delete set null,
  status text not null default 'running', -- running | completed | failed
  codex_prompt text not null,
  codex_branch text not null,
  codex_stdout text,
  codex_stderr text,
  codex_exit_code int,
  validation_results jsonb not null default '[]'::jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create index if not exists idx_build_packets_status_queued_at
  on build_packets(status, queued_at);

create index if not exists idx_execution_runs_build_packet_id
  on execution_runs(build_packet_id);
