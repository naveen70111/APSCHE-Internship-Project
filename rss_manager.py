"""
rss_manager.py  —  Chronicle Intelligence  v9-BUGFIX

BUG FIXES IN THIS VERSION
──────────────────────────
Bug 4  : _is_noise_para() expanded — detects trailing-headline noise words
         (horoscope, OTT, Related Stories, Tags, etc.) and discards them
         before they reach the article body.
Bug 7  : scrape_full_text() now checks is_article_complete(); if body is
         truncated (ends mid-sentence / < 30 words), retries extraction
         with min_words=5 fallback before giving up.
Bug 14 : _NOISE_TAGS expanded with script, style, iframe, nav, header,
         footer, aside, form, button, noscript, figure, figcaption, ins,
         svg, template, dialog, canvas, video, audio, object, embed.
         _remove_noise_elements() also strips data-* attribute blocks.
Bug 15 : _extract_best_image() now skips known logo/icon patterns
         (logo, icon, avatar, placeholder, sprite, pixel, blank) and
         re-validates every candidate through validate_image_url().
Bug 20 : Every network / parsing call wrapped in try/except with
         meaningful log messages; scrape_full_text() never raises.
"""

import urllib.request
import urllib.parse
import re
import json
import ssl
import socket
import time
from typing import Optional
from random import choice

import requests
from bs4 import BeautifulSoup

import content_cleaner
from config import (
    MIN_CONTENT_WORDS, MIN_PARAGRAPH_CHARS,
    SCRAPE_MAX_RETRIES, SCRAPE_TIMEOUT,
    DEBUG_LOGGING,
)


def _dprint(*args, **kwargs):
    if DEBUG_LOGGING:
        print(*args, **kwargs)


socket.setdefaulttimeout(SCRAPE_TIMEOUT)

_USER_AGENTS = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
     "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"),
]


def _random_ua() -> str:
    return choice(_USER_AGENTS)


# ─────────────────────────────────────────────────────────────
# Google News URL decoder
# ─────────────────────────────────────────────────────────────

try:
    from googlenewsdecoder import gnewsdecoder
    _HAS_GNEWS_DECODER = True
except ImportError:
    _HAS_GNEWS_DECODER = False
    _dprint("[WARN] 'googlenewsdecoder' not installed — Google News links "
            "will not be decoded to real article URLs.")


class SessionManager:
    def __init__(self):
        self.current_user     = None
        self.is_authenticated = False

    def login_session(self, username: str):
        self.current_user     = username
        self.is_authenticated = True

    def logout_session(self):
        self.current_user     = None
        self.is_authenticated = False


def clean_sentence_deduplicate(text_blocks: list[str]) -> list[str]:
    return content_cleaner.deduplicate_sentences(text_blocks)


_SSL_CTX = ssl._create_unverified_context()

_BASE_HEADERS = {
    "User-Agent":      _USER_AGENTS[0],
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "te-IN,te;q=0.9,en-IN;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.google.com/",
    "Connection":      "keep-alive",
}

_EXTRA_HEADERS = {
    "Cache-Control":  "no-cache",
    "Pragma":         "no-cache",
    "DNT":            "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
}

# ─────────────────────────────────────────────────────────────
# Bug 14: Expanded noise tag list
# ─────────────────────────────────────────────────────────────

_NOISE_TAGS = [
    # Original set
    "script", "style", "nav", "header", "footer", "aside",
    "form", "iframe", "ins", "button", "noscript",
    "figure", "figcaption",
    # Bug 14 additions
    "svg", "template", "dialog", "canvas",
    "video", "audio", "object", "embed",
    "link", "meta", "base",
    "select", "textarea", "input", "label",
    "map", "area", "picture",
]

_NOISE_CLASS_RE = re.compile(
    r'(social|share|related|recommend|comment|advertisement|'
    r'sidebar|widget|promo|subscribe|newsletter|footer|header|'
    r'navigation|breadcrumb|tags|author[-_]bio|also[-_]read|'
    r'popup|modal|cookie|banner|ad[-_]|ads[-_]|'
    r'trending|popular|most[-_]read|you[-_]may|'
    r'read[-_]more|more[-_]stories|pagination|'
    r'print|email[-_]share|whatsapp|telegram)',
    re.I
)

