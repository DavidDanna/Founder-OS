create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  project_name text not null,
  project_type text,
  summary text,
  problem_statement text,
  target_user text,
  stage text default 'Idea',
  priority text default 'Medium',
  status text default 'Active',
  repo_link text,
  notes text,
  created_at timestamptz default now()
);

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  task_title text not null,
  task_type text,
  description text,
  priority text default 'Medium',
  status text default 'New',
  needs_review boolean default false,
  created_at timestamptz default now()
);

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  document_type text,
  title text not null,
  status text default 'Draft',
  link text,
  created_at timestamptz default now()
);

create table if not exists weekly_summaries (
  id uuid primary key default gen_random_uuid(),
  week_label text not null,
  summary_text text,
  open_items text,
  priority_projects text,
  created_at timestamptz default now()
);
