# Founder OS

Shared pre-launch builder system for planning, structuring, and tracking multiple digital products.

## Current purpose
- Capture project ideas
- Structure projects
- Generate starter tasks
- Track build progress

## First project
- AFDP

---

## Execution Worker (v1)

This repo now includes a **minimum working execution worker** that pulls queued build packets from Supabase/Postgres and executes them with Codex.

### What v1 supports
- `execution_runs` table support
- Build packet queue polling/claiming
- Approved-task → build-packet queue coordination
- Project/task lookup for context
- Codex-ready prompt generation
- Branch naming logic (`founder-os/<task-slug>-<id8>`)
- Validation command execution + tracking
- Status updates for `build_packets`, `tasks`, and `execution_runs`

### Files
- Worker: `worker/execution_worker.py`
- Coordinator: `worker/packet_coordinator.py`
- Schema migration: `sql/migrations/20260427_execution_worker.sql`

### Setup
1. Apply schema in Supabase SQL editor:
   - `sql/founder_os_schema.sql`
   - `sql/migrations/20260427_execution_worker.sql`
   - `sql/migrations/20260427_execution_worker_retries.sql` (safe to run on existing installs)
   - `sql/migrations/20260427_execution_worker_failure_codes.sql` (safe to run on existing installs)
   - `sql/migrations/20260427_execution_worker_constraints.sql` (safe to run on existing installs)
   - `sql/migrations/20260427_task_review_and_packet_link.sql` (task approval + packet link flow)
   - `sql/migrations/20260428_execution_worker_outputs.sql` (commit/PR output tracking)
2. Install Python dependency:
   ```bash
   pip install psycopg[binary]
   ```
3. Set environment variables:
   ```bash
   export SUPABASE_DB_URL='postgresql://...'
   export REPO_ROOT='/workspace'  # or absolute repo path in single-repo mode
   export REPO_MAP_JSON='{"AFDP":"/Users/jojo/Developer/african-food-discovery-platform"}'
   export COMMAND_TIMEOUT_SECONDS='1800'
   export CODEX_RESULT_JSON_RELPATH='.founder_os/execution_result.json'
   # Optional: either a template string or plain command (e.g. CODEX_EXEC_COMMAND=codex)
   export CODEX_EXEC_COMMAND='codex run --prompt-file {prompt_file} --repo {repo_path} --branch {branch}'
   # Optional: JSON array OR newline-delimited commands
   export DEFAULT_VALIDATION_COMMANDS='["npm install","npm run lint","npm run build"]'
   ```

### Run
Queue approved tasks into `build_packets`:
```bash
python worker/packet_coordinator.py
```

Process one packet and exit:
```bash
RUN_ONCE=true python worker/execution_worker.py
```

Run continuously:
```bash
python worker/execution_worker.py
```

Or use Make targets:
```bash
make queue-approved-tasks
make worker-once
make worker-loop
```

### Packet contract (minimal)
`build_packets.validation_commands` should be a JSON array of shell commands, for example:
```json
["npm test", "npm run lint"]
```

Contract checks performed by worker before execution:
- Required fields: `id`, `project_id`, `packet_title`, `packet_body`, `target_repo`, `base_branch`
- `validation_commands` must be a JSON array of strings
- `validation_commands` cannot contain blank commands
- `target_repo` must resolve inside `REPO_ROOT` and exist on disk

Database constraints enforce:
- valid packet/run statuses only
- `attempts >= 0`
- `max_attempts >= 1`

### Status behavior
- Task approval to queue:
  - Compatible approval models:
    - `tasks.approved = true` (legacy/current)
    - `tasks.review_status = approved` (new migration model)
    - `tasks.execution_status in ('Queued','Approved')` (legacy queue model)
  - approved task + `build_packet_id is null` → coordinator creates `build_packets` row
  - `tasks.build_packet_id` and `tasks.packet_generated_at` are populated
  - `tasks.status = Queued`
- On claim:
  - `build_packets.status = running`
  - `tasks.status = In Progress` (if task-linked)
- On success:
  - `build_packets.status = completed`
  - `execution_runs.status = completed`
  - `execution_runs.commit_sha`, `execution_runs.pr_url`, `execution_runs.pr_number` captured when provided by Codex output file
  - `tasks.status = Review`
- On failed attempt (before max attempts):
  - `build_packets.status = queued` (re-queued)
  - `build_packets.last_error_code` captures machine-readable failure reason
  - `build_packets.last_error` records the failure reason
  - `execution_runs.status = failed` (if run was created for that attempt)
  - `execution_runs.failure_code` captures machine-readable failure reason
- On terminal failure (max attempts reached):
  - `build_packets.status = failed`
  - `execution_runs.status = failed` (if run was created)
  - `tasks.status = Blocked`

Failure codes currently emitted by the worker:
- `missing_project`
- `missing_task`
- `invalid_packet`
- `invalid_repo_path`
- `codex_nonzero`
- `validation_nonzero`
- `unhandled_worker_error`

Codex output contract:
- Worker asks Codex to write `.founder_os/execution_result.json` in the target repo.
- JSON keys consumed by worker: `branch`, `commit_sha`, `pr_url`, `pr_number`.

### Validation steps (local)
```bash
python -m py_compile worker/execution_worker.py
python -m py_compile worker/packet_coordinator.py
python -m unittest worker/test_execution_worker.py
python -m unittest worker/test_packet_coordinator.py
RUN_ONCE=true python worker/execution_worker.py
```

The second command requires `SUPABASE_DB_URL` and a reachable database.

### Quick smoke test (recommended)
1. Seed a packet with `worker/smoke_test.sql` (replace placeholder IDs/paths first).
2. Run worker once:
   ```bash
   RUN_ONCE=true python worker/execution_worker.py
   ```
3. Re-run the status queries from `worker/smoke_test.sql` and confirm:
   - `build_packets.status` moved from `queued` to `completed` or `failed`
   - one `execution_runs` row exists for that packet

### Retry behavior
- Each packet tracks `attempts` and `max_attempts` (`max_attempts` defaults to `3`).
- On failure before max attempts, packet is re-queued (`status = queued`) for another try.
- Once max attempts is reached, packet is marked `failed` and task is marked `Blocked`.
