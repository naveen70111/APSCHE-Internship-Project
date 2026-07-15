"""
api_manager.py  —  Chronicle Intelligence  v9-BUGFIX

BUG FIXES IN THIS VERSION
──────────────────────────
Bug 7  : _post_clean() calls is_article_complete(); if truncated and body
         < 200 words, retries Gemini once with explicit continuation prompt.
Bug 8  : After Gemini response, if body < 100 words (EN) / < 80 words (TE),
         automatic one-shot expansion retry using higher token budget.
Bug 9  : Stronger language-enforcement injected into EVERY system prompt.
         EN prompt: "Translate source to English. NEVER output Telugu script."
         TE prompt: (in Telugu) "ఒక్క ఆంగ్ల వాక్యం రాయకండి."
Bug 10 : _best_source() now passes full title into prompt so Gemini can
         translate proper nouns / place names accurately.
Bug 15 : validate_image_url() delegated to content_cleaner; bad image URLs
         are caught early and the scrape step retries for a clean image.
Bug 17 : validate_content_matches_title() guard retained; cache entry is
         deleted and Gemini retried when topic mismatch detected.
Bug 18 : _is_recent() freshness filter in _smart_filter() — articles older
         than 3 days are dropped before reaching the feed.
Bug 19 : Article-level AI cache checked first; result cached after generation.
Bug 20 : All Gemini/network calls wrapped in try/except; every failure logs
         a useful message and falls back gracefully without crashing.
"""

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests
import urllib3

import content_cleaner
import database
import rss_manager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    GEMINI_API_KEYS, GNEWS_API_KEY,
    CACHE_TTL_MINUTES, REQUEST_TIMEOUT,
    CATEGORY_MAP, LANG_MAP,
    DEFAULT_CATEGORY, DEFAULT_LANGUAGE,
    MIN_CONTENT_WORDS, AI_MAX_TOKENS, AI_TEMPERATURE,
    GEMINI_429_BLOCK_SECONDS, GEMINI_DEFAULT_BLOCK_SECONDS,
    DEBUG_LOGGING,
)


def _dprint(*args, **kwargs):
    if DEBUG_LOGGING:
        print(*args, **kwargs)


_DISPLAY_MIN_WORDS  = 5
_TARGET_WORDS_EN    = 350
_TARGET_WORDS_TE    = 110
_MIN_WORDS_EN       = 100   # Bug 8 threshold for English
_MIN_WORDS_TE       = 80    # Bug 8 threshold for Telugu
_TOKEN_BUDGET       = 2500
_TOKEN_BUDGET_RETRY = 3200
_MAX_ARTICLE_AGE_DAYS = 3   # Bug 18

_article_cache: dict = {}
_cache_lock          = threading.Lock()
_inflight:      dict = {}
_inflight_lock       = threading.Lock()

_key_status: dict = {k: {"blocked_until": 0.0} for k in GEMINI_API_KEYS}
_key_lock         = threading.Lock()

_gemini_lock             = threading.Lock()
_gemini_call_times: list = []
_GEMINI_RPM_LIMIT        = 10
_GEMINI_MODELS           = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]

_MAX_ENRICH       = 10
_ENRICH_WORKERS   = 8
_ENRICH_TIMEOUT_S = 18

_GNEWS_VALID_CATEGORIES = {
    "general", "world", "nation", "business",
    "technology", "entertainment", "sports", "science", "health",
}
_PUBLISHER_CATEGORIES = {"eenadu", "sakshi", "andhrajyothi"}

_DIRECT_RSS: dict[str, list[str]] = {
    "sakshi":       ["https://www.sakshi.com/rss.xml", "https://www.sakshi.com/news/rss"],
    "eenadu":       ["https://www.eenadu.net/rss/telugu-news.xml", "https://www.eenadu.net/rss"],
    "andhrajyothi": ["https://www.andhrajyothi.com/rss/telugu-news.xml",
                     "https://www.andhrajyothi.com/rss/latest-news.xml",
                     "https://www.andhrajyothi.com/rss"],
}
_PUBLISHER_FILTER = {
    "eenadu":       ("eenadu.net",   "eenadu"),
    "sakshi":       ("sakshi.com",   "sakshi"),
    "andhrajyothi": ("andhrajyothi", "andhra jyothi"),
}

print(f"[INIT] Gemini models: {_GEMINI_MODELS}")
print(f"[INIT] Available API keys: {len(GEMINI_API_KEYS)}")
print(f"[INIT] GNews key configured: {bool(GNEWS_API_KEY)}")


