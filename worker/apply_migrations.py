#!/usr/bin/env python3
"""Apply Founder OS SQL migrations in filename order."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


def migration_files(repo_root: Path) -> list[Path]:
    migration_dir = repo_root / "sql" / "migrations"
    return sorted(path for path in migration_dir.glob("*.sql") if path.is_file())


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL is required")

    repo_root = Path(__file__).resolve().parents[1]
    files = migration_files(repo_root)
    if not files:
        raise SystemExit("No migration files found under sql/migrations")

    with psycopg.connect(db_url) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            for file in files:
                sql = file.read_text()
                cur.execute(sql)
                print(f"applied={file.relative_to(repo_root)}")
        conn.commit()


if __name__ == "__main__":
    main()
