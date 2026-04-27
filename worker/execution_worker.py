#!/usr/bin/env python3
"""Founder OS execution worker (minimum viable version).

Flow:
1) claim one queued build packet
2) lookup project/task context
3) generate Codex prompt + branch name
4) execute Codex command
5) run validation commands
6) update build_packets, tasks, execution_runs statuses
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


@dataclass
class WorkerConfig:
    db_url: str
    poll_seconds: int = 10
    codex_exec_command: str = "codex run --prompt-file {prompt_file} --repo {repo_path} --branch {branch}"
    repo_root: str = "/workspace"
    command_timeout_seconds: int = 1800


class PacketValidationError(ValueError):
    """Raised when a queued build packet does not meet the worker contract."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_slug(value: str, max_len: int = 40) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized[:max_len] or "task"


def build_branch_name(task: dict[str, Any] | None, packet: dict[str, Any]) -> str:
    task_part = "task"
    if task:
        task_part = sanitize_slug(task.get("task_title") or "task")
        task_id = str(task["id"])[:8]
    else:
        task_id = str(packet["id"])[:8]
    return f"founder-os/{task_part}-{task_id}"


def build_codex_prompt(packet: dict[str, Any], project: dict[str, Any], task: dict[str, Any] | None, branch: str) -> str:
    task_block = ""
    if task:
        task_block = (
            f"Task Title: {task['task_title']}\n"
            f"Task Description: {task.get('description') or 'N/A'}\n"
            f"Task Type: {task.get('task_type') or 'N/A'}\n"
        )

    return (
        "You are Codex acting as Founder OS execution engine.\n"
        "Implement only what is requested in the build packet with minimal changes.\n"
        "Do not add infrastructure not explicitly requested.\n\n"
        f"Project: {project['project_name']}\n"
        f"Project Summary: {project.get('summary') or 'N/A'}\n"
        f"Target Repo: {packet['target_repo']}\n"
        f"Base Branch: {packet['base_branch']}\n"
        f"Execution Branch: {branch}\n\n"
        f"Build Packet Title: {packet['packet_title']}\n"
        f"Build Packet Body:\n{packet['packet_body']}\n\n"
        f"{task_block}"
        "After making changes, run requested validations, commit, and prepare PR output.\n"
    )


def run_command(command: str, cwd: str, timeout_seconds: int) -> tuple[int, str, str]:
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        timeout_msg = f"Command timed out after {timeout_seconds}s"
        stderr = f"{stderr}\n{timeout_msg}".strip()
        return 124, stdout, stderr


def run_codex(
    codex_template: str,
    prompt: str,
    repo_path: str,
    branch: str,
    timeout_seconds: int,
) -> tuple[int, str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        command = codex_template.format(
            prompt_file=shlex.quote(prompt_file),
            repo_path=shlex.quote(repo_path),
            branch=shlex.quote(branch),
        )
        return run_command(command, cwd=repo_path, timeout_seconds=timeout_seconds)
    finally:
        os.unlink(prompt_file)


def validate_packet(packet: dict[str, Any]) -> None:
    required = ["id", "project_id", "packet_title", "packet_body", "target_repo", "base_branch"]
    missing = [key for key in required if not packet.get(key)]
    if missing:
        raise PacketValidationError(f"Missing required packet fields: {', '.join(missing)}")


def parse_validation_commands(raw_commands: Any) -> list[str]:
    if raw_commands is None:
        return []
    commands = raw_commands
    if isinstance(raw_commands, str):
        try:
            commands = json.loads(raw_commands)
        except json.JSONDecodeError as exc:
            raise PacketValidationError(f"validation_commands is not valid JSON: {exc}") from exc
    if not isinstance(commands, list) or any(not isinstance(item, str) for item in commands):
        raise PacketValidationError("validation_commands must be a JSON array of command strings")
    return commands


def resolve_repo_path(repo_root: str, target_repo: str) -> str:
    candidate = (Path(repo_root) / target_repo).resolve()
    root = Path(repo_root).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PacketValidationError("target_repo must stay within REPO_ROOT") from exc
    if not candidate.exists():
        raise PacketValidationError(f"target_repo path does not exist: {candidate}")
    return str(candidate)


def fetch_one_queued_packet(conn: psycopg.Connection[Any]) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select *
            from build_packets
            where status = 'queued'
            order by queued_at asc
            for update skip locked
            limit 1
            """
        )
        return cur.fetchone()


def claim_packet(conn: psycopg.Connection[Any], packet_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update build_packets
               set status = 'running',
                   started_at = %s,
                   last_error = null
             where id = %s
            """,
            (utc_now(), packet_id),
        )


