#!/usr/bin/env python3
"""Preflight checks before running Founder OS coordinator/worker in a live environment."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import psycopg


def check_db(url: str) -> tuple[bool, str]:
    if "[YOUR-PASSWORD]" in url or "<password>" in url.lower():
        return False, "database URL still contains a password placeholder"
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
        return True, "database connection OK"
    except Exception as exc:  # noqa: BLE001
        return False, f"database connection failed: {exc}"


def check_repo_paths(repo_root: str, repo_map_raw: str | None) -> tuple[bool, str]:
    missing: list[str] = []
    root = Path(repo_root)
    if not root.exists():
        missing.append(str(root))

    if repo_map_raw:
        try:
            repo_map = json.loads(repo_map_raw)
        except json.JSONDecodeError as exc:
            return False, f"REPO_MAP_JSON is invalid JSON: {exc}"
        for name, path in repo_map.items():
            if not Path(path).exists():
                missing.append(f"{name}:{path}")

    if missing:
        return False, f"missing repo paths: {', '.join(missing)}"
    return True, "repo paths OK"


def check_binary(name: str) -> tuple[bool, str]:
    if shutil.which(name):
        return True, f"{name} found"
    return False, f"{name} not found in PATH"


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL is required")

    repo_root = os.environ.get("REPO_ROOT", "/workspace")
    repo_map_raw = os.environ.get("REPO_MAP_JSON")
    codex_command = os.environ.get("CODEX_EXEC_COMMAND", "codex")
    codex_binary = codex_command.split()[0]

    checks = [
        ("database", *check_db(db_url)),
        ("repos", *check_repo_paths(repo_root, repo_map_raw)),
        ("codex", *check_binary(codex_binary)),
        ("git", *check_binary("git")),
    ]

    failures = [name for name, ok, _ in checks if not ok]
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")

    if failures:
        raise SystemExit(f"Preflight failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
