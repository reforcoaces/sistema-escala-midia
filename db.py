"""Persistência SQLite para voluntários, disponibilidade e escala."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "escala.sqlite"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    c = get_conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS volunteer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                birth_date TEXT
            );

            CREATE TABLE IF NOT EXISTS volunteer_area (
                volunteer_id INTEGER NOT NULL REFERENCES volunteer(id) ON DELETE CASCADE,
                area TEXT NOT NULL,
                PRIMARY KEY (volunteer_id, area)
            );

            CREATE TABLE IF NOT EXISTS extra_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                event_date TEXT NOT NULL,
                label TEXT,
                event_time TEXT,
                UNIQUE (year, month, event_date)
            );

            CREATE TABLE IF NOT EXISTS availability (
                volunteer_id INTEGER NOT NULL REFERENCES volunteer(id) ON DELETE CASCADE,
                event_date TEXT NOT NULL,
                available INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (volunteer_id, event_date)
            );

            CREATE TABLE IF NOT EXISTS assignment (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                event_date TEXT NOT NULL,
                area TEXT NOT NULL,
                volunteer_id INTEGER REFERENCES volunteer(id) ON DELETE SET NULL,
                PRIMARY KEY (year, month, event_date, area)
            );

            CREATE TABLE IF NOT EXISTS month_options (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                include_training INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (year, month)
            );

            CREATE TABLE IF NOT EXISTS app_setting (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS birthday_notification_sent (
                volunteer_id INTEGER NOT NULL REFERENCES volunteer(id) ON DELETE CASCADE,
                year INTEGER NOT NULL,
                PRIMARY KEY (volunteer_id, year)
            );
            """
        )
        _migrate_schema(conn)


def _migrate_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(extra_event)").fetchall()}
    if "event_time" not in cols:
        conn.execute("ALTER TABLE extra_event ADD COLUMN event_time TEXT")
    vcols = {r[1] for r in conn.execute("PRAGMA table_info(volunteer)").fetchall()}
    if "birth_date" not in vcols:
        conn.execute("ALTER TABLE volunteer ADD COLUMN birth_date TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_setting (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS birthday_notification_sent (
            volunteer_id INTEGER NOT NULL REFERENCES volunteer(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            PRIMARY KEY (volunteer_id, year)
        )
        """
    )
