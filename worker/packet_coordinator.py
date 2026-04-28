#!/usr/bin/env python3
"""Founder OS queue coordinator.

Queues build packets for approved tasks so the execution worker can process them.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass
class CoordinatorConfig:
    db_url: str
    default_target_repo: str
    default_base_branch: str = "main"
    default_validation_commands: list[str] | None = None
    batch_size: int = 25


class CoordinatorError(ValueError):
    """Raised when the coordinator cannot produce a valid build packet."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_validation_commands_env(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    if "\n" in raw_value and not raw_value.strip().startswith("["):
        commands = [line.strip() for line in raw_value.splitlines() if line.strip()]
        return commands
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise CoordinatorError(f"DEFAULT_VALIDATION_COMMANDS must be JSON: {exc}") from exc

    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise CoordinatorError("DEFAULT_VALIDATION_COMMANDS must be a JSON array of strings")

    commands = [item.strip() for item in parsed]
    if any(not item for item in commands):
        raise CoordinatorError("DEFAULT_VALIDATION_COMMANDS cannot contain blank commands")
    return commands


def derive_target_repo(project_repo_link: str | None, fallback_repo: str) -> str:
    if project_repo_link:
        link = project_repo_link.strip()
        github_match = re.match(r"https://github\.com/[^/]+/([^/.]+)(?:\.git)?/?$", link)
        if github_match:
            return github_match.group(1)
        if link and not link.startswith("http"):
            return link
    if not fallback_repo:
        raise CoordinatorError("DEFAULT_TARGET_REPO is required when project.repo_link is missing")
    return fallback_repo


def build_packet_body(task: dict[str, Any]) -> str:
    description = task.get("description") or "No description provided."
    return (
        f"Project: {task['project_name']}\n"
        f"Task: {task['task_title']}\n\n"
        f"Implementation requirements:\n{description}\n"
    )


def fetch_approved_tasks(conn: psycopg.Connection[Any], batch_size: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = 'public'
               and table_name = 'tasks'
               and column_name in ('approved', 'review_status', 'build_packet_id')
            """
        )
        columns = {row[0] for row in cur.fetchall()}

    approval_filter = "coalesce(t.review_status, 'pending') = 'approved'"
    if "approved" in columns:
        approval_filter = "coalesce(t.approved, false) = true"

    packet_link_filter = "true"
    if "build_packet_id" in columns:
        packet_link_filter = "t.build_packet_id is null"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            select t.*, p.project_name, p.repo_link
              from tasks t
              join projects p on p.id = t.project_id
             where {approval_filter}
               and {packet_link_filter}
             order by t.created_at asc
             for update of t skip locked
             limit %s
            """,
            (batch_size,),
        )
        return list(cur.fetchall())


def queue_task_packet(conn: psycopg.Connection[Any], task: dict[str, Any], config: CoordinatorConfig) -> str:
    target_repo = derive_target_repo(task.get("repo_link"), config.default_target_repo)
    packet_body = build_packet_body(task)
    validation_commands = config.default_validation_commands or []

    with conn.cursor() as cur:
        cur.execute(
            """
            insert into build_packets (
              project_id,
              task_id,
              packet_title,
              packet_body,
              target_repo,
              base_branch,
              validation_commands,
              status,
              queued_at
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, 'queued', %s)
            returning id
            """,
            (
                task["project_id"],
                task["id"],
                task["task_title"],
                packet_body,
                target_repo,
                config.default_base_branch,
                json.dumps(validation_commands),
                utc_now(),
            ),
        )
        packet_id = str(cur.fetchone()[0])

        cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = 'public'
               and table_name = 'tasks'
               and column_name in ('build_packet_id', 'packet_generated_at', 'status')
            """
        )
        columns = {row[0] for row in cur.fetchall()}

        set_parts: list[str] = []
        params: list[Any] = []
        if "build_packet_id" in columns:
            set_parts.append("build_packet_id = %s")
            params.append(packet_id)
        if "packet_generated_at" in columns:
            set_parts.append("packet_generated_at = %s")
            params.append(utc_now())
        if "status" in columns:
            set_parts.append("status = 'Queued'")

        if set_parts:
            params.append(task["id"])
            cur.execute(f"update tasks set {', '.join(set_parts)} where id = %s", params)

    return packet_id


def queue_approved_tasks(config: CoordinatorConfig) -> int:
    queued_count = 0
    with psycopg.connect(config.db_url) as conn:
        conn.autocommit = False
        tasks = fetch_approved_tasks(conn, config.batch_size)
        for task in tasks:
            queue_task_packet(conn, task, config)
            queued_count += 1
        conn.commit()
    return queued_count


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL is required")

    config = CoordinatorConfig(
        db_url=db_url,
        default_target_repo=os.environ.get("DEFAULT_TARGET_REPO", ""),
        default_base_branch=os.environ.get("DEFAULT_BASE_BRANCH", "main"),
        default_validation_commands=parse_validation_commands_env(os.environ.get("DEFAULT_VALIDATION_COMMANDS")),
        batch_size=int(os.environ.get("COORDINATOR_BATCH_SIZE", "25")),
    )

    queued = queue_approved_tasks(config)
    print(f"queued_packets={queued}")


if __name__ == "__main__":
    main()