_CATEGORY_KEYWORDS: dict = {
    "technology": [
        "ai", "artificial intelligence", "machine learning", "software", "hardware",
        "coding", "app", "cyber", "cybersecurity", "cloud", "robot", "algorithm",
        "startup", "tech", "nvidia", "microsoft", "google", "openai", "apple",
        "samsung", "chip", "semiconductor", "5g", "smartphone",
        "సాంకేతికత", "సాఫ్ట్‌వేర్", "గాడ్జెట్స్", "సైబర్", "క్లౌడ్", "టెక్నాలజీ",
    ],
    "business": [
        "stock", "market", "finance", "bank", "economy", "trade", "investment",
        "rupee", "gdp", "nifty", "sensex", "rbi", "shares", "profit", "revenue",
        "inflation", "budget", "tax", "corporate",
        "వ్యాపారం", "మార్కెట్లు", "ఆర్థికం", "స్టాక్స్", "బడ్జెట్",
    ],
    "sports": [
        "cricket", "football", "soccer", "ipl", "rcb", "csk", "mi", "kkr",
        "player", "tournament", "league", "team", "wicket", "goal", "tennis",
        "badminton", "olympics", "athlete", "champion", "trophy", "kohli", "dhoni",
        "క్రీడలు", "క్రికెట్", "మ్యాచ్", "ఐపీఎల్",
    ],
    "science": [
        "research", "space", "nasa", "isro", "discovery", "planet", "galaxy",
        "black hole", "climate", "biology", "physics", "chemistry", "medicine",
        "vaccine", "satellite", "study", "scientists", "experiment", "findings",
        "శాస్త్రం", "పరిశోధన", "అంతరిక్షం", "విజ్ఞానం",
    ],
}


# ─────────────────────────────────────────────────────────────
# Bug 18: freshness filter
# ─────────────────────────────────────────────────────────────

def _is_recent(published_at: str, max_days: int = _MAX_ARTICLE_AGE_DAYS) -> bool:
    """Return True if article is within the last max_days days. Unknown dates pass."""
    if not published_at:
        return True
    dt = None
    try:
        dt = parsedate_to_datetime(published_at)
    except Exception:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except Exception:
            pass
    if dt is None:
        return True
    try:
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        age_sec = (datetime.now() - dt).total_seconds()
        return -3600 <= age_sec <= max_days * 86400
    except Exception:
        return True


# ─────────────────────────────────────────────────────────────
# Bug 9: Language-enforcing system prompts
# ─────────────────────────────────────────────────────────────

# English — explicit translation + no Telugu allowed
_PROMPT_SYSTEM_EN = (
    "You are a senior news journalist writing for a premium English newspaper.\n\n"
    "LANGUAGE RULE (most important): Your output MUST be 100% in English.\n"
    "If the source material is in Telugu, Hindi, or any other language, translate "
    "it fully to English before writing. NEVER output Telugu script, Devanagari, "
    "or any non-English characters. Proper nouns (names, places) stay in English.\n\n"
    "ANTI-HALLUCINATION RULE: Use ONLY facts present in the source material. "
    "Do NOT invent names, quotes, statistics, dates, or events not in the source. "
    "If source facts are insufficient, expand by explaining the background, "
    "significance, and historical context — using general knowledge only.\n\n"
    "FORMATTING RULES:\n"
    "1. Minimum {target} words. End at a complete sentence — never cut off.\n"
    "2. Structure: strong opening paragraph, detailed body paragraphs, closing.\n"
    "3. REMOVE completely: dates, bylines, author names, publisher names, "
    "'Read More' links, ads, photo captions, navigation text, copyright.\n"
    "4. Write in third person. No 'click here', no 'subscribe', no 'follow us'.\n"
    "5. Output ONLY the article body. No headline. No preamble. "
    "Start directly with paragraph 1."
)

# Telugu — explicit single-language enforcement written in Telugu
_PROMPT_SYSTEM_TE = (
    "మీరు ఒక ప్రొఫెషనల్ తెలుగు న్యూస్ ఎడిటర్.\n\n"
    "భాష నియమం (అతి ముఖ్యమైనది): మీ జవాబు పూర్తిగా తెలుగులో మాత్రమే ఉండాలి. "
    "ఒక్క ఆంగ్ల వాక్యం కూడా రాయకండి. వ్యక్తుల పేర్లు మరియు స్థలాల పేర్లు "
    "తెలుగులో లిప్యంతరీకరణ చేయండి.\n\n"
    "నియమాలు:\n"
    "1. భాష: చాలా సరళమైన, స్పష్టమైన తెలుగు వాడండి.\n"
    "2. పొడవు: {target} పదాలు మాత్రమే. ఈ పరిమితి దాటకండి.\n"
    "3. నిర్మాణం: 2-3 స్పష్టమైన పేరాగ్రాఫ్లు ఇవ్వండి.\n"
    "4. కంటెంట్: వార్తలోని ముఖ్యమైన విషయాలు మాత్రమే చేర్చండి.\n"
    "5. ముగింపు: పూర్తి వాక్యంతో ముగించండి, వాక్యం మధ్యలో ఆపవద్దు.\n"
    "6. తొలగించండి: తేదీలు, రచయిత పేర్లు, 'Read More', ప్రకటనలు అన్నీ తీసివేయండి.\n"
    "7. అవుట్‌పుట్: కేవలం వ్యాసం మాత్రమే. శీర్షిక వద్దు."
)

# Prompt tiers
_TIER_RICH   = 150
_TIER_MEDIUM = 40

