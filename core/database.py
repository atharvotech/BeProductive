"""
Focus Engine Pro — SQLite Database Layer
All screen time, web time, token, and settings data.
"""

import os
import sys
import sqlite3
import datetime
import threading

def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(_base_dir(), "core", "data.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Thread-local SQLite connection (SQLite is not thread-safe by default)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def _retry_write(fn, max_retries=3):
    """Retry a database write operation if the DB is locked/busy."""
    import time as _time
    for attempt in range(max_retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e) or "disk I/O" in str(e):
                if attempt < max_retries - 1:
                    _time.sleep(0.5 * (attempt + 1))
                    continue
            raise


def init_db():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS screen_time (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            date        TEXT    NOT NULL,
            hour        INTEGER NOT NULL,
            app_name    TEXT    NOT NULL,
            window_title TEXT   NOT NULL DEFAULT '',
            category    TEXT    NOT NULL DEFAULT 'other',
            seconds     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS web_time (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            date        TEXT    NOT NULL,
            hour        INTEGER NOT NULL,
            domain      TEXT    NOT NULL,
            url         TEXT    NOT NULL DEFAULT '',
            page_title  TEXT    NOT NULL DEFAULT '',
            category    TEXT    NOT NULL DEFAULT 'other',
            seconds     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            date        TEXT    NOT NULL,
            earned      INTEGER NOT NULL DEFAULT 0,
            spent       INTEGER NOT NULL DEFAULT 0,
            reason      TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT    PRIMARY KEY,
            value       TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            date            TEXT PRIMARY KEY,
            total_screen_sec INTEGER NOT NULL DEFAULT 0,
            study_sec       INTEGER NOT NULL DEFAULT 0,
            entertainment_sec INTEGER NOT NULL DEFAULT 0,
            gaming_sec      INTEGER NOT NULL DEFAULT 0,
            idle_sec        INTEGER NOT NULL DEFAULT 0,
            social_sec      INTEGER NOT NULL DEFAULT 0,
            tokens_earned   INTEGER NOT NULL DEFAULT 0,
            tokens_spent    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS killed_processes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            process_name TEXT   NOT NULL,
            reason      TEXT    NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_screen_date ON screen_time(date);
        CREATE INDEX IF NOT EXISTS idx_screen_app  ON screen_time(app_name);
        CREATE INDEX IF NOT EXISTS idx_web_date    ON web_time(date);
        CREATE INDEX IF NOT EXISTS idx_web_domain  ON web_time(domain);
        CREATE INDEX IF NOT EXISTS idx_tokens_date ON tokens(date);
    """)
    # Seed default settings
    defaults = {
        "focus_mode": "off",            # off | on | auto
        "auto_focus_threshold_min": "30",
        "token_earn_rate": "30",        # tokens per hour of study
        "token_deduct_rate": "15",      # tokens per hour of gaming
        "dns_blocking": "on",
        "blocked_keywords": "reels,shorts,tiktok,gaming,porn",
        "whitelisted_apps": "steam.exe,steamwebhelper.exe,DesktopMate.exe,VTube Studio.exe",
        "whitelisted_channels": "",
        "blocked_apps_custom": "",
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v)
        )
    conn.commit()


# ─── Screen Time ──────────────────────────────────────────────────────────

def log_screen_time(app_name: str, window_title: str, category: str, seconds: int):
    now = datetime.datetime.now()
    def _write():
        conn = _get_conn()
        conn.execute(
            """INSERT INTO screen_time(date, hour, app_name, window_title, category, seconds)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d"), now.hour, app_name, window_title, category, seconds),
        )
        conn.commit()
    _retry_write(_write)


def get_screen_time_stats(date: str) -> list:
    """Aggregate screen time by app for a given date."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT app_name, category, SUM(seconds) as total_sec
           FROM screen_time WHERE date = ?
           GROUP BY app_name ORDER BY total_sec DESC""",
        (date,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_hourly_breakdown(date: str) -> list:
    """24-element list with {hour, study, gaming, social, entertainment, other, idle}."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT hour, category, SUM(seconds) as total_sec
           FROM screen_time WHERE date = ?
           GROUP BY hour, category ORDER BY hour""",
        (date,),
    ).fetchall()
    # Build 24-hour structure
    hourly = []
    for h in range(24):
        entry = {"hour": h, "study": 0, "gaming": 0, "social": 0,
                 "entertainment": 0, "other": 0, "idle": 0, "productivity": 0}
        hourly.append(entry)
    for r in rows:
        h = r["hour"]
        cat = r["category"]
        if cat in hourly[h]:
            hourly[h][cat] += r["total_sec"]
        else:
            hourly[h]["other"] += r["total_sec"]
    return hourly


def get_top_apps(date: str, limit: int = 10) -> list:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT app_name, category, SUM(seconds) as total_sec
           FROM screen_time WHERE date = ?
           GROUP BY app_name ORDER BY total_sec DESC LIMIT ?""",
        (date, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_category_totals(date: str) -> dict:
    """Return total seconds per category for a day.
    Merges screen_time (desktop) + web_time (extension) for a complete picture.
    """
    conn = _get_conn()
    # Desktop app screen time
    rows = conn.execute(
        """SELECT category, SUM(seconds) as total_sec
           FROM screen_time WHERE date = ?
           GROUP BY category""",
        (date,),
    ).fetchall()
    result = {"study": 0, "gaming": 0, "social": 0,
              "entertainment": 0, "other": 0, "idle": 0, "productivity": 0}
    for r in rows:
        cat = r["category"]
        if cat in result:
            result[cat] += r["total_sec"]
        else:
            result["other"] += r["total_sec"]

    # Also add web-based study time from the Chrome extension
    web_rows = conn.execute(
        """SELECT category, SUM(seconds) as total_sec
           FROM web_time WHERE date = ? AND category != 'blocked'
           GROUP BY category""",
        (date,),
    ).fetchall()
    for r in web_rows:
        cat = r["category"]
        if cat in result:
            result[cat] += r["total_sec"]
        else:
            result["other"] += r["total_sec"]

    return result


def get_monthly_stats(year: int, month: int) -> list:
    """Daily totals for a given month."""
    conn = _get_conn()
    prefix = f"{year}-{month:02d}"
    rows = conn.execute(
        """SELECT date, category, SUM(seconds) as total_sec
           FROM screen_time WHERE date LIKE ?
           GROUP BY date, category ORDER BY date""",
        (prefix + "%",),
    ).fetchall()
    # Pivot
    days = {}
    for r in rows:
        d = r["date"]
        if d not in days:
            days[d] = {"date": d, "study": 0, "gaming": 0, "social": 0,
                       "entertainment": 0, "other": 0, "idle": 0, "productivity": 0, "total": 0}
        cat = r["category"]
        sec = r["total_sec"]
        if cat in days[d]:
            days[d][cat] += sec
        else:
            days[d]["other"] += sec
        days[d]["total"] += sec
    return list(days.values())


def get_yearly_stats(year: int) -> list:
    """Monthly totals for a given year."""
    conn = _get_conn()
    prefix = f"{year}"
    rows = conn.execute(
        """SELECT substr(date,1,7) as month, category, SUM(seconds) as total_sec
           FROM screen_time WHERE date LIKE ?
           GROUP BY month, category ORDER BY month""",
        (prefix + "%",),
    ).fetchall()
    months = {}
    for r in rows:
        m = r["month"]
        if m not in months:
            months[m] = {"month": m, "study": 0, "gaming": 0, "social": 0,
                         "entertainment": 0, "other": 0, "idle": 0, "productivity": 0, "total": 0}
        cat = r["category"]
        sec = r["total_sec"]
        if cat in months[m]:
            months[m][cat] += sec
        else:
            months[m]["other"] += sec
        months[m]["total"] += sec
    return list(months.values())


# ─── Web Time ─────────────────────────────────────────────────────────────

def log_web_time(domain: str, url: str, page_title: str, category: str, seconds: int):
    now = datetime.datetime.now()
    def _write():
        conn = _get_conn()
        conn.execute(
            """INSERT INTO web_time(date, hour, domain, url, page_title, category, seconds)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d"), now.hour, domain, url, page_title, category, seconds),
        )
        conn.commit()
    _retry_write(_write)


def get_web_time_stats(date: str) -> list:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT domain, category, SUM(seconds) as total_sec
           FROM web_time WHERE date = ?
           GROUP BY domain ORDER BY total_sec DESC""",
        (date,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_web_blocked_log(date: str) -> list:
    """Return blocked web page attempts (logged as category='blocked')."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT timestamp, domain, url, page_title
           FROM web_time WHERE date = ? AND category = 'blocked'
           ORDER BY timestamp DESC LIMIT 50""",
        (date,),
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Tokens ───────────────────────────────────────────────────────────────

def get_token_balance() -> int:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(earned) - SUM(spent), 0) as balance FROM tokens"
    ).fetchone()
    return row["balance"] if row else 0


def earn_tokens(amount: int, reason: str = "study"):
    now = datetime.datetime.now()
    def _write():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO tokens(date, earned, spent, reason) VALUES(?, ?, 0, ?)",
            (now.strftime("%Y-%m-%d"), amount, reason),
        )
        conn.commit()
    _retry_write(_write)


def spend_tokens(amount: int, reason: str = "gaming"):
    now = datetime.datetime.now()
    def _write():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO tokens(date, earned, spent, reason) VALUES(?, 0, ?, ?)",
            (now.strftime("%Y-%m-%d"), amount, reason),
        )
        conn.commit()
    _retry_write(_write)


def get_token_history(date: str = None) -> list:
    conn = _get_conn()
    if date:
        rows = conn.execute(
            "SELECT * FROM tokens WHERE date = ? ORDER BY timestamp DESC", (date,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tokens ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Settings ─────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value)
    )
    conn.commit()


def get_all_settings() -> dict:
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ─── Daily Summary ────────────────────────────────────────────────────────

def update_daily_summary(date: str):
    """Recompute and upsert the daily summary row."""
    def _write():
        conn = _get_conn()
        cats = get_category_totals(date)
        total = sum(cats.values())
        token_row = conn.execute(
            "SELECT COALESCE(SUM(earned),0) as e, COALESCE(SUM(spent),0) as s FROM tokens WHERE date=?",
            (date,),
        ).fetchone()
        conn.execute(
            """INSERT OR REPLACE INTO daily_summary
               (date, total_screen_sec, study_sec, entertainment_sec, gaming_sec, idle_sec, social_sec, tokens_earned, tokens_spent)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, total, cats["study"], cats["entertainment"], cats["gaming"],
             cats["idle"], cats["social"], token_row["e"], token_row["s"]),
        )
        conn.commit()
    _retry_write(_write)