# Site-specific selectors
_SITE_SELECTORS: list[tuple[str, list[str]]] = [
    ("andhrajyothi", [
        "div.article-content", "div.story-content", "div.news-content",
        "div.article-body", "div#article-body", "div.newsDetail",
        "div.news-detail", "div.storyDetail", "div.contentarea",
        "div.content-area", "div.fullstory", "div.story",
        "div.artdetail", "div.art-detail", "section.article",
        "div.article-text", "div.post-content", "div.entry-content",
        "div.td-post-content", "div.tdb-block-inner",
        "div[class*='story']", "div[class*='article']",
        "div[class*='content']", "div[class*='news']",
        "article", "main",
    ]),
    ("eenadu", [
        "div.story-content", "div.article-body", "div.content-area",
        "div.news-content", "div#content", "div.story",
        "div.fulltext", "div.article-text", "div.post-content",
        "div[class*='story']", "div[class*='article']", "article",
    ]),
    ("sakshi", [
        "div.article-content", "div.story-content", "div.news-story",
        "div.article-body", "div.content", "div#articleContent",
        "div.fulltext", "div.post-content",
        "div[class*='story']", "div[class*='article']", "article",
    ]),
    ("hindustantimes", [
        "div.story-content", "div.article-body", "div.article-content",
        "div.full-details", "article", "div[class*='article']",
    ]),
    ("tupaki", [
        "div.article-content", "div.content", "article",
        "div[class*='story']", "div[class*='article']",
    ]),
]

_CONTENT_CLASS_RE = re.compile(
    r'(story[-_]?body|story[-_]?content|news[-_]?text|post[-_]?content|'
    r'article[-_]?body|entry[-_]?content|article[-_]?text|news[-_]?content|'
    r'main[-_]?content|content[-_]?body|td[-_]?module|newsarticle|'
    r'articlecontent|fullstory|full[-_]?article|article[-_]?detail|'
    r'post[-_]?body|blog[-_]?content|page[-_]?content)',
    re.I
)

# ─────────────────────────────────────────────────────────────
# Bug 15: Image quality filter
# ─────────────────────────────────────────────────────────────

_BAD_IMAGE_PATTERNS = re.compile(
    r'(?i)(logo|icon|avatar|placeholder|sprite|pixel|blank|'
    r'default[-_]?(?:image|img|photo|thumb)|'
    r'loading[-_]?image|noimage|no[-_]?image|'
    r'1x1|transparent|spacer)',
)


def _is_article_image(url: str) -> bool:
    """Bug 15: Reject logos, icons, placeholders, and other non-article images."""
    if not url:
        return False
    if not content_cleaner.validate_image_url(url):
        return False
    if _BAD_IMAGE_PATTERNS.search(url):
        return False
    # Must be a reasonably sized image path, not a tiny tracking pixel
    url_path = url.lower().split('?')[0]
    if re.search(r'/\d+x\d+\.(gif|png)$', url_path):
        # 1x1 or tiny tracking images
        dims = re.search(r'/(\d+)x(\d+)', url_path)
        if dims:
            w, h = int(dims.group(1)), int(dims.group(2))
            if w < 50 or h < 50:
                return False
    return True


# ─────────────────────────────────────────────────────────────
# Google News URL decode
# ─────────────────────────────────────────────────────────────

def resolve_google_news_url(url: str) -> str:
    if not url.startswith("https://news.google.com"):
        return url
    try:
        parsed    = urllib.parse.urlparse(url)
        gn_art_id = parsed.path.split("/")[-1]
        get_url   = f"https://news.google.com/articles/{gn_art_id}"
        req_get   = urllib.request.Request(get_url,
                                            headers={"User-Agent": _random_ua()})
        with urllib.request.urlopen(req_get, timeout=SCRAPE_TIMEOUT,
                                    context=_SSL_CTX) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        soup      = BeautifulSoup(html, "html.parser")
        if not soup:
            return url
        div       = soup.select_one("c-wiz > div")
        if not div:
            return url
        signature = div.get("data-n-a-sg")
        timestamp = div.get("data-n-a-ts")
        if not signature or not timestamp:
            return url
        articles_req = [
            "Fbv4je",
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
            f'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{gn_art_id}",{timestamp},"{signature}"]'
        ]
        payload_data = (
            f"f.req={urllib.parse.quote(json.dumps([[articles_req]]))}"
        )
        headers  = {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Referer":      "https://news.google.com/",
            "User-Agent":   _random_ua(),
        }
        req_post = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=payload_data.encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(req_post, timeout=SCRAPE_TIMEOUT,
                                    context=_SSL_CTX) as resp_post:
            text = resp_post.read().decode("utf-8", errors="ignore")
        parts = text.split("\n\n")
        if len(parts) > 1:
            raw_data    = json.loads(parts[1])
            inner_json  = json.loads(raw_data[0][2])
            decoded_url = inner_json[1]
            if decoded_url.startswith("http"):
                return decoded_url
    except Exception:
        pass
    return url