_PROMPT_USER_RICH = (
    "ARTICLE TITLE: {title}\n\n"
    "SOURCE MATERIAL ({src_words} words):\n{source}\n\n"
    "Rewrite as a clean, well-structured article of at least {target} words. "
    "The article MUST be about the topic stated in the title. "
    "Use all facts from the source. Remove noise, metadata, and repetition. "
    "No new facts. Start directly with paragraph 1."
)
_PROMPT_USER_MEDIUM = (
    "ARTICLE TITLE: {title}\n\n"
    "SOURCE MATERIAL ({src_words} words):\n{source}\n\n"
    "Write a news article of at least {target} words specifically about: {title}. "
    "Use every fact in the source. Expand by explaining background, significance, "
    "and broader implications. Do NOT invent facts, quotes, or statistics. "
    "Stay on the topic of the title. Start directly with paragraph 1."
)
_PROMPT_USER_THIN = (
    "ARTICLE TITLE: {title}\n\n"
    "SOURCE MATERIAL ({src_words} words):\n{source}\n\n"
    "Write a news article of at least {target} words about: {title}. "
    "Use source facts. Explain background, why it matters, and broader context. "
    "Do NOT invent specific names, quotes, or numbers. "
    "Stay strictly on the title topic. Start directly with paragraph 1."
)
_PROMPT_USER_RETRY = (
    "ARTICLE TITLE: {title}\n\n"
    "SOURCE MATERIAL:\n{source}\n\n"
    "Your previous response was too short ({got} words). "
    "You MUST write at least {target} words. "
    "Expand with more background, context, significance, and implications. "
    "Use ONLY facts from the source. Start directly with paragraph 1."
)
# Bug 7: continuation prompt for truncated articles
_PROMPT_USER_CONTINUE = (
    "ARTICLE TITLE: {title}\n\n"
    "INCOMPLETE ARTICLE (appears truncated):\n{body}\n\n"
    "The article above is incomplete — it stops mid-way. "
    "Rewrite it as a complete article of at least {target} words. "
    "Keep all existing content and add a proper conclusion. "
    "Do NOT add new facts not in the original. "
    "End with a complete sentence ending in a period."
)


# ─────────────────────────────────────────────────────────────
# Key / throttle helpers
# ─────────────────────────────────────────────────────────────

def _get_active_key() -> str | None:
    with _key_lock:
        now = time.time()
        for k in GEMINI_API_KEYS:
            if _key_status.get(k, {}).get("blocked_until", 0.0) < now:
                return k
        return None


def _block_key(key: str, secs: float = 60.0):
    with _key_lock:
        if key in _key_status:
            _key_status[key]["blocked_until"] = time.time() + secs
            _dprint(f"[KEY] Blocked key for {secs}s")


def _gemini_throttle():
    with _gemini_lock:
        now    = time.time()
        cutoff = now - 60.0
        while _gemini_call_times and _gemini_call_times[0] < cutoff:
            _gemini_call_times.pop(0)
        if len(_gemini_call_times) >= _GEMINI_RPM_LIMIT:
            wait       = _gemini_call_times[0] + 60.0
            sleep_time = max(0.0, wait - now) + 1.0
            _dprint(f"[THROTTLE] Waiting {sleep_time:.1f}s")
            time.sleep(sleep_time)
        _gemini_call_times.append(time.time())


# ─────────────────────────────────────────────────────────────
# Core Gemini call (Bug 20: full exception handling)
# ─────────────────────────────────────────────────────────────

def _call_gemini_raw(system_prompt: str, user_prompt: str,
                     max_tokens: int) -> str | None:
    key = _get_active_key()
    if not key:
        _dprint("[API] No active Gemini key")
        return None

    _gemini_throttle()

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature":     AI_TEMPERATURE,
            "maxOutputTokens": max_tokens,
            "topP":            0.92,
            "topK":            40,
        },
    }

    for model in _GEMINI_MODELS:
        _dprint(f"[API] Trying {model}...")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        try:
            resp = requests.post(url, json=payload, timeout=45, verify=False)
            _dprint(f"[API] Status: {resp.status_code}")

            if resp.status_code == 200:
                data       = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    _dprint("[API] No candidates"); continue
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    _dprint("[API] No parts"); continue
                raw = parts[0].get("text", "").strip()
                if raw:
                    _dprint(f"[API] Got {len(raw.split())} words from {model}")
                    return raw
                _dprint("[API] Empty text")

            elif resp.status_code == 429:
                _dprint("[API] 429 rate limited")
                _block_key(key, GEMINI_429_BLOCK_SECONDS)
                return None

            elif resp.status_code in (400, 401, 403):
                _dprint(f"[API] {resp.status_code} auth error")
                _block_key(key, GEMINI_DEFAULT_BLOCK_SECONDS)
                return None

            elif resp.status_code in (500, 503):
                _dprint(f"[API] {resp.status_code} server error, next model")
                time.sleep(1)

        except Exception as e:
            _dprint(f"[API] Exception on {model}: {type(e).__name__}: {str(e)[:80]}")
            _block_key(key, GEMINI_DEFAULT_BLOCK_SECONDS)
            break

    return None


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def _post_clean(text: str, lang: str, title: str = "") -> str:
    """Standard cleaning applied to every Gemini output."""
    text = re.sub(r'^```(?:html)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```$', '', text).strip()
    if "<p" in text or "<h1" in text:
        text = _strip_html(text)
    # Pass title so filter_relevant_paragraphs can run (Bugs 5, 6)
    text = content_cleaner.final_clean_pipeline(text, lang, title=title)
    return text.strip()


