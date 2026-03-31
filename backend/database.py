"""
Unified database layer — auto-switches between SQLite (local dev) and PostgreSQL (production).

If DATABASE_URL env var is set → uses PostgreSQL (Supabase, etc.)
Otherwise → falls back to SQLite in local file.

Usage is identical in both modes:
    db = database.get_db()
    rows = db.execute("SELECT ...").fetchall()
    row["column_name"]   # works in both modes
    db.close()
"""

import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "ppc_intel.db")))

# ── PostgreSQL wrapper ────────────────────────────────────────

class PGCursor:
    """Wraps psycopg2 cursor to mimic sqlite3 dict-row interface."""

    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, sql: str, params=None):
        sql = _pg_sql(sql)
        self._cur.execute(sql, params or ())
        return self

    def executemany(self, sql: str, seq):
        sql = _pg_sql(sql)
        self._cur.executemany(sql, seq)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return _DictRow(dict(zip(cols, row)))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [_DictRow(dict(zip(cols, r))) for r in rows]

    @property
    def lastrowid(self):
        self._cur.execute("SELECT lastval()")
        return self._cur.fetchone()[0]

    def close(self):
        self._cur.close()


class _DictRow(dict):
    """Row that supports both dict['key'] and row.key access."""
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)


class PGConnection:
    """Wraps psycopg2 connection to mimic sqlite3 connection interface."""

    def __init__(self, conn):
        self._conn = conn
        self._cur = PGCursor(conn.cursor())

    def execute(self, sql: str, params=None):
        return self._cur.execute(sql, params)

    def executemany(self, sql: str, seq):
        return self._cur.executemany(sql, seq)

    def executescript(self, script: str):
        """Execute multiple statements. PostgreSQL doesn't have this natively."""
        for stmt in _split_statements(script):
            stmt = stmt.strip()
            if stmt:
                self._cur.execute(stmt)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._cur.close()
        self._conn.close()

    def cursor(self):
        return self._cur

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, _):
        pass  # no-op, PGConnection always returns dicts


def _split_statements(script: str) -> list:
    """Split SQL script on semicolons, ignoring those inside strings."""
    statements = []
    current = []
    in_string = False
    for char in script:
        if char == "'" and not in_string:
            in_string = True
        elif char == "'" and in_string:
            in_string = False
        if char == ";" and not in_string:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def _pg_sql(sql: str) -> str:
    """Convert SQLite-flavoured SQL to PostgreSQL-compatible SQL."""
    import re

    # AUTOINCREMENT → SERIAL (handle in CREATE TABLE)
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY", sql, flags=re.IGNORECASE)
    sql = re.sub(r"INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY", sql, flags=re.IGNORECASE)

    # datetime('now') → NOW()
    sql = re.sub(r"datetime\('now'\)", "NOW()", sql, flags=re.IGNORECASE)

    # strftime('%Y-W%W', col) → to_char(col::date, 'IYYY-"W"IW')
    def replace_strftime(m):
        fmt = m.group(1)
        col = m.group(2).strip()
        if "%Y-W%W" in fmt or "%Y-W%V" in fmt:
            return f"to_char({col}::date, 'IYYY-\"W\"IW')"
        if "%Y-%m-%d" in fmt:
            return f"to_char({col}::date, 'YYYY-MM-DD')"
        return m.group(0)

    sql = re.sub(r"strftime\('([^']+)',\s*([^)]+)\)", replace_strftime, sql, flags=re.IGNORECASE)

    # SQLite ? placeholders → PostgreSQL %s
    sql = sql.replace("?", "%s")

    # PRAGMA → skip
    if sql.strip().upper().startswith("PRAGMA"):
        return "SELECT 1"

    return sql


# ── SQLite wrapper (adds dict-like row factory) ───────────────