def decode_google_news_url(url: str) -> str:
    if "news.google.com" not in url:
        return url
    if _HAS_GNEWS_DECODER:
        try:
            result = gnewsdecoder(url, interval=None)
            if result and result.get("status") and result.get("decoded_url"):
                decoded = result["decoded_url"]
                _dprint(f"[DECODE] OK: {url[:55]}... -> {decoded[:70]}")
                return decoded
            msg = (result or {}).get("message", "unknown error")
            _dprint(f"[DECODE] gnewsdecoder failed: {msg[:80]}")
        except Exception as e:
            _dprint(f"[DECODE] gnewsdecoder exception: {str(e)[:80]}")
    resolved = resolve_google_news_url(url)
    if resolved != url and "news.google.com" not in resolved:
        _dprint(f"[DECODE] Batchexecute OK: {resolved[:70]}")
        return resolved
    _dprint("[DECODE] All strategies failed, using original link")
    return url


def decode_html_bytes(content: bytes, content_type_header: str = "") -> str:
    if not content:
        return ""
    encoding = None
    if content_type_header:
        match = re.search(r'charset=([\w-]+)', content_type_header, re.I)
        if match:
            encoding = match.group(1).strip()
    if not encoding:
        meta_charset = re.search(
            rb'<meta[^>]+charset=["\']?([\w-]+)["\']?', content, re.I)
        if meta_charset:
            encoding = meta_charset.group(1).decode('ascii', errors='ignore').strip()
    if not encoding:
        try:
            import charset_normalizer
            result = charset_normalizer.from_bytes(content).best()
            if result:
                encoding = result.encoding
        except ImportError:
            try:
                import chardet
                result = chardet.detect(content)
                if result and result.get('confidence', 0) > 0.5:
                    encoding = result.get('encoding')
            except ImportError:
                pass
    if not encoding:
        encoding = 'utf-8'
    for enc in (encoding, 'utf-8', 'latin-1'):
        try:
            return content.decode(enc)
        except Exception:
            continue
    return content.decode('utf-8', errors='replace')


def _fetch_html(url: str) -> Optional[str]:
    url_lower       = url.lower()
    is_telugu_site  = any(s in url_lower for s in [
        "andhrajyothi", "eenadu", "sakshi", "hindustantimes",
        "tupaki", "tv9", "abp", "ntv", "hmm",
    ])
    for attempt in range(SCRAPE_MAX_RETRIES):
        headers = dict(_BASE_HEADERS)
        headers["User-Agent"] = _random_ua()
        if is_telugu_site:
            headers.update(_EXTRA_HEADERS)
        try:
            r = requests.get(url, headers=headers,
                             timeout=SCRAPE_TIMEOUT, verify=False)
            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                return decode_html_bytes(r.content, content_type)
            _dprint(f"[FETCH] HTTP {r.status_code} attempt {attempt+1} for {url[:60]}")
        except Exception as e:
            _dprint(f"[FETCH] Exception attempt {attempt+1}: {str(e)[:80]}")
            if attempt < SCRAPE_MAX_RETRIES - 1:
                time.sleep(0.8)
    return None


# ─────────────────────────────────────────────────────────────
# Bug 15: Improved image extraction
# ─────────────────────────────────────────────────────────────