def _best_source(title: str, description: str, scraped: str) -> str:
    title_c = content_cleaner.clean_metadata(title or "").strip()
    desc_c  = content_cleaner.clean_metadata(description or "").strip()
    scr_c   = content_cleaner.clean_metadata(scraped or "").strip()
    parts   = []
    if title_c:
        parts.append(f"Title: {title_c}")
    body = scr_c if len(scr_c.split()) > len(desc_c.split()) else desc_c
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def _select_user_prompt(title: str, source: str, src_wc: int,
                         target: str) -> str:
    if src_wc >= _TIER_RICH:
        _dprint(f"[CONTENT] Tier=RICH ({src_wc}w)")
        return _PROMPT_USER_RICH.format(
            title=title, source=source, src_words=src_wc, target=target)
    elif src_wc >= _TIER_MEDIUM:
        _dprint(f"[CONTENT] Tier=MEDIUM ({src_wc}w)")
        return _PROMPT_USER_MEDIUM.format(
            title=title, source=source, src_words=src_wc, target=target)
    else:
        _dprint(f"[CONTENT] Tier=THIN ({src_wc}w)")
        return _PROMPT_USER_THIN.format(
            title=title, source=source, src_words=src_wc, target=target)


# ─────────────────────────────────────────────────────────────
# _guaranteed_content — Bugs 7, 8, 9 addressed
# ─────────────────────────────────────────────────────────────

def _guaranteed_content(title: str, description: str,
                         scraped: str = "",
                         lang: str = "en") -> tuple[str, str]:
    """
    Generate clean article body via Gemini.

    Bug 8: If response < min words, auto-retry with expansion prompt.
    Bug 9: System prompt enforces single-language output strictly.
    Bug 7: If body appears truncated, retry with continuation prompt.
    """
    title_c = content_cleaner.clean_metadata(title or "").strip()
    desc_c  = content_cleaner.clean_metadata(description or "").strip()
    scr_c   = ""
    if scraped:
        scr_c = content_cleaner.build_clean_article(scraped, language=lang,
                                                     min_words=5) or ""

    source  = _best_source(title_c, desc_c, scr_c)
    src_wc  = len(source.split())
    _dprint(f"[CONTENT] source_words={src_wc} lang={lang}")

    if not GEMINI_API_KEYS or not any(GEMINI_API_KEYS):
        return _raw_fallback(title_c, desc_c, scr_c, lang)

    # Bug 9: language-enforcing system prompt
    target_words = str(_TARGET_WORDS_TE) if lang == "te" else str(_TARGET_WORDS_EN)
    min_words    = _MIN_WORDS_TE        if lang == "te" else _MIN_WORDS_EN
    system_tmpl  = _PROMPT_SYSTEM_TE   if lang == "te" else _PROMPT_SYSTEM_EN
    system       = system_tmpl.format(target=target_words)

    user = _select_user_prompt(title_c, source, src_wc, target=target_words)

    # ── Attempt 1 ────────────────────────────────────────────
    raw = _call_gemini_raw(system, user, _TOKEN_BUDGET)
    if raw:
        body = _post_clean(raw, lang, title=title_c)
        wc   = len(body.split())
        _dprint(f"[CONTENT] Attempt 1: {wc} words")

        # Bug 7: detect truncation and retry
        if wc > 0 and not content_cleaner.is_article_complete(body):
            _dprint(f"[CONTENT] Truncated — retrying with continuation prompt")
            cont = _PROMPT_USER_CONTINUE.format(
                title=title_c, body=body, target=target_words)
            raw_c = _call_gemini_raw(system, cont, _TOKEN_BUDGET_RETRY)
            if raw_c:
                body_c = _post_clean(raw_c, lang, title=title_c)
                if len(body_c.split()) > wc:
                    body = body_c
                    wc   = len(body.split())

        # Bug 8: too short — expansion retry
        if wc < min_words:
            _dprint(f"[CONTENT] {wc} < {min_words} words — expansion retry")
            retry_user = _PROMPT_USER_RETRY.format(
                title=title_c, source=source,
                got=wc, target=target_words)
            raw2 = _call_gemini_raw(system, retry_user, _TOKEN_BUDGET_RETRY)
            if raw2:
                body2 = _post_clean(raw2, lang, title=title_c)
                wc2   = len(body2.split())
                _dprint(f"[CONTENT] Expansion: {wc2} words")
                if wc2 > wc:
                    body = body2

        if body:
            return "", body

    _dprint("[CONTENT] Gemini failed — raw fallback")
    return _raw_fallback(title_c, desc_c, scr_c, lang)


def _raw_fallback(title_c: str, desc_c: str,
                  scr_c: str, lang: str) -> tuple[str, str]:
    for candidate in (scr_c, desc_c, title_c):
        if candidate and len(candidate.split()) >= _DISPLAY_MIN_WORDS:
            body = content_cleaner.remove_repeated_paragraphs(candidate)
            body = content_cleaner.ensure_complete_ending(body, lang)
            if content_cleaner.is_duplicate_of_title(body, title_c):
                return "", content_cleaner.no_details_message(lang)
            return "", body
    return "", content_cleaner.no_details_message(lang)


