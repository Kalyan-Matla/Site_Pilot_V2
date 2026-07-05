"""Database access layer.

Two backends, one call-site API:
- SQLite (default) for local dev / Docker / Render — a single file, no setup.
- Postgres (when DATABASE_URL is set) for serverless hosts like Vercel, where
  there's no persistent disk between invocations.

Every router calls conn.execute(sql, params) with sqlite-style '?'
placeholders. PgConnection below translates those transparently so no call
site needs to know which backend is active.
"""
import os
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Vercel's deployed bundle is read-only; only /tmp is writable there.
_ON_VERCEL = bool(os.environ.get("VERCEL"))
_default_data_dir = "/tmp/sitepilot-data" if _ON_VERCEL else str(BASE_DIR / "data")
DATA_DIR = Path(os.environ.get("DATA_DIR", _default_data_dir))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "sitepilot.db"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", DATA_DIR / "uploads"))
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATIONS_PG_DIR = Path(__file__).resolve().parent / "migrations_pg"

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
IS_PG = bool(DATABASE_URL)

_QMARK = re.compile(r"\?")


def _pyformat(sql: str) -> str:
    """Translate sqlite '?' placeholders to psycopg '%s'. Safe: no query in
    this codebase embeds a literal '?' character inside a string."""
    return _QMARK.sub("%s", sql)


class PgRow(dict):
    """Mimics sqlite3.Row: supports both row['col'] and positional row[0]
    (the latter is used by scalar())."""

    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else super().__getitem__(key)


class PgCursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def _cols(self):
        return [d.name for d in self._cur.description]

    def fetchone(self):
        r = self._cur.fetchone()
        return PgRow(self._cols(), r) if r is not None else None

    def fetchall(self):
        cols = self._cols()
        return [PgRow(cols, r) for r in self._cur.fetchall()]


class PgConnection:
    """Wraps a psycopg connection to match the sqlite3.Connection surface
    this codebase relies on: execute/executescript/commit/rollback/close."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(_pyformat(sql), tuple(params))
        return PgCursor(cur)

    def executescript(self, sql):
        # Postgres' simple-query protocol runs multiple ;-separated
        # statements in one call as long as no parameters are bound.
        with self._conn.cursor() as cur:
            cur.execute(sql)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def connect():
    if IS_PG:
        import psycopg

        return PgConnection(psycopg.connect(DATABASE_URL))
    # check_same_thread=False: each connection is request-scoped and used
    # sequentially, but FastAPI's threadpool may hop threads within a request.
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    """FastAPI dependency: one connection per request, commit on success."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        mdir = MIGRATIONS_PG_DIR if IS_PG else MIGRATIONS_DIR
        # Inlined rather than calling now_utc_text(): on a fresh Postgres
        # database this bootstrap table is created before 001_init.sql
        # (which defines that function) has run.
        ts_default = (
            "(to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))"
            if IS_PG
            else "(datetime('now'))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            f"(name TEXT PRIMARY KEY, applied_at TEXT DEFAULT {ts_default})"
        )
        conn.commit()
        applied = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(mdir.glob("*.sql")):
            if path.name in applied:
                continue
            conn.executescript(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (path.name,))
            conn.commit()
    finally:
        conn.close()


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def scalar(conn, sql, params=(), default=0):
    r = conn.execute(sql, params).fetchone()
    v = r[0] if r else None
    return default if v is None else v


def insert(conn, table, data: dict) -> int:
    cols = ", ".join(data)
    ph = ", ".join("?" for _ in data)
    if IS_PG:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph}) RETURNING id", tuple(data.values()))
        return cur.fetchone()["id"]
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", tuple(data.values()))
    return cur.lastrowid


def update(conn, table, rec_id: int, data: dict):
    if not data:
        return
    sets = ", ".join(f"{c} = ?" for c in data)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), rec_id))


def next_number(conn, table, column, prefix) -> str:
    """Sequential document numbers like PO-0007, GRN-0003."""
    n = scalar(conn, f"SELECT COUNT(*) FROM {table}") + 1
    while row(conn, f"SELECT 1 AS x FROM {table} WHERE {column} = ?", (f"{prefix}-{n:04d}",)):
        n += 1
    return f"{prefix}-{n:04d}"