class SQLiteConnection:
    """Thin wrapper around sqlite3 connection with dict rows."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

    def execute(self, sql: str, params=None):
        return self._conn.execute(sql, params or ())

    def executemany(self, sql: str, seq):
        return self._conn.executemany(sql, seq)

    def executescript(self, script: str):
        return self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()


# ── Public API ────────────────────────────────────────────────

_POOLER_REGIONS = [
    "us-east-1", "us-west-1", "us-west-2",
    "eu-central-1", "eu-west-1",
    "ap-southeast-1", "ap-northeast-1", "ap-south-1",
    "sa-east-1", "ca-central-1",
]

# Cache the working pooler so we don't re-detect on every request
_pooler_cache: dict = {}


def _find_supabase_pooler(project_ref: str, password: str, dbname: str) -> dict:
    """Try each Supabase pooler region and return params for the first that connects."""
    import psycopg2
    for region in _POOLER_REGIONS:
        host = f"aws-0-{region}.pooler.supabase.com"
        params = dict(
            host=host,
            port=6543,
            user=f"postgres.{project_ref}",
            password=password,
            dbname=dbname,
            sslmode="require",
            connect_timeout=5,
        )
        try:
            test = psycopg2.connect(**params)
            test.close()
            return params
        except Exception:
            continue
    raise RuntimeError(
        "Could not connect to any Supabase pooler region. "
        "Check DATABASE_URL, password, and that the Supabase project is active."
    )


def get_db():
    """Return a database connection. Caller must call .close() when done."""
    if DATABASE_URL:
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError("psycopg2-binary not installed. Run: pip install psycopg2-binary")

        import re
        from urllib.parse import urlparse

        parsed = urlparse(DATABASE_URL)
        hostname = parsed.hostname or ""
        port = parsed.port or 5432
        user = parsed.username
        password = parsed.password
        dbname = (parsed.path or "/postgres").lstrip("/") or "postgres"

        # Supabase direct-connection hosts (db.*.supabase.co) are IPv6-only.
        # HuggingFace Spaces free tier has no IPv6 outbound.
        # Auto-detect the correct IPv4 pooler for this project.
        m = re.match(r"^db\.([a-z0-9]+)\.supabase\.co$", hostname)
        if m:
            project_ref = m.group(1)
            if project_ref not in _pooler_cache:
                _pooler_cache[project_ref] = _find_supabase_pooler(project_ref, password, dbname)
            conn_params = dict(_pooler_cache[project_ref])
        else:
            # Non-Supabase or already-pooler URL — connect as-is
            conn_params = dict(
                host=hostname,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                sslmode="require",
                connect_timeout=15,
            )

        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False
        return PGConnection(conn)
    else:
        conn = sqlite3.connect(str(DB_PATH))
        return SQLiteConnection(conn)


def _add_column_safe(conn, table: str, column: str, col_type: str = "TEXT"):
    """Add a column if it doesn't exist — works for both SQLite and PostgreSQL."""
    if DATABASE_URL:
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            )
        except Exception:
            pass
    else:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass


def init_db():
    """Create all tables. Idempotent — safe to call on every startup."""
    conn = get_db()

    # Core tables
    _create_tables(conn)

    # Migrations
    _add_column_safe(conn, "uploads", "date_start", "TEXT")
    _add_column_safe(conn, "uploads", "date_end", "TEXT")

    conn.commit()
    conn.close()