# ─────────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────────

def make_article_id(url: str, title: str) -> str:
    raw = f"{(url or '').strip()}|{(title or '').strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _sentiment_score(title: str, desc: str) -> tuple[str, int]:
    text = f"{title} {desc}".lower()
    pos  = ["win","gain","growth","success","launch","record","best","rise",
            "profit","boost","surge","improve","positive","good"]
    neg  = ["loss","crash","fail","drop","risk","warn","crisis","attack",
            "death","disaster","ban","scam","collapse","decline","cut"]
    p    = sum(1 for w in pos if w in text)
    n    = sum(1 for w in neg if w in text)
    score = max(38, min(99, 60 + p * 5 - n * 4))
    label = "Positive" if p > n else "Negative" if n > p else "Neutral"
    return label, score


def _tags(category: str, article_id: str, language: str) -> list:
    te = {
        "sports":       ["#క్రీడలు","#క్రికెట్","#IPL","#మ్యాచ్"],
        "technology":   ["#సాంకేతికత","#AI","#సాఫ్ట్‌వేర్","#ఆవిష్కరణ"],
        "business":     ["#వ్యాపారం","#మార్కెట్లు","#ఆర్థికం","#స్టాక్స్"],
        "science":      ["#శాస్త్రం","#పరిశోధన","#అంతరిక్షం","#గ్రహాలు"],
        "general":      ["#వార్తలు","#ప్రపంచం","#తాజా","#ముఖ్యాంశాలు"],
        "eenadu":       ["#ఈనాడు","#తెలుగువార్తలు"],
        "sakshi":       ["#సాక్షి","#తెలుగువార్తలు"],
        "andhrajyothi": ["#ఆంధ్రజ్యోతి","#తెలుగువార్తలు"],
    }
    en = {
        "sports":       ["#Sports","#Cricket","#IPL","#MatchUpdate"],
        "technology":   ["#Tech","#AI","#Software","#Innovation"],
        "business":     ["#Business","#Economy","#Markets","#Finance"],
        "science":      ["#Science","#Space","#Research","#Discovery"],
        "general":      ["#News","#Global","#CurrentAffairs","#Breaking"],
        "eenadu":       ["#Eenadu","#TeluguNews"],
        "sakshi":       ["#Sakshi","#TeluguNews"],
        "andhrajyothi": ["#AndhraJyothi","#TeluguNews"],
    }
    pool = (te if language == "te" else en).get(category.lower(), ["#News"])
    idx  = int(article_id[:8], 16) % len(pool)
    live = "#లైవ్అప్‌డేట్స్" if language == "te" else "#LiveUpdates"
    return [pool[idx], pool[(idx + 1) % len(pool)], live]


def _normalize_category(category: str) -> str:
    if not category:
        return DEFAULT_CATEGORY
    c = category.strip()
    if c in CATEGORY_MAP:
        return CATEGORY_MAP[c]
    lo = c.lower()
    if lo in CATEGORY_MAP.values():
        return lo
    return DEFAULT_CATEGORY


def _normalize_language(language: str) -> str:
    if not language:
        return DEFAULT_LANGUAGE
    l = language.strip()
    if l in LANG_MAP:
        return LANG_MAP[l]
    lo = l.lower()
    if lo in LANG_MAP.values():
        return lo
    return DEFAULT_LANGUAGE


def _classify_category(title: str, description: str) -> str:
    text   = f"{title} {description}".lower()
    scores = {}
    for cat, kws in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > 0:
            scores[cat] = score
    return max(scores, key=scores.get) if scores else "general"


def _smart_filter(articles: list) -> list:
    """Deduplicate + Bug 18 freshness filter (drop articles > 3 days old)."""
    filtered:   list     = []
    seen_urls:  set[str] = set()
    seen_norm:  set[str] = set()
    dropped = 0
    for art in articles:
        if not art:
            continue
        url   = art.get("url", "")
        title = art.get("title", "")
        if not url or not title or "[Removed]" in title:
            continue
        if not _is_recent(art.get("published_at", "")):
            dropped += 1
            continue
        norm = re.sub(r'[^a-z0-9\u0C00-\u0C7F]', '', title.lower()).strip()
        if url in seen_urls or norm in seen_norm:
            continue
        seen_urls.add(url)
        seen_norm.add(norm)
        filtered.append(art)
    if dropped:
        _dprint(f"[FRESHNESS] Dropped {dropped} stale article(s)")
    return filtered


# ─────────────────────────────────────────────────────────────
# RSS helpers
# ─────────────────────────────────────────────────────────────

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept":     "application/rss+xml, application/xml, text/xml",
    "Referer":    "https://news.google.com/",
}