def get_streak() -> int:
    """Count consecutive days with study time > 0 ending at today."""
    conn = _get_conn()
    today = datetime.date.today()
    streak = 0
    for i in range(365):
        d = (today - datetime.timedelta(days=i)).isoformat()
        row = conn.execute(
            "SELECT SUM(seconds) as s FROM screen_time WHERE date=? AND category='study'",
            (d,),
        ).fetchone()
        if row and row["s"] and row["s"] > 0:
            streak += 1
        else:
            if i == 0:
                continue  # today might not have study yet
            break
    return streak


# ─── Killed Processes Log ─────────────────────────────────────────────────

def log_killed_process(process_name: str, reason: str = ""):
    def _write():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO killed_processes(process_name, reason) VALUES(?, ?)",
            (process_name, reason),
        )
        conn.commit()
    _retry_write(_write)


# ─── Recent Web Activity ─────────────────────────────────────────────────

def get_recent_web_activity(limit: int = 20) -> list:
    """Return the most recent web activity entries (newest first)."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT timestamp, domain, url, page_title, category, seconds
           FROM web_time
           WHERE category != 'blocked'
           ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_spotify_screen_time(date: str) -> int:
    """Return total seconds of Spotify usage for a given date."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT COALESCE(SUM(seconds), 0) as total_sec
           FROM screen_time WHERE date = ? AND LOWER(app_name) = 'spotify.exe'""",
        (date,),
    ).fetchone()
    return row["total_sec"] if row else 0
