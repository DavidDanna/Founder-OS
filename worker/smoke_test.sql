-- Founder OS worker smoke test
-- Replace IDs and repo path placeholders before running.

-- 1) ensure a task exists for the project (optional)
-- insert into tasks (project_id, task_title, description, status)
-- values ('<project_uuid>', 'Smoke test execution task', 'Validate worker end-to-end', 'New')
-- returning id;

-- 2) enqueue one packet
insert into build_packets (
  project_id,
  task_id,
  packet_title,
  packet_body,
  target_repo,
  base_branch,
  max_attempts,
  validation_commands
) values (
  '<project_uuid>',
  null,
  'Smoke test packet',
  'Create or update a small README note so we can validate execution flow.',
  '<repo-folder-under-REPO_ROOT>',
  'main',
  2,
  '["git status --short"]'::jsonb
)
returning id, status, queued_at;

-- 3) watch queue state
select id, status, started_at, completed_at, codex_branch, last_error
from build_packets
order by queued_at desc
limit 5;

-- 4) inspect execution run details
select id, build_packet_id, status, codex_exit_code, started_at, finished_at
from execution_runs
order by started_at desc
limit 5;
