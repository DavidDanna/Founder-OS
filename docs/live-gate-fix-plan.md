# Founder OS Live Gate Fix Plan

This runbook focuses on unblocking the three current blockers seen by preflight:

1. Supabase DB connectivity (`Network is unreachable`)
2. Repo path accessibility
3. Codex binary availability

## 1) Fix Supabase DB connectivity

If you see `Network is unreachable` to the `db.<ref>.supabase.co` host, your runtime likely cannot route IPv6.

### Use an IPv4-capable connection string
- In Supabase Dashboard, open **Project Settings → Database → Connection string**.
- Prefer a **pooler** host that supports IPv4 in your runtime.
- Set:

```bash
export SUPABASE_DB_URL='postgresql://<user>:<password>@<pooler-host>:6543/postgres?sslmode=require'
```

### Validate connection
```bash
make preflight
```

## 2) Fix repo path accessibility

The worker must run where the target repo path exists.

### Option A (recommended): run on your machine
Use your local path directly:

```bash
export REPO_ROOT='/Users/jojo/Developer/african-food-discovery-platform'
export DEFAULT_TARGET_REPO='AFDP'
export REPO_MAP_JSON='{"AFDP":"/Users/jojo/Developer/african-food-discovery-platform"}'
```

### Option B: run in container/CI
Mount repo(s) into runtime and point `REPO_ROOT`/`REPO_MAP_JSON` to mounted paths.

## 3) Fix Codex binary availability

Install Codex CLI in the same environment running worker/coordinator.

### Validate binary
```bash
which codex
make preflight
```

## 4) Queue and execute one real task

Use one real task row with a valid project link.

```bash
export DEFAULT_VALIDATION_COMMANDS=$'npm install\nnpm run lint\nnpm run build'
python worker/packet_coordinator.py
RUN_ONCE=true python worker/execution_worker.py
```

## 5) Verify DB state after run

```sql
select id, status, started_at, completed_at, codex_branch, last_error_code, last_error
from build_packets
order by queued_at desc
limit 10;

select id, build_packet_id, status, failure_code, commit_sha, pr_url, pr_number, codex_exit_code
from execution_runs
order by started_at desc
limit 10;
```

## 6) Definition of done for live gate

- Preflight passes (`database`, `repos`, `codex`, `git`).
- Coordinator queues at least one packet.
- Worker completes one run (`completed` or clear terminal `failed` with reason).
- `execution_runs` captures branch/commit/PR outputs when Codex emits result JSON.