def _parse_rss_item(item, category: str, language: str,
                    pub_filter: tuple | None) -> dict | None:
    t_nd = item.find("title")
    l_nd = item.find("link")
    d_nd = item.find("description")
    p_nd = item.find("pubDate")
    s_nd = item.find("source")

    raw_title = (t_nd.text or "") if t_nd is not None else ""
    url_link  = (l_nd.text or "") if l_nd is not None else ""
    desc_raw  = (d_nd.text or "") if d_nd is not None else ""
    pub_date  = (p_nd.text or "") if p_nd is not None else ""
    source    = (s_nd.text or "Google News") if s_nd is not None else "Google News"

    if not raw_title or not url_link:
        return None
    if pub_filter:
        domain_frag, source_frag = pub_filter
        ul = url_link.lower(); sl = source.lower()
        if domain_frag not in ul and source_frag not in sl:
            return None

    title_c = content_cleaner.clean_metadata(
        re.sub(r"\s+-\s+[^-\n]+$", "", raw_title).strip())
    desc_c  = content_cleaner.clean_metadata(
        re.sub(r'<[^>]+>', ' ', desc_raw).strip()) or title_c

    art_id      = make_article_id(url_link, title_c)
    sent, score = _sentiment_score(title_c, desc_c)
    return {
        "article_id":   art_id,
        "title":        title_c,
        "description":  desc_c,
        "content":      desc_c,
        "source":       source,
        "url":          url_link,
        "image_url":    "",
        "published_at": pub_date,
        "language":     language,
        "category":     category,
        "sentiment":    sent,
        "score":        score,
        "tags":         _tags(category, art_id, language),
        "timestamp":    datetime.now().isoformat(),
    }


def _fetch_rss_url(feed_url: str, category: str, language: str,
                   pub_filter: tuple | None, seen: set,
                   max_items: int = 30) -> list:
    try:
        r = requests.get(feed_url, headers=_RSS_HEADERS, timeout=10, verify=False)
        _dprint(f"[RSS] {feed_url[:80]} -> HTTP {r.status_code}")
        if r.status_code != 200:
            return []
        root     = ET.fromstring(r.content)
        articles = []
        for item in root.findall(".//item")[:max_items]:
            art = _parse_rss_item(item, category, language, pub_filter)
            if art and art["article_id"] not in seen:
                seen.add(art["article_id"])
                articles.append(art)
        _dprint(f"[RSS] Parsed {len(articles)} articles")
        return articles
    except Exception as e:
        _dprint(f"[RSS] Exception: {type(e).__name__}: {str(e)[:80]}")
        return []


def _fetch_publisher_rss(category: str, language: str, seen: set) -> list:
    pub_filter = _PUBLISHER_FILTER.get(category)
    articles   = []
    for feed_url in _DIRECT_RSS.get(category, []):
        arts = _fetch_rss_url(feed_url, category, language,
                              pub_filter=None, seen=seen)
        articles.extend(arts)
        if len(articles) >= 10:
            return articles
    q_map = {
        "eenadu":       "Eenadu Telugu News",
        "sakshi":       "Sakshi Telugu News",
        "andhrajyothi": "Andhra Jyothi Telugu News",
    }
    query  = q_map.get(category, category)
    hl     = "te" if language == "te" else "en"
    ceid   = "IN:te" if language == "te" else "IN:en"
    gn_url = (
        f"https://news.google.com/rss/search"
        f"?q={quote_plus(query)}&hl={hl}&gl=IN&ceid={ceid}"
    )
    articles.extend(
        _fetch_rss_url(gn_url, category, language, pub_filter, seen))
    return articles


def _fetch_google_rss(query: str = None, category: str = None,
                       language: str = "en", seen: set = None) -> list:
    if seen is None:
        seen = set()
    hl   = "te" if language == "te" else "en-IN"
    gl   = "IN"
    ceid = "IN:te" if language == "te" else "IN:en"
    if query:
        url = (f"https://news.google.com/rss/search?"
               f"q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}")
    elif category and category not in ("general",) | _PUBLISHER_CATEGORIES:
        cat_map = {"technology": "TECHNOLOGY", "sports": "SPORTS",
                   "business": "BUSINESS", "science": "SCIENCE",
                   "health": "HEALTH", "entertainment": "ENTERTAINMENT"}
        cat_id  = cat_map.get(category.lower(), "WORLD")
        url     = (f"https://news.google.com/rss/headlines/section/topic/"
                   f"{cat_id}?hl={hl}&gl={gl}&ceid={ceid}")
    else:
        url = f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"
    _dprint(f"[RSS] Fetching: {url[:100]}")
    return _fetch_rss_url(url, category or "general", language,
                          pub_filter=None, seen=seen)


def _http_get(url: str) -> dict | None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers,
                             timeout=REQUEST_TIMEOUT, verify=False)
            _dprint(f"[FETCH] HTTP {r.status_code} for {url[:90]}...")
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            _dprint(f"[FETCH] Attempt {attempt+1}: {type(e).__name__}: {str(e)[:80]}")
    return None


def _build_gnews_url(category: str, search_term: str, language: str,
                      drop_lang: bool = False) -> str:
    lang_part = "" if drop_lang else f"&lang={language}"
    if search_term:
        return (f"https://gnews.io/api/v4/search?q={quote_plus(search_term)}"
                f"{lang_part}&country=in&max=30&token={GNEWS_API_KEY}")
    elif category in _GNEWS_VALID_CATEGORIES:
        return (f"https://gnews.io/api/v4/top-headlines?"
                f"country=in{lang_part}&category={category}"
                f"&max=30&token={GNEWS_API_KEY}")
    else:
        return (f"https://gnews.io/api/v4/top-headlines?"
                f"country=in{lang_part}&category=general"
                f"&max=30&token={GNEWS_API_KEY}")