def _create_tables(conn):
    stmts = [
        """CREATE TABLE IF NOT EXISTS uploads (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            report_type TEXT NOT NULL,
            rows_count INTEGER,
            date_start TEXT,
            date_end TEXT,
            uploaded_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS keyword_data (
            id SERIAL PRIMARY KEY,
            upload_id INTEGER REFERENCES uploads(id),
            search_term TEXT,
            campaign TEXT,
            ad_group TEXT,
            match_type TEXT,
            impressions REAL DEFAULT 0,
            clicks REAL DEFAULT 0,
            spend REAL DEFAULT 0,
            sales REAL DEFAULT 0,
            orders REAL DEFAULT 0,
            acos REAL DEFAULT 0,
            roas REAL DEFAULT 0,
            ctr REAL DEFAULT 0,
            cpc REAL DEFAULT 0,
            cvr REAL DEFAULT 0,
            status TEXT,
            report_date TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS business_data (
            id SERIAL PRIMARY KEY,
            upload_id INTEGER REFERENCES uploads(id),
            asin TEXT,
            title TEXT,
            sessions REAL DEFAULT 0,
            units_ordered REAL DEFAULT 0,
            ordered_product_sales REAL DEFAULT 0,
            report_date TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS competitor_prices (
            id SERIAL PRIMARY KEY,
            asin TEXT NOT NULL,
            title TEXT,
            price REAL,
            currency TEXT DEFAULT '$',
            checked_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS sales_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_date TEXT NOT NULL,
            asin TEXT NOT NULL DEFAULT '__total__',
            units_ordered REAL DEFAULT 0,
            ordered_product_sales REAL DEFAULT 0,
            sessions REAL DEFAULT 0,
            order_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            UNIQUE(snapshot_date, asin)
        )""",
        """CREATE TABLE IF NOT EXISTS competitor_keyword_intel (
            id SERIAL PRIMARY KEY,
            keyword TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            competition_level TEXT,
            competition_score INTEGER,
            market_insight TEXT,
            competitor_strategies TEXT,
            keyword_gaps TEXT,
            long_tail_opportunities TEXT,
            negative_suggestions TEXT,
            bid_recommendation TEXT,
            action_plan TEXT,
            raw_response TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS api_sync_log (
            id SERIAL PRIMARY KEY,
            sync_type TEXT NOT NULL,
            status TEXT NOT NULL,
            records_synced INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS facebook_spend (
            id SERIAL PRIMARY KEY,
            spend_date TEXT NOT NULL,
            campaign_name TEXT NOT NULL DEFAULT '__total__',
            spend REAL DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            purchases INTEGER DEFAULT 0,
            purchase_value REAL DEFAULT 0,
            reach INTEGER DEFAULT 0,
            synced_at TEXT,
            UNIQUE(spend_date, campaign_name)
        )""",
        """CREATE TABLE IF NOT EXISTS facebook_creatives (
            id SERIAL PRIMARY KEY,
            ad_id TEXT NOT NULL,
            ad_name TEXT,
            campaign_name TEXT,
            adset_name TEXT,
            spend REAL DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            purchases INTEGER DEFAULT 0,
            purchase_value REAL DEFAULT 0,
            roas REAL DEFAULT 0,
            cpa REAL DEFAULT 0,
            ctr REAL DEFAULT 0,
            cpc REAL DEFAULT 0,
            reach INTEGER DEFAULT 0,
            thumbnail_url TEXT,
            title TEXT,
            body TEXT,
            image_url TEXT,
            synced_at TEXT,
            period_days INTEGER DEFAULT 14
        )""",
        """CREATE TABLE IF NOT EXISTS shopify_daily (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL UNIQUE,
            revenue REAL DEFAULT 0,
            order_count INTEGER DEFAULT 0,
            new_customers INTEGER DEFAULT 0,
            avg_order_value REAL DEFAULT 0,
            synced_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS shopify_utm_attribution (
            id SERIAL PRIMARY KEY,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            source TEXT,
            medium TEXT,
            campaign TEXT,
            orders INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            new_customers INTEGER DEFAULT 0,
            synced_at TEXT
        )""",
    ]

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_kw_upload  ON keyword_data(upload_id)",
        "CREATE INDEX IF NOT EXISTS idx_kw_status  ON keyword_data(status)",
        "CREATE INDEX IF NOT EXISTS idx_kw_term    ON keyword_data(search_term)",
        "CREATE INDEX IF NOT EXISTS idx_kw_date    ON keyword_data(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_biz_date   ON business_data(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_comp_asin  ON competitor_prices(asin, checked_at)",
        "CREATE INDEX IF NOT EXISTS idx_sales_date ON sales_snapshots(snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_sales_asin ON sales_snapshots(asin)",
        "CREATE INDEX IF NOT EXISTS idx_fb_date    ON facebook_spend(spend_date)",
        "CREATE INDEX IF NOT EXISTS idx_shop_date  ON shopify_daily(date)",
    ]

    for stmt in stmts + indexes:
        try:
            conn.execute(stmt)
        except Exception as e:
            # On PostgreSQL, "already exists" errors are OK
            if "already exists" not in str(e).lower():
                raise


# init_db() is called from main.py startup event, NOT at import time.
# Calling it here would block module import and crash the app if DB is unreachable.