def _extract_best_image(soup: BeautifulSoup, base_url: str) -> str:
    """
    Bug 15: Extract the best article image, skipping logos/icons/avatars.
    Tries meta tags first (most reliable), then article/main container imgs.
    """
    if not soup:
        return ""
    candidates: list[str] = []
    try:
        # Priority 1: Open Graph / Twitter meta tags
        for attr, name in [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name",     "twitter:image"),
            ("name",     "twitter:image:src"),
            ("itemprop", "image"),
        ]:
            tag = soup.find("meta", {attr: name})
            if tag:
                img = tag.get("content", "").strip()
                if img:
                    if not img.startswith(("http://", "https://")):
                        img = urllib.parse.urljoin(base_url, img)
                    if _is_article_image(img):
                        candidates.append(img)

        link_tag = soup.find("link", {"rel": "image_src"})
        if link_tag:
            href = link_tag.get("href", "").strip()
            if href:
                if not href.startswith(("http://", "https://")):
                    href = urllib.parse.urljoin(base_url, href)
                if _is_article_image(href):
                    candidates.append(href)

        # Priority 2: Images inside article/main containers
        for container in soup.find_all(["article", "main"]):
            if not container:
                continue
            for img_tag in container.find_all("img"):
                if not img_tag:
                    continue
                src = img_tag.get("src", "") or img_tag.get("data-src", "")
                if not src:
                    continue
                if not src.startswith(("http://", "https://")):
                    src = urllib.parse.urljoin(base_url, src)
                try:
                    w = int(str(img_tag.get("width",  "0")).replace("px", ""))
                    h = int(str(img_tag.get("height", "0")).replace("px", ""))
                    if w >= 200 and h >= 100 and _is_article_image(src):
                        candidates.append(src)
                        break
                except Exception:
                    if _is_article_image(src):
                        candidates.append(src)

        # Return first valid candidate
        for c in candidates:
            if _is_article_image(c):
                return c
    except Exception as e:
        _dprint(f"[IMAGE] Extraction error: {str(e)[:60]}")
    return ""


# ─────────────────────────────────────────────────────────────
# Bug 14: Aggressive noise removal
# ─────────────────────────────────────────────────────────────

def _remove_noise_elements(container) -> None:
    """Bug 14: Remove all noise HTML elements before paragraph extraction."""
    if not container:
        return
    try:
        # Remove noise tags
        for tag in container(_NOISE_TAGS):
            tag.decompose()
        # Remove noise classes
        for tag in container.find_all(True):
            classes = " ".join(tag.get("class") or [])
            if _NOISE_CLASS_RE.search(classes):
                tag.decompose()
            # Bug 14: also remove data-ad, data-widget, data-tracking attributes
            tag_attrs = dict(tag.attrs) if hasattr(tag, 'attrs') else {}
            for attr in tag_attrs:
                if attr.startswith(('data-ad', 'data-widget', 'data-track',
                                    'data-analytics', 'data-ga')):
                    tag.decompose()
                    break
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Bug 4: Expanded noise paragraph detector
# ─────────────────────────────────────────────────────────────

# Words that mark a paragraph as navigation / junk (Bug 4)
_PARA_NOISE_WORDS = [
    # Existing
    "cookie", "privacy policy", "terms of", "sign in", "subscribe",
    "newsletter", "all rights reserved", "copyright ©", "©",
    "advertisement", "follow us on", "share this", "download app",
    "photos view all", "view all photos", "photo gallery",
    "watch video", "watch now", "play video", "video:",
    "slideshow", "click here", "read more", "also read",
    "continue reading", "related news", "trending now",
    # Telugu noise
    "గమనిక", "ఇదీ చదవండి", "ఇది కూడా చదవండి", "మరిన్ని వార్తలు",
    "వాట్సాప్", "టెలిగ్రామ్", "youtube.com", "facebook.com",
    "twitter.com", "instagram.com", "t.me/",
    "ఫొటోలు చూడండి", "వీడియో చూడండి", "మరింత చదవండి",
    "ట్రెండింగ్", "తాజా వార్తలు", "సంబంధిత వార్తలు",
    # Bug 4 additions — trailing headline indicators
    "horoscope", "also read:", "read also:", "see also:",
    "related stories", "related articles", "more stories",
    "you may like", "you may also like", "recommended",
    "big stories", "top stories", "trending stories",
    "popular stories", "latest stories", "breaking stories",
    "english summary", "ai summary", "machine summary",
    "translation summary", "in brief", "quick facts",
    "previous story", "next story", "read latest news",
    "tags:", "categories:", "topics:", "keywords:",
    "font size", "text size", "image credit", "photo credit",
    "getty images", "reuters", "afp photo", "ap photo",
    "staff reporter", "desk report", "bureau report",
    "internet desk", "web desk", "news desk", "digital desk",
]


def _is_noise_para(text: str) -> bool:
    """
    Bug 4: Return True for paragraphs that are clearly navigation /
    junk / trailing headlines — should be excluded from article body.
    """
    if not text or len(text.strip()) < 5:
        return True
    t    = text.lower()
    hits = sum(1 for w in _PARA_NOISE_WORDS if w in t)
    if hits >= 2:
        return True
    # Single-line that looks like a section heading with no sentence content
    stripped = text.strip()
    if (len(stripped.split()) <= 5
            and not re.search(r'[.!?।]', stripped)
            and stripped.isupper()):
        return True
    return False