def get_project_and_task(conn: psycopg.Connection[Any], packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from projects where id = %s", (packet["project_id"],))
        project = cur.fetchone()
        if not project:
            raise ValueError(f"Project not found: {packet['project_id']}")

        task = None
        if packet.get("task_id"):
            cur.execute("select * from tasks where id = %s", (packet["task_id"],))
            task = cur.fetchone()
        return project, task


def create_execution_run(
    conn: psycopg.Connection[Any],
    packet: dict[str, Any],
    branch: str,
    prompt: str,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into execution_runs (build_packet_id, project_id, task_id, status, codex_prompt, codex_branch)
            values (%s, %s, %s, 'running', %s, %s)
            returning id
            """,
            (packet["id"], packet["project_id"], packet.get("task_id"), prompt, branch),
        )
        row = cur.fetchone()
        return row[0]


def update_task_status(conn: psycopg.Connection[Any], task_id: UUID | None, status: str) -> None:
    if not task_id:
        return
    with conn.cursor() as cur:
        cur.execute("update tasks set status = %s where id = %s", (status, task_id))


def finalize_success(
    conn: psycopg.Connection[Any],
    packet_id: UUID,
    run_id: UUID,
    branch: str,
    codex_out: str,
    codex_err: str,
    codex_code: int,
    validation_results: list[dict[str, Any]],
) -> None:
    finished_at = utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            update build_packets
               set status = 'completed',
                   completed_at = %s,
                   codex_branch = %s
             where id = %s
            """,
            (finished_at, branch, packet_id),
        )
        cur.execute(
            """
            update execution_runs
               set status = 'completed',
                   finished_at = %s,
                   codex_stdout = %s,
                   codex_stderr = %s,
                   codex_exit_code = %s,
                   validation_results = %s
             where id = %s
            """,
            (finished_at, codex_out, codex_err, codex_code, json.dumps(validation_results), run_id),
        )


def finalize_failure(
    conn: psycopg.Connection[Any],
    packet_id: UUID,
    run_id: UUID,
    err: str,
    codex_out: str = "",
    codex_err: str = "",
    codex_code: int | None = None,
    validation_results: list[dict[str, Any]] | None = None,
) -> None:
    finished_at = utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            update build_packets
               set status = 'failed',
                   completed_at = %s,
                   last_error = %s
             where id = %s
            """,
            (finished_at, err[:4000], packet_id),
        )
        cur.execute(
            """
            update execution_runs
               set status = 'failed',
                   finished_at = %s,
                   codex_stdout = %s,
                   codex_stderr = %s,
                   codex_exit_code = %s,
                   validation_results = %s
             where id = %s
            """,
            (
                finished_at,
                codex_out,
                codex_err,
                codex_code,
                json.dumps(validation_results or []),
                run_id,
            ),
        )


def run_validation_commands(commands: list[str], cwd: str, timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cmd in commands:
        code, out, err = run_command(cmd, cwd, timeout_seconds=timeout_seconds)
        results.append(
            {
                "command": cmd,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
                "passed": code == 0,
            }
        )
    return results


def process_one_packet(config: WorkerConfig) -> bool:
    with psycopg.connect(config.db_url) as conn:
        conn.autocommit = False
        packet = fetch_one_queued_packet(conn)
        if not packet:
            conn.commit()
            return False

        claim_packet(conn, packet["id"])
        update_task_status(conn, packet.get("task_id"), "In Progress")
        conn.commit()

        run_id: UUID | None = None
        try:
            validate_packet(packet)
            project, task = get_project_and_task(conn, packet)
            branch = build_branch_name(task, packet)
            prompt = build_codex_prompt(packet, project, task, branch)
            run_id = create_execution_run(conn, packet, branch, prompt)
            conn.commit()

            repo_path = resolve_repo_path(config.repo_root, packet["target_repo"])
            codex_code, codex_out, codex_err = run_codex(
                config.codex_exec_command,
                prompt,
                repo_path,
                branch,
                timeout_seconds=config.command_timeout_seconds,
            )

            commands = parse_validation_commands(packet.get("validation_commands"))
            validation_results = run_validation_commands(
                commands,
                cwd=repo_path,
                timeout_seconds=config.command_timeout_seconds,
            )
            validations_ok = all(item["passed"] for item in validation_results)

            if codex_code == 0 and validations_ok:
                finalize_success(conn, packet["id"], run_id, branch, codex_out, codex_err, codex_code, validation_results)
                update_task_status(conn, packet.get("task_id"), "Review")
            else:
                reason = "Codex execution failed" if codex_code != 0 else "Validation commands failed"
                finalize_failure(
                    conn,
                    packet["id"],
                    run_id,
                    err=reason,
                    codex_out=codex_out,
                    codex_err=codex_err,
                    codex_code=codex_code,
                    validation_results=validation_results,
                )
                update_task_status(conn, packet.get("task_id"), "Blocked")

            conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            if run_id:
                finalize_failure(conn, packet["id"], run_id, err=f"Unhandled worker error: {exc}")
                update_task_status(conn, packet.get("task_id"), "Blocked")
                conn.commit()
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "update build_packets set status = 'failed', last_error = %s where id = %s",
                        (f"Worker setup failure: {exc}"[:4000], packet["id"]),
                    )
                    update_task_status(conn, packet.get("task_id"), "Blocked")
                conn.commit()
            return True


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL is required")

    config = WorkerConfig(
        db_url=db_url,
        poll_seconds=int(os.environ.get("WORKER_POLL_SECONDS", "10")),
        codex_exec_command=os.environ.get(
            "CODEX_EXEC_COMMAND",
            "codex run --prompt-file {prompt_file} --repo {repo_path} --branch {branch}",
        ),
        repo_root=os.environ.get("REPO_ROOT", "/workspace"),
        command_timeout_seconds=int(os.environ.get("COMMAND_TIMEOUT_SECONDS", "1800")),
    )

    run_once = os.environ.get("RUN_ONCE", "false").lower() == "true"
    while True:
        handled = process_one_packet(config)
        if run_once:
            return
        if not handled:
            time.sleep(config.poll_seconds)


if __name__ == "__main__":
    main()