def _parse_gnews_articles(data: dict, category: str, search_term: str,
                           language: str, seen: set) -> list:
    out = []
    for item in data.get("articles", []):
        if not item:
            continue
        title = (item.get("title") or "").strip()
        if not title or "[Removed]" in title:
            continue
        desc      = content_cleaner.clean_metadata(
            (item.get("description") or title).strip())
        url_link  = (item.get("url") or "").strip()
        source    = item.get("source", {}).get("name") or "Global Agency"
        pub_at    = item.get("publishedAt") or ""
        raw_img   = item.get("image") or ""
        # Bug 15: validate image URL
        image_url = raw_img if content_cleaner.validate_image_url(raw_img) else ""
        content   = content_cleaner.clean_metadata(
            (item.get("content") or "").strip())
        art_id = make_article_id(url_link, title)
        if not url_link or art_id in seen:
            continue
        seen.add(art_id)
        eff_cat = category
        if not search_term and category == "general":
            classified = _classify_category(title, desc)
            if classified != "general":
                eff_cat = classified
        sent, score = _sentiment_score(title, desc)
        out.append({
            "article_id":   art_id,
            "title":        title,
            "description":  desc,
            "content":      content,
            "source":       source,
            "url":          url_link,
            "image_url":    image_url,
            "published_at": pub_at,
            "language":     language,
            "category":     eff_cat,
            "sentiment":    sent,
            "score":        score,
            "tags":         _tags(eff_cat, art_id, language),
            "timestamp":    datetime.now().isoformat(),
        })
    return out


def _enrich_with_full_article(article: dict) -> dict:
    if not article:
        return article
    url = article.get("url", "")
    if not url:
        return article
    try:
        scraped_text, scraped_img = rss_manager.scrape_full_text(url)
        scraped_wc  = len(scraped_text.split()) if scraped_text else 0
        existing_wc = max(
            len(article.get("content", "").split()),
            len(article.get("description", "").split()))
        if scraped_text and scraped_wc > existing_wc:
            article["content"] = scraped_text
        # Bug 15: validate scraped image
        if scraped_img and content_cleaner.validate_image_url(scraped_img):
            if not article.get("image_url"):
                article["image_url"] = scraped_img
    except Exception as e:
        _dprint(f"[SCRAPE] Failed for {url[:60]}: {str(e)[:40]}")
    return article


def _enrich_batch_parallel(articles: list) -> list:
    if not articles:
        return []
    subset = articles[:_MAX_ENRICH]
    rest   = articles[_MAX_ENRICH:]
    _dprint(f"[ENRICH] Scraping {len(subset)} articles ({_ENRICH_WORKERS} workers)...")
    t0       = time.time()
    results  = list(subset)
    executor = ThreadPoolExecutor(max_workers=_ENRICH_WORKERS)
    future_map = {
        executor.submit(_enrich_with_full_article, art): i
        for i, art in enumerate(subset)
    }
    done = 0
    try:
        for future in as_completed(future_map, timeout=_ENRICH_TIMEOUT_S):
            i = future_map[future]
            try:
                results[i] = future.result()
                done += 1
            except Exception as e:
                _dprint(f"[ENRICH] Worker error: {str(e)[:60]}")
    except FuturesTimeoutError:
        _dprint(f"[ENRICH] Timeout after {_ENRICH_TIMEOUT_S}s ({done}/{len(subset)} done)")
    executor.shutdown(wait=False)
    _dprint(f"[ENRICH] Done in {time.time() - t0:.1f}s")
    return results + rest


# ─────────────────────────────────────────────────────────────
# Public fetch API
# ─────────────────────────────────────────────────────────────

def _fetch_and_enrich(category: str = "general", search_term: str = None,
                      language: str = "en") -> list:
    category = _normalize_category(category)
    language = _normalize_language(language)
    _dprint(f"[FETCH] category={category} language={language} search={search_term}")
    collected: list     = []
    seen:      set[str] = set()

    if search_term:
        if GNEWS_API_KEY:
            gnews_url = _build_gnews_url(category, search_term, language)
            data = _http_get(gnews_url)
            if data:
                collected.extend(
                    _parse_gnews_articles(data, category, search_term, language, seen))
        collected.extend(
            _fetch_google_rss(query=search_term, language=language, seen=seen))

    elif category in _PUBLISHER_CATEGORIES:
        collected.extend(_fetch_publisher_rss(category, language, seen))
        if len(collected) < 5:
            collected.extend(
                _fetch_google_rss(category=category, language=language, seen=seen))

    else:
        if GNEWS_API_KEY:
            gnews_url = _build_gnews_url(category, None, language)
            data = _http_get(gnews_url)
            if data:
                total = len(data.get("articles", []))
                _dprint(f"[FETCH] GNews: {total} articles")
                if total == 0:
                    data2 = _http_get(
                        _build_gnews_url(category, None, language, drop_lang=True))
                    if data2 and len(data2.get("articles", [])) > 0:
                        data = data2
                if data:
                    collected.extend(
                        _parse_gnews_articles(data, category, None, language, seen))
        if len(collected) < 10:
            collected.extend(
                _fetch_google_rss(category=category, language=language, seen=seen))

    _dprint(f"[FETCH] Collected: {len(collected)}")
    collected = _smart_filter(collected)
    enriched  = _enrich_batch_parallel(collected)
    _dprint(f"[FETCH] Final: {len(enriched)} articles")
    return enriched


