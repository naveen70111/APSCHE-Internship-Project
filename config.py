"""
config.py  —  Chronicle Intelligence Configuration  v9-BUGFIX
No functional changes — API keys, timeouts, and constants unchanged.
"""

# ── Gemini API Key ────────────────────────────────────────────
GEMINI_API_KEYS = [
    "AQ.Ab8RN6JyvVMa2ge7lgrVqkpEmh2YFcQ1w8eTfjZHxEnuNUM2qQ"
]

# ── GNews API Key ─────────────────────────────────────────────
GNEWS_API_KEY = "2eb4125410a5b1424e242a6080db19b6"

# ── App / Window ──────────────────────────────────────────────
APP_TITLE    = "Chronicle Intelligence"
APP_WIDTH    = 1200
APP_HEIGHT   = 800
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
FONT_FAMILY  = "Segoe UI"

# ── Database ──────────────────────────────────────────────────
DB_FILE = "chronicle_news.db"

# ── Timeouts ──────────────────────────────────────────────────
REQUEST_TIMEOUT    = 10
SCRAPE_TIMEOUT     = 5
SCRAPE_MAX_RETRIES = 1
MIN_PARAGRAPH_CHARS = 10

# ── Content quality ───────────────────────────────────────────
MIN_CONTENT_WORDS = 40
AI_MAX_TOKENS     = 1500
AI_TEMPERATURE    = 0.7

# ── Cache ─────────────────────────────────────────────────────
CACHE_TTL_MINUTES = 1440   # 24 hours

# ── Category / Language maps ──────────────────────────────────
CATEGORY_MAP = {
    "General":      "general",
    "Technology":   "technology",
    "Business":     "business",
    "Sports":       "sports",
    "Science":      "science",
    "Eenadu":       "eenadu",
    "Sakshi":       "sakshi",
    "Andhra Jyothi": "andhrajyothi",
}

LANG_MAP = {
    "English": "en",
    "Telugu":  "te",
}

DEFAULT_CATEGORY = "general"
DEFAULT_LANGUAGE = "en"

# ── Debug ─────────────────────────────────────────────────────
DEBUG_LOGGING = False

# ── Gemini rate-limit handling ────────────────────────────────
GEMINI_429_BLOCK_SECONDS     = 20
GEMINI_DEFAULT_BLOCK_SECONDS = 15

# ── Startup log ───────────────────────────────────────────────
print("[CONFIG] OK - Loaded")
print(f"[CONFIG] Gemini key: {GEMINI_API_KEYS[0][:20]}...*** (active)")
print(f"[CONFIG] GNews key: {GNEWS_API_KEY[:20]}...*** (active)")
print(f"[CONFIG] Cache TTL: {CACHE_TTL_MINUTES} minutes")
print(f"[CONFIG] Window size: {APP_WIDTH}x{APP_HEIGHT}")

# ── Metrics ───────────────────────────────────────────────────
METRICS = {
    "rss_fetched":        0,
    "scraped_successful": 0,
    "gemini_generated":   0,
    "cache_hits":         0,
    "cache_misses":       0,
    "failed_urls":        set(),
}


def log_rss_fetched(count: int):
    METRICS["rss_fetched"] += count


def log_scrape_success(url: str):
    METRICS["scraped_successful"] += 1


def log_scrape_fail(url: str):
    METRICS["failed_urls"].add(url)


def log_gemini_generated():
    METRICS["gemini_generated"] += 1


def log_cache_hit():
    METRICS["cache_hits"] += 1


def log_cache_miss():
    METRICS["cache_misses"] += 1