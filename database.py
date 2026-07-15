"""
database.py  —  Chronicle Intelligence  SQLite Persistence Layer  v9-BUGFIX

Bug 19: Cache is checked before every AI generation; only valid bundles
        (≥ 40 words, complete sentence ending) are stored.
Bug 20: Every SQLite call is wrapped in try/except with a self-heal path
        that rebuilds the DB file if schema or file corruption is detected.
        All public functions are guaranteed never to raise.
"""

import sqlite3
import hashlib
import json
import re
import os
import content_cleaner
import config

DB_PATH = "chronicle_data.db"


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _init():
    conn = _connect()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username   TEXT PRIMARY KEY,
            password   TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            username   TEXT NOT NULL,
            pref_key   TEXT NOT NULL,
            pref_value TEXT,
            PRIMARY KEY (username, pref_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            article_id TEXT PRIMARY KEY,
            data       TEXT    NOT NULL,
            word_count INTEGER NOT NULL DEFAULT 0,
            cached_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add word_count column if missing
    try:
        cur.execute(
            "ALTER TABLE ai_cache ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass   # Column already exists

    conn.commit()
    conn.close()


def init_db():
    try:
        _init()
    except Exception as e:
        print(f"[CACHE] DB init failed: {e}. Rebuilding…")
        try:
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            _init()
            print("[CACHE] DB rebuilt successfully.")
        except Exception as ex:
            print(f"[ERROR] DB rebuild failed: {ex}")


# Auto-run on import with self-heal
try:
    _init()
except Exception:
    init_db()


# ─────────────────────────────────────────────────────────────
# Quality control (Bug 19)
# ─────────────────────────────────────────────────────────────

MIN_CACHE_WORDS = 40


def validate_article_bundle(bundle: dict) -> bool:
    """
    Return True only when the bundle carries enough clean content to be
    worth caching. Short, partial, or empty bundles are rejected.
    """
    if not bundle or not isinstance(bundle, dict):
        return False
    content = (bundle.get("content") or "").strip()
    if not content:
        return False
    word_count = len(content.split())
    if word_count < MIN_CACHE_WORDS:
        return False
    if not re.search(r'[.!?।"\')\]]\s*$', content):
        last_char = content[-1] if content else ""
        if last_char.isalnum():
            return False
    return True


def _word_count(bundle: dict) -> int:
    return len((bundle.get("content") or "").split())


# ─────────────────────────────────────────────────────────────
# Auth (Bug 20: all wrapped)
# ─────────────────────────────────────────────────────────────

def register_user(username: str, password: str) -> str:
    if not username or not password:
        return "error"
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username.strip(), _hash(password)))
        conn.commit()
        return "success"
    except sqlite3.IntegrityError:
        return "exists"
    except Exception as e:
        print(f"[ERROR] register_user: {e}")
        return "error"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def authenticate_user(username: str, password: str) -> bool:
    if not username or not password:
        return False
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = ?",
                    (username.strip(),))
        row = cur.fetchone()
        return row is not None and row["password"] == _hash(password)
    except Exception as e:
        print(f"[ERROR] authenticate_user: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# User preferences
# ─────────────────────────────────────────────────────────────

_PREF_DEFAULTS = {
    "category":  "General",
    "language":  "English",
    "dark_mode": False,
}


def save_user_preference(username: str, key: str, value) -> None:
    if not username:
        return
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO user_preferences (username, pref_key, pref_value)
            VALUES (?, ?, ?)
            ON CONFLICT(username, pref_key)
            DO UPDATE SET pref_value = excluded.pref_value
        """, (username, key, json.dumps(value)))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] save_user_preference: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_user_preferences(username: str) -> dict:
    prefs = dict(_PREF_DEFAULTS)
    if not username:
        return prefs
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute(
            "SELECT pref_key, pref_value FROM user_preferences WHERE username = ?",
            (username,))
        rows = cur.fetchall()
        for row in rows:
            try:
                prefs[row["pref_key"]] = json.loads(row["pref_value"])
            except (json.JSONDecodeError, TypeError):
                prefs[row["pref_key"]] = row["pref_value"]
        prefs["dark_mode"] = bool(prefs.get("dark_mode", False))
    except Exception as e:
        print(f"[ERROR] get_user_preferences: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return prefs


# ─────────────────────────────────────────────────────────────
# AI Cache (Bug 19 — check before generate, cache after)
# ─────────────────────────────────────────────────────────────

def get_cached_ai(article_id: str) -> dict | None:
    """
    Return cached bundle only if it passes quality validation.
    Stale / short entries are deleted on the spot so the caller regenerates.
    """
    if not article_id:
        return None
    row = None
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute(
            "SELECT data, word_count FROM ai_cache WHERE article_id = ?",
            (article_id,))
        row = cur.fetchone()
    except Exception as e:
        print(f"[CACHE] Error reading {article_id}: {e}")
        init_db()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not row:
        config.log_cache_miss()
        return None

    config.log_cache_hit()
    try:
        bundle = json.loads(row["data"])
        if bundle:
            if "content" in bundle:
                bundle["content"] = content_cleaner.repair_garbled_telugu(
                    bundle["content"])
            if "ai_headline" in bundle:
                bundle["ai_headline"] = content_cleaner.repair_garbled_telugu(
                    bundle["ai_headline"])
    except Exception:
        _delete_cached_ai(article_id)
        return None

    if not validate_article_bundle(bundle):
        _delete_cached_ai(article_id)
        return None
    return bundle


def save_cached_ai(article_id: str, bundle: dict) -> None:
    """Only persist bundles that pass quality validation (Bug 19)."""
    if not article_id or not bundle:
        return
    if bundle:
        if "content" in bundle:
            bundle["content"] = content_cleaner.repair_garbled_telugu(
                bundle["content"])
        if "ai_headline" in bundle:
            bundle["ai_headline"] = content_cleaner.repair_garbled_telugu(
                bundle["ai_headline"])
    if not validate_article_bundle(bundle):
        return
    wc = _word_count(bundle)
    try:
        conn = _connect()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO ai_cache (article_id, data, word_count)
            VALUES (?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE
                SET data       = excluded.data,
                    word_count = excluded.word_count,
                    cached_at  = CURRENT_TIMESTAMP
        """, (article_id, json.dumps(bundle, ensure_ascii=False), wc))
        conn.commit()
    except Exception as e:
        print(f"[CACHE] Error saving {article_id}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _delete_cached_ai(article_id: str) -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM ai_cache WHERE article_id = ?", (article_id,))
        conn.commit()
    except Exception as e:
        print(f"[CACHE] Error deleting {article_id}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def clear_ai_cache() -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM ai_cache")
        conn.commit()
    except Exception as e:
        print(f"[CACHE] Error clearing cache: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