def _paras_from_container(container, min_len: int) -> list[str]:
    if not container:
        return []
    try:
        _remove_noise_elements(container)
        paras: list[str] = []
        for p in container.find_all(["p", "div"], recursive=True):
            if not p:
                continue
            if p.name == "div" and p.find(["p", "article", "section"]):
                continue
            t = p.get_text(separator=" ").strip() if p else ""
            t = re.sub(r'\s+', ' ', t)
            if len(t) >= min_len and not _is_noise_para(t):
                paras.append(t)
        return paras
    except Exception:
        return []


def _wc(paras: list[str]) -> int:
    return sum(len(p.split()) for p in paras if p)


def _extract_meta_description(soup: BeautifulSoup) -> str:
    if not soup:
        return ""
    try:
        for attr, name in [
            ("property", "og:description"),
            ("name",     "twitter:description"),
            ("name",     "description"),
        ]:
            tag = soup.find("meta", {attr: name})
            if tag:
                content = (tag.get("content") or "").strip()
                content = re.sub(r'\s+', ' ', content)
                if len(content) >= MIN_PARAGRAPH_CHARS:
                    return content
    except Exception:
        pass
    return ""


def _extract_paragraphs(soup: BeautifulSoup, url: str = "") -> list[str]:
    if not soup:
        return []
    min_len   = MIN_PARAGRAPH_CHARS
    url_lower = url.lower()

    # Tier 0: site-specific selectors
    for site_key, selectors in _SITE_SELECTORS:
        if site_key in url_lower:
            for selector in selectors:
                try:
                    containers = soup.select(selector)
                    if not containers:
                        continue
                    paras: list[str] = []
                    for c in containers:
                        if c:
                            paras.extend(_paras_from_container(c, min_len))
                    if _wc(paras) >= MIN_CONTENT_WORDS:
                        return paras
                except Exception:
                    continue

    # Tier 1: semantic tags
    paras = []
    for tag in soup.find_all(["article", "main"]):
        if tag:
            paras.extend(_paras_from_container(tag, min_len))
    if _wc(paras) >= MIN_CONTENT_WORDS:
        return paras

    # Tier 1.5: itemprop="articleBody"
    paras_15 = []
    for tag in soup.find_all(attrs={"itemprop": re.compile(r"articleBody", re.I)}):
        if tag:
            paras_15.extend(_paras_from_container(tag, min_len))
    if _wc(paras_15) >= MIN_CONTENT_WORDS:
        return paras_15
    if _wc(paras_15) > _wc(paras):
        paras = paras_15

    # Tier 2: content-class divs
    paras_2 = []
    for div in soup.find_all(["div", "section"], class_=_CONTENT_CLASS_RE):
        if div:
            paras_2.extend(_paras_from_container(div, min_len))
    if _wc(paras_2) >= MIN_CONTENT_WORDS:
        return paras_2
    if _wc(paras_2) > _wc(paras):
        paras = paras_2

    # Tier 3: largest div by <p> count
    try:
        for tag in soup(_NOISE_TAGS):
            tag.decompose()
        best_div   = None
        best_count = 0
        for div in soup.find_all(["div", "section"]):
            if not div:
                continue
            n = len(div.find_all("p"))
            if n > best_count:
                best_count = n
                best_div   = div
        if best_div and best_count >= 3:
            paras_3 = _paras_from_container(best_div, min_len)
            if _wc(paras_3) >= MIN_CONTENT_WORDS:
                return paras_3
            if _wc(paras_3) > _wc(paras):
                paras = paras_3
    except Exception:
        pass

    # Tier 4: all <p> tags
    paras_4 = []
    for p in soup.find_all("p"):
        if p:
            t = p.get_text(separator=" ").strip()
            t = re.sub(r'\s+', ' ', t)
            if len(t) >= min_len and not _is_noise_para(t):
                paras_4.append(t)
    if _wc(paras_4) > _wc(paras):
        paras = paras_4

    return paras


_SKIP_URL_PATTERNS = re.compile(
    r'/(video|videos|photos|photo|gallery|galleries|cartoon|'
    r'cartoons|slideshow|reels|shorts|watch)/', re.I
)


def _is_scrapeable(url: str) -> bool:
    if not url:
        return False
    return _SKIP_URL_PATTERNS.search(url) is None


