from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

REQUIRED_TABLES = [
    "brands",
    "sources",
    "runs",
    "raw_files",
    "canonical_search",
    "canonical_paid",
    "canonical_organic",
    "canonical_web",
    "canonical_crm",
    "canonical_plan",
    "review_items",
    "decision_ledger",
    "ai_labels",
    "outputs"
]


def get_default_db_url() -> str:
    """Return database URL from environment or default to local sqlite."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not url:
        db_path = Path(os.getcwd()) / "howl.db"
        url = f"sqlite:///{db_path}"
    return url


def get_engine(db_url: Optional[str] = None) -> Engine:
    """Create and return a SQLAlchemy engine."""
    url = db_url or get_default_db_url()
    # Normalize postgres url if using postgres:// prefix (older Heroku/Supabase format)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


def _adapt_postgres_sql_for_sqlite(sql: str) -> str:
    """Translate PostgreSQL DDL dialect to SQLite dialect for local test runs."""
    sql = re.sub(r"JSONB NOT NULL DEFAULT '\s*\{\}\s*'::jsonb", "TEXT NOT NULL DEFAULT '{}'", sql, flags=re.IGNORECASE)
    sql = re.sub(r"JSONB", "TEXT", sql, flags=re.IGNORECASE)
    sql = re.sub(r"TIMESTAMPTZ", "TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"DOUBLE PRECISION", "REAL", sql, flags=re.IGNORECASE)
    sql = re.sub(r"BIGINT", "INTEGER", sql, flags=re.IGNORECASE)
    sql = re.sub(r"BOOLEAN NOT NULL DEFAULT FALSE", "INTEGER NOT NULL DEFAULT 0", sql, flags=re.IGNORECASE)
    sql = re.sub(r"BOOLEAN NOT NULL DEFAULT TRUE", "INTEGER NOT NULL DEFAULT 1", sql, flags=re.IGNORECASE)
    sql = re.sub(r"BOOLEAN", "INTEGER", sql, flags=re.IGNORECASE)
    sql = re.sub(r"now\(\)", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    return sql


def run_migrations(engine: Optional[Engine] = None) -> List[str]:
    """Execute all SQL migration scripts in order."""
    if engine is None:
        engine = get_engine()

    migrations_dir = Path(__file__).parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    applied = []

    is_sqlite = engine.dialect.name == "sqlite"

    with engine.begin() as conn:
        for m_file in migration_files:
            raw_sql = m_file.read_text(encoding="utf-8")
            if is_sqlite:
                exec_sql = _adapt_postgres_sql_for_sqlite(raw_sql)
            else:
                exec_sql = raw_sql

            statements = [s.strip() for s in exec_sql.split(";") if s.strip()]
            for stmt in statements:
                conn.execute(text(stmt))
            applied.append(m_file.name)

    return applied


def check_tables_exist(engine: Optional[Engine] = None) -> Dict[str, bool]:
    """Inspect the database and verify the presence of all required platform tables."""
    if engine is None:
        engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    return {tbl: (tbl in existing_tables) for tbl in REQUIRED_TABLES}


def all_required_tables_exist(engine: Optional[Engine] = None) -> bool:
    """Return True if every required platform table exists in the target database."""
    status = check_tables_exist(engine)
    return all(status.values())
