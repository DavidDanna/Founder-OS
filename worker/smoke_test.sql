-- Founder OS worker smoke test
-- Replace IDs and repo path placeholders before running.

-- 1) ensure a task exists for the project (optional)
-- insert into tasks (project_id, task_title, description, status)
-- values ('<project_uuid>', 'Smoke test execution task', 'Validate worker end-to-end', 'New')
-- returning id;

-- 1b) approve one task for packet generation
-- update tasks
--    set review_status = 'approved',
--        approved_at = now()
--  where id = '<task_uuid>';

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
select id, status, started_at, completed_at, codex_branch, last_error_code, last_error
from build_packets
order by queued_at desc
limit 5;

-- 3b) verify task linkage
select id, status, review_status, build_packet_id, packet_generated_at
from tasks
order by created_at desc
limit 5;

-- 4) inspect execution run details
select id, build_packet_id, status, failure_code, commit_sha, pr_url, pr_number, codex_exit_code, started_at, finished_at
from execution_runs
order by started_at desc
limit 5;