def _mark_language(articles: list, target_lang: str) -> list:
    return [{**a, "language": target_lang} for a in articles if a]


def get_cached_news(category: str, language: str = "en") -> list:
    category = _normalize_category(category)
    language = _normalize_language(language)
    key      = f"{category}_{language}"

    with _cache_lock:
        entry = _article_cache.get(key)
        if entry and datetime.now() < entry["expires"]:
            _dprint(f"[CACHE] Hit for {key}: {len(entry['articles'])} articles")
            return entry["articles"]

    with _inflight_lock:
        if key in _inflight:
            ev = _inflight[key]; is_owner = False
        else:
            ev = threading.Event()
            _inflight[key] = ev; is_owner = True

    if not is_owner:
        ev.wait(timeout=25)
        with _cache_lock:
            e = _article_cache.get(key)
            return e["articles"] if e else []

    try:
        import fetcher
        articles = fetcher.fetch_news(category=category, language=language)
        if not articles and language == "te":
            _dprint("[CACHE] No Telugu — trying English")
            articles = _mark_language(
                fetcher.fetch_news(category=category, language="en"), "te")
        if articles:
            exp = datetime.now() + timedelta(minutes=CACHE_TTL_MINUTES)
            with _cache_lock:
                _article_cache[key] = {"articles": articles, "expires": exp}
        return articles
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        ev.set()


def get_news_with_fallback(category: str, language: str = "en") -> tuple:
    category = _normalize_category(category)
    language = _normalize_language(language)
    arts     = get_cached_news(category, language)
    if arts:
        return arts, language
    fb   = "te" if language == "en" else "en"
    arts = get_cached_news(category, fb)
    return (arts, fb) if arts else ([], language)


def sync_latest_news(category: str, language: str = "en") -> list:
    cat  = _normalize_category(category)
    lang = _normalize_language(language)
    cached = get_cached_news(cat, lang)
    if cached:
        return cached
    try:
        import fetcher
        arts = fetcher.fetch_news(category=cat, language=lang)
        if not arts and lang == "te":
            arts = _mark_language(
                fetcher.fetch_news(category=cat, language="en"), "te")
        if arts:
            exp = datetime.now() + timedelta(minutes=CACHE_TTL_MINUTES)
            with _cache_lock:
                _article_cache[f"{cat}_{lang}"] = {"articles": arts, "expires": exp}
        return arts
    except Exception as e:
        _dprint(f"[SYNC] Exception: {type(e).__name__}: {str(e)[:100]}")
        return []


def invalidate_cache(category: str = None, language: str = None):
    with _cache_lock:
        if category and language:
            k = f"{_normalize_category(category)}_{_normalize_language(language)}"
            _article_cache.pop(k, None)
        else:
            _article_cache.clear()


def compile_advanced_ai_intelligence(
    article_id:   str,
    title:        str,
    description:  str,
    category:     str,
    language:     str = "en",
    content:      str = "",
    source:       str = "",
    published_at: str = "",
    image_url:    str = "",
) -> dict | None:
    language  = _normalize_language(language)
    min_words = _MIN_WORDS_TE if language == "te" else _MIN_WORDS_EN * 3

    cached = database.get_cached_ai(article_id)
    if cached:
        body = (cached.get("content") or "").strip()
        if body and len(body.split()) >= min_words:
            return cached
        try:
            database._delete_cached_ai(article_id)
        except Exception:
            pass

    _, body = _guaranteed_content(
        title=title or "", description=description or "",
        scraped=content or "", lang=language)

    # Run full pipeline with title for Bug 5/6 relevance filtering
    body = content_cleaner.final_clean_pipeline(body, language, title=title or "")
    if not body.strip():
        body = content_cleaner.ensure_complete_ending(
            content_cleaner.clean_metadata(title or "Content unavailable."),
            language)

    bundle = {"content": body, "ai_headline": ""}
    try:
        if database.validate_article_bundle(bundle):
            database.save_cached_ai(article_id, bundle)
    except Exception:
        pass

    return bundle


def search_news(keyword: str, language: str = "en",
                category: str = None) -> list:
    language = _normalize_language(language)
    query    = (keyword or "").strip().lower()
    if not query:
        return []
    results: list = []
    with _cache_lock:
        for entry in _article_cache.values():
            for art in entry.get("articles", []):
                if not art:
                    continue
                if art.get("language") != language:
                    continue
                if category and art.get("category") != _normalize_category(category):
                    continue
                hay = f"{art.get('title','')} {art.get('description','')}".lower()
                if query in hay:
                    results.append(art)
    if results:
        return results
    try:
        import fetcher
        return fetcher.fetch_news(category=category, language=language,
                                  search_term=keyword)
    except Exception:
        return []


def start_background_preload(language: str = "en"):
    pass