# ─────────────────────────────────────────────────────────────
# Main scrape function (Bugs 7, 14, 15, 20)
# ─────────────────────────────────────────────────────────────

def scrape_full_text(url: str) -> tuple[str, str]:
    """
    Scrape article text and best image.  Returns (clean_text, image_url).
    Both may be empty strings on failure — never raises.

    Bug 7  : If extracted text appears truncated, retries with min_words=5.
    Bug 14 : Expanded noise tag removal before paragraph extraction.
    Bug 15 : Image validated through _is_article_image() — logos / icons skipped.
    Bug 20 : All exceptions caught; meaningful log messages emitted.
    """
    import config
    try:
        resolved = decode_google_news_url(url)
        if "news.google.com" in resolved:
            resolved = url

        if not _is_scrapeable(resolved):
            _dprint(f"[SCRAPE] Non-article URL skipped: {resolved[:70]}")
            config.log_scrape_fail(resolved)
            return "", ""

        raw_html = _fetch_html(resolved)
        if not raw_html:
            _dprint(f"[SCRAPE] No HTML for {resolved[:70]}")
            config.log_scrape_fail(resolved)
            return "", ""

        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except Exception as e:
            _dprint(f"[SCRAPE] BeautifulSoup failed: {str(e)[:60]}")
            config.log_scrape_fail(resolved)
            return "", ""

        if not soup:
            config.log_scrape_fail(resolved)
            return "", ""

        # Bug 15: extract and validate image
        image_url = _extract_best_image(soup, resolved)
        if not _is_article_image(image_url):
            image_url = ""

        raw_paras = _extract_paragraphs(soup, url=resolved)

        # Fallback to meta description when body extraction fails
        if _wc(raw_paras) < 15:
            meta_desc = _extract_meta_description(soup)
            if meta_desc:
                if _wc(raw_paras) == 0:
                    raw_paras = [meta_desc]
                elif meta_desc not in " ".join(raw_paras):
                    raw_paras = raw_paras + [meta_desc]

        if not raw_paras:
            config.log_scrape_fail(resolved)
            return "", image_url

        lang = "te" if any(x in resolved.lower() for x in [
            "andhrajyothi", "eenadu", "sakshi", "hindustantimes", "tupaki",
        ]) else "en"

        # Bug 14: clean_metadata + build_clean_article strips all HTML junk
        clean_text = content_cleaner.build_clean_article(
            "\n\n".join(raw_paras), language=lang,
            min_words=MIN_CONTENT_WORDS,
        )

        # Bug 7: if truncated, retry with lower threshold
        if not clean_text or not content_cleaner.is_article_complete(clean_text):
            _dprint(f"[SCRAPE] Incomplete extraction, retrying with min_words=5")
            clean_text = content_cleaner.build_clean_article(
                "\n\n".join(raw_paras), language=lang, min_words=5)

        if not clean_text:
            _dprint(f"[SCRAPE] No clean text extracted from {resolved[:70]}")
            config.log_scrape_fail(resolved)
            return "", image_url

        # Bug 4: remove trailing junk from scraped text
        clean_text = content_cleaner.remove_trailing_junk(clean_text)
        # Bug 16: dedup paragraphs
        clean_text = content_cleaner.remove_repeated_paragraphs(clean_text)

        config.log_scrape_success(resolved)
        return clean_text, image_url

    except Exception as e:
        # Bug 20: never crash — log and return empty
        _dprint(f"[SCRAPE] Unexpected error for {url[:70]}: {type(e).__name__}: {str(e)[:100]}")
        try:
            import config as _config
            _config.log_scrape_fail(url)
        except Exception:
            pass
        return "", ""


def filter_important_articles(articles: list, prefs: list) -> list:
    if not articles:
        return []
    tech_on   = "Tech"   in prefs
    sports_on = "Sports" in prefs
    filtered  = []
    for art in articles:
        if not art:
            continue
        cat = (art.get("category") or "").lower()
        if tech_on and sports_on:
            if cat not in ("technology", "sports"):
                continue
        elif tech_on:
            if cat != "technology":
                continue
        elif sports_on:
            if cat != "sports":
                continue
        filtered.append(art)
    seen_urls: set[str] = set()
    unique: list        = []
    for art in filtered:
        if not art:
            continue
        u = art.get("url", "").strip()
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique.append(art)
    return unique


def rank_articles(articles: list, prefs) -> list:
    if not articles:
        return []
    return sorted([a for a in articles if a],
                  key=lambda x: x.get("score", 0), reverse=True)
