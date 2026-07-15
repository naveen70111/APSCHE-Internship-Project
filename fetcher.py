"""
fetcher.py  —  Chronicle Intelligence  v9-BUGFIX

BUG FIXES IN THIS VERSION
──────────────────────────
Bug 18 : _smart_filter (imported from api_manager) now includes the
         freshness guard — articles older than 3 days are dropped here.
Bug 20 : All fetch paths wrapped in try/except; failures log a message
         and fall through to the next source without crashing.
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote_plus
from random import choice

import requests
import urllib3

import content_cleaner
from api_manager import (
    make_article_id, _sentiment_score, _tags,
    _normalize_category, _normalize_language,
    _smart_filter, _classify_category,
    _GNEWS_VALID_CATEGORIES, _PUBLISHER_CATEGORIES,
)
from config import (
    GNEWS_API_KEY, DEBUG_LOGGING,
    REQUEST_TIMEOUT,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _log(msg: str):
    if DEBUG_LOGGING:
        print(msg)


_USER_AGENTS = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"),
]


def _random_ua() -> str:
    return choice(_USER_AGENTS)


_PUBLISHER_FILTER = {
    "eenadu":       ("eenadu.net",   "eenadu"),
    "sakshi":       ("sakshi.com",   "sakshi"),
    "andhrajyothi": ("andhrajyothi", "andhra jyothi"),
}

_DIRECT_RSS: dict[str, list[str]] = {
    "sakshi": [
        "https://www.sakshi.com/rss.xml",
        "https://www.sakshi.com/news/rss",
        "https://feeds.feedburner.com/sakshieducation",
    ],
    "eenadu": [
        "https://www.eenadu.net/rss/telugu-news.xml",
        "https://www.eenadu.net/rss",
        "https://www.eenadu.net/telugu-news/national/2",
    ],
    "andhrajyothi": [
        "https://www.andhrajyothi.com/rss/telugu-news.xml",
        "https://www.andhrajyothi.com/rss/latest-news.xml",
        "https://www.andhrajyothi.com/rss",
        "https://www.andhrajyothi.com/rss/index.xml",
    ],
}

_PUBLISHER_GN_QUERY = {
    "eenadu":       "Eenadu Telugu News",
    "sakshi":       "Sakshi Telugu News",
    "andhrajyothi": "Andhra Jyothi Telugu News",
}

_CAT_TOPIC_ID = {
    "technology":    "TECHNOLOGY",
    "sports":        "SPORTS",
    "business":      "BUSINESS",
    "science":       "SCIENCE",
    "health":        "HEALTH",
    "entertainment": "ENTERTAINMENT",
    "world":         "WORLD",
    "nation":        "NATION",
}


def _rss_headers(extra: bool = False) -> dict:
    h = {
        "User-Agent":      _random_ua(),
        "Accept":          "application/rss+xml, application/xml, text/xml, */*;q=0.8",
        "Referer":         "https://www.google.com/",
        "Accept-Language": "te-IN,te;q=0.9,en-IN;q=0.8,en;q=0.7",
    }
    if extra:
        h.update({"Cache-Control": "no-cache", "Pragma": "no-cache", "DNT": "1"})
    return h


def _build_gnews_url(category: str, language: str,
                     search_term: str = None, drop_lang: bool = False) -> str:
    lang_part = "" if drop_lang else f"&lang={language}"
    if search_term:
        return (f"https://gnews.io/api/v4/search"
                f"?q={quote_plus(search_term)}{lang_part}"
                f"&country=in&max=30&token={GNEWS_API_KEY}")
    if category in _GNEWS_VALID_CATEGORIES:
        return (f"https://gnews.io/api/v4/top-headlines"
                f"?country=in{lang_part}&category={category}"
                f"&max=30&token={GNEWS_API_KEY}")
    return (f"https://gnews.io/api/v4/top-headlines"
            f"?country=in{lang_part}&category=general"
            f"&max=30&token={GNEWS_API_KEY}")


def _http_get_json(url: str) -> dict | None:
    headers = {"User-Agent": _random_ua()}
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers,
                             timeout=REQUEST_TIMEOUT, verify=False)
            _log(f"[FETCH] HTTP {r.status_code} for {url[:90]}...")
            if r.status_code == 200:
                return r.json()
            _log(f"[FETCH] Non-200: {r.text[:200]}")
        except Exception as e:
            _log(f"[FETCH] Exception attempt {attempt+1}: "
                 f"{type(e).__name__}: {str(e)[:80]}")
    return None


def _parse_gnews_response(data: dict, category: str, language: str,
                           search_term: str, seen: set) -> list:
    out = []
    for item in (data.get("articles") or []):
        if not item:
            continue
        title = (item.get("title") or "").strip()
        if not title or "[Removed]" in title:
            continue
        url_link  = (item.get("url") or "").strip()
        desc      = content_cleaner.clean_metadata(
            (item.get("description") or title).strip())
        source    = item.get("source", {}).get("name") or "Global Agency"
        pub_at    = item.get("publishedAt") or ""
        raw_img   = item.get("image") or ""
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


def _fetch_gnews(category: str, language: str,
                 search_term: str = None, seen: set = None) -> list:
    if seen is None:
        seen = set()
    if not GNEWS_API_KEY:
        _log("[FETCH] No GNEWS_API_KEY — skipping GNews")
        return []
    try:
        url  = _build_gnews_url(category, language, search_term)
        data = _http_get_json(url)
        if data:
            total = len(data.get("articles") or [])
            _log(f"[FETCH] GNews returned {total} articles")
            if total == 0:
                _log("[FETCH] Retrying GNews without &lang=...")
                data2 = _http_get_json(
                    _build_gnews_url(category, language, search_term, drop_lang=True))
                if data2 and len(data2.get("articles") or []) > 0:
                    data = data2
        else:
            _log("[FETCH] GNews returned None")
            return []
        articles = _parse_gnews_response(data, category, language, search_term, seen)
        _log(f"[FETCH] After GNews parse: {len(articles)} articles")
        return articles
    except Exception as e:
        _log(f"[FETCH] GNews exception: {type(e).__name__}: {str(e)[:80]}")
        return []


def _parse_rss_item(item, category: str, language: str,
                    publisher_filter: tuple | None) -> dict | None:
    try:
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
        if publisher_filter:
            domain_frag, source_frag = publisher_filter
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
    except Exception:
        return None


def _fetch_rss_url(feed_url: str, category: str, language: str,
                   publisher_filter: tuple | None,
                   max_items: int = 30, seen: set = None,
                   use_extra_headers: bool = False) -> list:
    import config
    if seen is None:
        seen = set()
    try:
        headers = _rss_headers(extra=use_extra_headers)
        r = requests.get(feed_url, headers=headers, timeout=10, verify=False)
        _log(f"[RSS] {feed_url[:80]} -> HTTP {r.status_code}")
        if r.status_code != 200:
            return []
        root     = ET.fromstring(r.content)
        articles = []
        for item in root.findall(".//item")[:max_items]:
            art = _parse_rss_item(item, category, language, publisher_filter)
            if art and art["article_id"] not in seen:
                seen.add(art["article_id"])
                articles.append(art)
        _log(f"[RSS] Parsed {len(articles)} articles from {feed_url[:60]}")
        config.log_rss_fetched(len(articles))
        return articles
    except Exception as e:
        _log(f"[RSS] Exception on {feed_url[:60]}: {type(e).__name__}: {str(e)[:80]}")
        return []


def _fetch_publisher_rss(category: str, language: str,
                         seen: set = None) -> list:
    if seen is None:
        seen = set()
    pub_filter = _PUBLISHER_FILTER.get(category)
    articles   = []
    for feed_url in _DIRECT_RSS.get(category, []):
        arts = _fetch_rss_url(feed_url, category, language,
                              publisher_filter=None, seen=seen,
                              use_extra_headers=True)
        if not arts:
            time.sleep(0.3)
            arts = _fetch_rss_url(feed_url, category, language,
                                  publisher_filter=None, seen=seen,
                                  use_extra_headers=False)
        articles.extend(arts)
        if len(articles) >= 10:
            _log(f"[FETCH] {len(articles)} from direct RSS")
            return articles

    _log(f"[FETCH] Direct RSS: {len(articles)}, trying Google News RSS...")
    query  = _PUBLISHER_GN_QUERY.get(category, category)
    hl     = "te" if language == "te" else "en"
    ceid   = "IN:te" if language == "te" else "IN:en"
    gn_url = (f"https://news.google.com/rss/search"
               f"?q={quote_plus(query)}&hl={hl}&gl=IN&ceid={ceid}")
    articles.extend(_fetch_rss_url(gn_url, category, language,
                                   publisher_filter=pub_filter, seen=seen))
    _log(f"[FETCH] Publisher total: {len(articles)}")
    return articles


def _fetch_google_news_rss(category: str, language: str,
                            search_term: str = None,
                            seen: set = None) -> list:
    if seen is None:
        seen = set()
    fetch_hl   = "en-IN"
    gl         = "IN"
    fetch_ceid = "IN:en"
    try:
        if search_term:
            fetch_hl   = "te" if language == "te" else "en-IN"
            fetch_ceid = "IN:te" if language == "te" else "IN:en"
            url = (f"https://news.google.com/rss/search"
                   f"?q={quote_plus(search_term)}&hl={fetch_hl}&gl={gl}&ceid={fetch_ceid}")
        elif category not in {"general"} | _PUBLISHER_CATEGORIES:
            cat_id = _CAT_TOPIC_ID.get(category.lower(), "WORLD")
            url = (f"https://news.google.com/rss/headlines/section/topic"
                   f"/{cat_id}?hl={fetch_hl}&gl={gl}&ceid={fetch_ceid}")
        else:
            hl   = "te" if language == "te" else "en-IN"
            ceid = "IN:te" if language == "te" else "IN:en"
            url  = f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"
        arts = _fetch_rss_url(url, category, language,
                              publisher_filter=None, seen=seen)
        for a in arts:
            a["language"] = language
        return arts
    except Exception as e:
        _log(f"[RSS] Google News RSS exception: {type(e).__name__}: {str(e)[:80]}")
        return []


def fetch_news(category: str = "general", language: str = "en",
               search_term: str = None) -> list:
    """
    Main entry point. Returns metadata-only articles (no full-text scraping).
    Full scraping is deferred to _open_reader() in ui_components.py.
    Bug 18 freshness filter applied via _smart_filter().
    """
    collected: list = []
    seen:      set  = set()

    try:
        if search_term:
            _log(f"[FETCH] Search mode: {search_term!r}")
            if GNEWS_API_KEY:
                collected.extend(
                    _fetch_gnews(category, language, search_term=search_term, seen=seen))
            collected.extend(
                _fetch_google_news_rss(category, language, search_term, seen))

        elif category in _PUBLISHER_CATEGORIES:
            _log(f"[FETCH] Publisher mode: {category}")
            collected.extend(_fetch_publisher_rss(category, language, seen))
            if len(collected) < 5:
                collected.extend(
                    _fetch_google_news_rss(category, language, seen=seen))

        else:
            _log("[FETCH] Standard mode")
            if GNEWS_API_KEY:
                collected.extend(
                    _fetch_gnews(category, language, search_term=None, seen=seen))
            if len(collected) < 10:
                _log("[FETCH] Topping up with Google News RSS...")
                collected.extend(
                    _fetch_google_news_rss(category, language, seen=seen))
            if not collected:
                _log("[FETCH] Last resort: general feed")
                hl   = "te" if language == "te" else "en-IN"
                ceid = "IN:te" if language == "te" else "IN:en"
                general_url = (f"https://news.google.com/rss"
                               f"?hl={hl}&gl=IN&ceid={ceid}")
                collected.extend(
                    _fetch_rss_url(general_url, category, language,
                                   publisher_filter=None, seen=seen))

        _log(f"[FETCH] Total collected: {len(collected)}")
        # Bug 18: _smart_filter drops stale articles
        collected = _smart_filter(collected)
        _log(f"[FETCH] After freshness filter: {len(collected)} articles")
        return collected

    except Exception as e:
        _log(f"[FETCH] Unexpected exception: {type(e).__name__}: {str(e)[:100]}")
        return []
