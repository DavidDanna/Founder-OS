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
- Project/task lookup for context
- Codex-ready prompt generation
- Branch naming logic (`founder-os/<task-slug>-<id8>`)
- Validation command execution + tracking
- Status updates for `build_packets`, `tasks`, and `execution_runs`

### Files
- Worker: `worker/execution_worker.py`
- Schema migration: `sql/migrations/20260427_execution_worker.sql`

### Setup
1. Apply schema in Supabase SQL editor:
   - `sql/founder_os_schema.sql`
   - `sql/migrations/20260427_execution_worker.sql`
2. Install Python dependency:
   ```bash
   pip install psycopg[binary]
   ```
3. Set environment variables:
   ```bash
   export SUPABASE_DB_URL='postgresql://...'
   export REPO_ROOT='/workspace'
   # Optional override if your Codex CLI syntax differs
   export CODEX_EXEC_COMMAND='codex run --prompt-file {prompt_file} --repo {repo_path} --branch {branch}'
   ```

### Run
Process one packet and exit:
```bash
RUN_ONCE=true python worker/execution_worker.py
```

Run continuously:
```bash
python worker/execution_worker.py
```

### Packet contract (minimal)
`build_packets.validation_commands` should be a JSON array of shell commands, for example:
```json
["npm test", "npm run lint"]
```

### Status behavior
- On claim:
  - `build_packets.status = running`
  - `tasks.status = In Progress` (if task-linked)
- On success:
  - `build_packets.status = completed`
  - `execution_runs.status = completed`
  - `tasks.status = Review`
- On failure (Codex/validation/unhandled):
  - `build_packets.status = failed`
  - `execution_runs.status = failed` (if run was created)
  - `tasks.status = Blocked`

### Validation steps (local)
```bash
python -m py_compile worker/execution_worker.py
RUN_ONCE=true python worker/execution_worker.py
```

The second command requires `SUPABASE_DB_URL` and a reachable database.
