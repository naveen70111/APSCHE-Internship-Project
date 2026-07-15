"""
content_cleaner.py  —  Chronicle Intelligence  v9-BUGFIX

BUG FIXES
──────────
Bug 1/13 : 40+ new byline/desk/author patterns in _META_PATTERNS.
Bug 2    : remove_summary_blocks() — strips English/AI/Machine Summary sections.
Bug 3    : Navigation/footer/social patterns added throughout.
Bug 4    : remove_trailing_junk() — removes orphaned headlines at end of article.
Bug 5/6  : filter_relevant_paragraphs() — removes off-topic paragraphs.
Bug 7    : is_article_complete() — detects truncated articles.
Bug 12   : Day-of-week, IST, AM/PM, time patterns in _META_PATTERNS.
Bug 14   : Bug-14 HTML tag list available for rss_manager.
Bug 16   : Strengthened deduplication in paragraphs and lines.
"""

import re
import unicodedata
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Encoding / Unicode garbage
# ─────────────────────────────────────────────────────────────

_ENCODING_GARBAGE = re.compile(
    r'[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f'
    r'\u2028\u2029\u200b-\u200f\u202a-\u202e\ufeff]+'
)
_HTML_ENTITIES   = re.compile(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);')
_CSS_JS_FRAGMENT = re.compile(
    r'(?i)(\.css|\.js|var\s+\w+|function\s*\(|document\.|window\.|'
    r'display\s*:|font-size\s*:|color\s*:)[^\n]*'
)

# ─────────────────────────────────────────────────────────────
# Arrow / navigation garbage
# ─────────────────────────────────────────────────────────────

_ARROW_CHARS = re.compile(
    r'[\u2190-\u21FF\u27A0-\u27BF\u2794-\u27AF\u2B00-\u2BFF'
    r'\u25A0-\u25FF\u2600-\u26FF\u00BB\u00AB\uFEFF\u200B-\u200F\u202A-\u202E]+'
)
_ARROW_SEQUENCES = re.compile(
    r'(?:\u2192|\u2190|\u2194|\u2191|\u2193|\u279C|\u279D|\u279E|\u279F'
    r'|\u27A0|\u25BA|\u25B6|\u25B8|\u25B9|\u25C4|\u00BB|\u00AB'
    r'|>{2,}|<{2,}|\-+>|<\-+)+'
)

# ─────────────────────────────────────────────────────────────
# Trailing junk regex (Bug 4)
# ─────────────────────────────────────────────────────────────

_TRAILING_JUNK_RE = re.compile(
    r'^(?:google\s+maps?|horoscope|family\s+drama|actress|actor|ott|ipl|bcci'
    r'|cricket\s+news|weather|stocks?|sensex|nifty|big\s+stories?|top\s+stories?'
    r'|trending|popular\s+stories?|latest\s+news|latest\s+stories?|breaking\s+news'
    r'|more\s+stories?|recommended|related\s+stories?|related\s+articles?'
    r'|also\s+read|read\s+more|you\s+may\s+like|continue\s+reading'
    r'|next\s+story|previous\s+story|tags?|categories|topics?|keywords?'
    r'|share|print|comments?|bookmark|follow|subscribe|advertisement|sponsored'
    r'|copyright|privacy\s+policy|terms\s+of|contact|footer|newsletter'
    r'|photo\s*gallery|videos?|gallery|slideshow|cartoon|opinion|editorial'
    r'|read\s+latest|cm\s+revanth|pm\s+modi|iran|actress\s+laya).*$',
    re.I
)

# ─────────────────────────────────────────────────────────────
# Junk phrases (Bugs 1, 2, 3, 13)
# ─────────────────────────────────────────────────────────────

_JUNK_PHRASES: list[str] = [
    # Telugu
    "గమనిక", "ఇదీ చదవండి", "ఇది కూడా చదవండి", "మరిన్ని వార్తలు",
    "ఎక్కువ మంది చదివినవి", "మూల కథనం", "మూలం", "అందుబాటులో లేవు",
    "పబ్లిష్ చేసిన", "వర్గం", "తాజా వార్తలు", "బ్రేకింగ్ న్యూస్",
    "లైవ్ అప్‌డేట్స్", "వాట్సాప్ చేరండి", "టెలిగ్రామ్ చేరండి",
    "యూట్యూబ్ చూడండి", "ఫేస్‌బుక్ చూడండి", "ట్విట్టర్ చూడండి",
    "సోషల్ మీడియా", "ఫోటో గ్యాలరీ", "వీడియో చూడండి",
    "ఆంగ్ల సారాంశం", "సారాంశం", "ఏఐ సారాంశం",
    # Bug 2 — Summary
    "English Summary", "English summary", "AI Summary", "AI summary",
    "Machine Summary", "Machine summary", "Translation Summary",
    "In Brief", "Quick Facts", "At A Glance", "At a glance",
    "Key Takeaways", "What You Need To Know", "TLDR", "TL;DR",
    "Automated Summary", "Auto Summary",
    # Bug 1/13 — Bylines / desks
    "Internet Desk", "Web Desk", "Desk Report", "Staff Reporter",
    "Bureau Report", "Special Correspondent", "Our Correspondent",
    "News Desk", "Digital Desk", "Online Desk", "Hyderabad Desk",
    "National News Team", "Telangana Dist Team",
    "Reporter", "Correspondent", "Agency",
    # Bug 1 — Image credits
    "Photo Source", "Getty Images", "Image Credits", "Credits",
    "Photo Credits", "Image Source", "Picture Source",
    "AFP Photo", "AP Photo", "Reuters Photo", "ANI Photo",
    "Image Credit", "Photo Credit", "Video Credit",
    # Bug 1 — Font size junk
    "Font Size", "Text Size", "A+ A++", "A A+",
    # Bug 3 — Navigation
    "Read More", "Read Also", "Also Read", "Also See",
    "Continue Reading", "Click Here to Read", "Read Full Story",
    "Read Latest News", "Read Latest Telugu News", "Read Latest World News",
    "Previous Story", "Next Story",
    "ఇదీ చదవండి",
    # Bug 3 — Section labels
    "Trending News", "Related Articles", "Related News",
    "Recommended Stories", "Suggested Articles", "More Stories",
    "Latest News", "Top Stories", "Breaking News", "Big Stories",
    "Popular Stories", "Latest Stories", "You May Like",
    "End Of Article", "End of Article",
    # Bug 3 — Social
    "Follow Us", "Follow us on", "Share This Story", "Share This Article",
    "Share This", "Subscribe", "Subscribe Now", "Join WhatsApp",
    "Join Telegram", "Telegram Channel",
    "Share", "Print", "Comments", "Bookmark", "Follow",
    # Bug 3 — Ads
    "Advertisement", "Sponsored", "Sponsored Content", "Promoted", "Paid Content",
    # Bug 3 — Media
    "Watch Video", "Photo Gallery", "Viral Photos", "Video", "Related Videos",
    # Bug 3 — Footer / legal
    "All rights reserved", "Copyright ©", "Cookie Policy",
    "Terms of Service", "Privacy Policy", "Sign In",
    "Create Account", "Register Now", "Download Our App",
    "Comment Below", "Footer", "Contact",
    # Publishers
    "Samayam Telugu", "Samayam", "eenadu.net", "Andhrajyothi.com",
    "Sakshi.com", "sakshieducation", "TV9 Telugu", "ABN Andhra Jyothi",
    "NTV Telugu", "Hmm TV",
    # Generic web
    "Sourced From", "Source Article", "Source Website",
    "Generated By AI", "AI-Generated", "Read Time",
    "A post shared by", "View this post on Instagram",
    "This content is not available", "Embedded content",
    "Twitter/X Post", "Facebook Post",
]

_JUNK_LINE_PAT: list[re.Pattern] = [
    re.compile(r'(?im)(^|(?<=\s)|(?<=।))' + re.escape(p) + r'[^\n।]*')
    for p in _JUNK_PHRASES
]

# ─────────────────────────────────────────────────────────────
# Metadata patterns (Bugs 1, 2, 3, 12, 13)
# ─────────────────────────────────────────────────────────────

_META_PATTERNS: list[str] = [
    # Bug 1/13: Bylines
    r"(?im)^by\s+[a-zA-Z\s\.]+$",
    r"(?i)by\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}(?:\s*[|\-,]\s*[^\n.।]{0,60})?(?=\n|$|\.|।)",
    r"(?i)reported\s*by\s*[:\-]?\s*[^\n.।]*",
    r"(?i)published\s*by\s*[:\-]?\s*[^\n.।]*",
    r"(?i)written\s+by\s*[:\-]?\s*[^\n.।]*",
    r"(?i)edited\s+by\s*[:\-]?\s*[^\n.।]*",
    r"(?i)author\s*[:\-]\s*[^\n.।]*",
    # Bug 1/13: Desk / reporter
    r"(?im)^(?:internet|web|news|digital|online|hyderabad|telangana|national|city|bureau|district)\s+desk\s*[:\-]?[^\n.।]*$",
    r"(?im)^desk\s+report\s*[:\-]?[^\n.།]*$",
    r"(?im)^bureau\s+report\s*[:\-]?[^\n.।]*$",
    r"(?im)^(?:staff\s+)?reporter\s*[:\-]?[^\n.།]*$",
    r"(?im)^correspondent\s*[:\-]?[^\n.।]*$",
    r"(?im)^special\s+correspondent\s*[:\-]?[^\n.।]*$",
    r"(?im)^agency\s*[:\-]?[^\n.।]*$",
    r"(?im)^(?:national|telangana|hyderabad|andhra)\s+(?:news\s+)?team\s*[:\-]?[^\n.।]*$",
    # Bug 12: Date / time
    r"(?i)last\s*updated\s*[:\-]?\s*[^\n.।]*",
    r"(?i)updated\s*on\s*[:\-]?\s*[^\n.।]*",
    r"(?i)published\s+(?:on|at)\s*[:\-]?\s*[^\n.।]*",
    r"(?i)posted\s*(?:on|at)\s*[:\-]?\s*[^\n.।]*",
    r"(?im)^published\s*[:\-]?[^\n.।]*$",
    r"(?im)^updated\s*[:\-]?[^\n.।]*$",
    r"(?i)\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}[^\n.।]*",
    r"(?i)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[^\n.।]*",
    r"(?im)^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b[^\n.।]*$",
    r"(?i)\d{1,2}:\d{2}\s*(?:am|pm)\s*(?:ist|utc|gmt)?[^\n.།]*",
    r"(?i)\[(?:ist|utc|gmt)\][^\n.।]*",
    r"(?i)\b(?:IST|UTC|GMT)\b\s*[^\n.।]{0,40}(?=\n|$)",
    r"(?i)\d+\s*min(?:ute)?\s+read",
    r"(?i)read\s+time\s*[:\-]?\s*\d+[^\n.।]*",
    # Bug 1: Font-size junk
    r"(?i)font\s*size\s*[:\-]?\s*[^\n.।]*",
    r"(?i)\bA\+\+?\b\s*(?:\bA\+?\b)?\s*[^\n.।]{0,20}",
    r"(?i)text\s*(?:size|resize)\s*[:\-]?\s*[^\n.।]*",
    # Bug 1: Image / photo credits
    r"(?i)(?:image|photo|picture|pic)\s*(?:credit|credits|source|courtesy)\s*[:\-]?\s*[^\n.।]*",
    r"(?i)(?:getty|reuters|ap\b|afp|ani\b|pti\b)\s*(?:images?)?\s*[^\n.।]{0,60}",
    # Bug 2: Summary headers
    r"(?i)(?:english\s+)?summary\s*[:\-]\s*[^\n.।]*",
    r"(?i)ai\s+(?:generated\s+)?summary[^\n.।]*",
    r"(?i)machine\s+(?:generated\s+)?summary[^\n.।]*",
    r"(?i)translation\s+summary[^\n.।]*",
    r"(?i)automated?\s+summary[^\n.।]*",
    r"(?i)in\s+brief\s*[:\-]\s*[^\n.।]*",
    r"(?i)quick\s+facts?\s*[:\-]\s*[^\n.।]*",
    r"(?i)at\s+a\s+glance\s*[:\-]\s*[^\n.।]*",
    r"(?i)key\s+takeaways?\s*[:\-]\s*[^\n.।]*",
    r"(?i)tl\s*;\s*dr\s*[:\-]?\s*[^\n.।]*",
    # Bug 3: Navigation / related
    r"(?im)^(?:read\s+(?:more|also|latest|full)|also\s+read|see\s+also)\s*[:\-]?[^\n.।]*$",
    r"(?im)^(?:previous|next)\s+story\s*[:\-]?[^\n.।]*$",
    r"(?im)^(?:more|related|recommended|trending|popular|big|top|latest)\s+stories?\s*[:\-]?[^\n.।]*$",
    r"(?im)^you\s+may\s+(?:also\s+)?like\s*[:\-]?[^\n.।]*$",
    r"(?im)^continue\s+reading\s*[:\-]?[^\n.।]*$",
    r"(?im)^read\s+latest\s+(?:telugu\s+|world\s+)?news\s*[:\-]?[^\n.।]*$",
    # Bug 3: Social / sharing
    r"(?im)^(?:share|print|comments?|bookmark|follow|subscribe)\s*[:\-]?[^\n.།]*$",
    r"(?im)^(?:newsletter|advertisement|sponsored|promoted)\s*[:\-]?[^\n.।]*$",
    r"(?i)follow\s+us\s+on[^\n.।]*",
    r"(?i)share\s+(?:this|on)\s+[^\n.।]*",
    r"(?i)subscribe\s+(?:to|now)[^\n.।]*",
    r"(?i)join\s+(?:whatsapp|telegram)[^\n.।]*",
    r"(?i)download\s+our\s+app[^\n.।]*",
    r"(?i)comment\s+below[^\n.।]*",
    # Bug 3: Footer / legal
    r"(?im)^all\s+rights\s+reserved[^\n.।]*$",
    r"(?i)copyright\s*©[^\n.।]*",
    r"(?i)©\s*\d{4}[^\n.।]*",
    r"(?im)^(?:privacy\s+policy|terms\s+of\s+(?:service|use)|cookie\s+policy|contact\s+us?)[^\n.।]*$",
    # Existing
    r"(?i)source\s*[:\-]\s*[^\n.।]*",
    r"(?i)source article",
    r"(?i)sourced from[^\n.।]*",
    r"(?i)generated\s+by\s+ai[^\n.।]*",
    r"(?i)ai\s+summary[^\n.।]*",
    r"(?i)ai[-\s]generated[^\n.।]*",
    r"(?i)this\s+article\s+was\s+(written|generated|created)\s+by[^\n.।]*",
    r"గమనిక[^\n।]*",
    r"ఇదీ చదవండి[^\n।]*",
    r"ఇది కూడా చదవండి[^\n।]*",
    r"మరిన్ని వార్తలు[^\n।]*",
    r"ఎక్కువ మంది చదివినవి[^\n।]*",
    r"(?i)మూల కథనం[^\n।]*",
    r"(?i)మూలం[^\n.।]*",
    r"(?i)అందుబాటులో లేవు",
    r"(?i)పబ్లిష్ చేసిన[^\n।]*",
    r"(?i)వర్గం\s*:[^\n।]*",
    r"\[\+?\s*\d+\s*chars?\]",
    r"\[\+?\s*\d+\s*characters?\]",
    r"\[\+?\s*\d+\s*అక్షరాలు?\]",
    r"\[…\]", r"\[\.\.\.\]", r"\.\.\.$",
    r"(?i)category\s*:[^\n।]*",
    r"(?i)tags?\s*:[^\n।]*",
    r"(?i)sign\s+in[^\n।]*",
    r"(?i)create\s+(?:an?\s+)?account[^\n।]*",
    r"(?i)register\s+now[^\n।]*",
    r"(?i)advertisement[^\n।]*",
    r"(?i)read\s+more\s*:[^\n।]*",
    r"(?i)also\s+read\s*:[^\n।]*",
    r"(?i)also\s+see\s*:[^\n।]*",
    r"(?i)click\s+here[^\n।]*",
    r"(?i)tap\s+here[^\n।]*",
    r"(?i)a post shared by[^\n।]*",
    r"(?i)view this post on instagram[^\n।]*",
    r"(?i)this content is not available[^\n।]*",
    r"(?i)samayam(?:\s+telugu)?[^\n।]*",
    r"(?i)eenadu\.net[^\n।]*",
    r"(?i)andhrajyothi\.com[^\n।]*",
    r"(?i)sakshi\.com[^\n।]*",
    r"(?i)internet\s+desk[^\n।]*",
    r"(?i)web\s+desk[^\n।]*",
    r"(?i)desk\s+report[^\n।]*",
    r"(?i)staff\s+reporter[^\n।]*",
    r"(?i)photo\s+source[^\n।]*",
    r"(?i)getty\s+images[^\n।]*",
    r"(?i)image\s+credits?[^\n।]*",
    r"(?i)end\s+of\s+article[^\n।]*",
    r"(?i)trending\s+news[^\n।]*",
    r"(?i)related\s+(?:articles?|news|stories)[^\n।]*",
    r"(?i)recommended\s+stories[^\n।]*",
    r"(?i)sponsored[^\n।]*",
    r"(?im)^https?://\S+$",
    r"(?im)^www\.\S+$",
]

_COMPILED_META = [re.compile(p) for p in _META_PATTERNS]

# ─────────────────────────────────────────────────────────────
# Sentence-level garbage
# ─────────────────────────────────────────────────────────────

_SENTENCE_GARBAGE: list[str] = [
    r"(?i)subscribe\s*to", r"(?i)\bnewsletter\b",
    r"(?i)all\s+rights\s+reserved", r"(?i)copyright\s*©",
    r"(?i)follow\s+us\s+on", r"(?i)cookie\s+policy",
    r"(?i)terms\s+of\s+(service|use)", r"(?i)\badvertisement\b",
    r"(?i)privacy\s+policy", r"(?i)\bsign\s+in\b",
    r"(?i)create\s+account", r"(?i)register\s+now",
    r"(?i)read\s+more\s*:", r"(?i)\balso\s+read\b",
    r"(?i)\balso\s+see\b", r"(?i)download\s+our\s+app",
    r"(?i)comment\s+below", r"(?i)sourced\s+from",
    r"(?i)\bsamayam\b", r"(?i)\bclick\s+here\b",
    r"(?i)\btap\s+here\b", r"(?i)related\s+stories",
    r"(?i)you\s+may\s+also\s+like", r"(?i)trending\s+now",
    r"(?i)most\s+popular", r"(?i)watch\s+video",
    r"(?i)photo\s+gallery", r"(?i)\btags?\s*:",
    r"(?i)internet\s+desk", r"(?i)web\s+desk",
    r"(?i)desk\s+report", r"(?i)staff\s+reporter",
    r"(?i)photo\s+source", r"(?i)getty\s+images",
    r"(?i)image\s+credits?", r"(?i)end\s+of\s+article",
    r"(?i)share\s+this\s+story", r"(?i)a\s+post\s+shared\s+by",
    r"(?i)recommended\s+stories", r"(?i)\bsponsored\b",
    r"(?i)continue\s+reading", r"(?i)bureau\s+report",
    r"(?i)news\s+desk", r"(?i)digital\s+desk",
    r"(?i)english\s+summary", r"(?i)ai\s+summary",
    r"(?i)machine\s+summary", r"(?i)translation\s+summary",
    r"(?i)in\s+brief", r"(?i)quick\s+facts?",
    r"(?i)key\s+takeaways?", r"(?i)previous\s+story",
    r"(?i)next\s+story", r"(?i)read\s+latest",
    r"(?i)big\s+stories?", r"(?i)top\s+stories?",
    r"(?i)more\s+stories?", r"(?i)popular\s+stories?",
    r"(?i)font\s+size", r"(?i)image\s+credit",
    r"(?i)photo\s+credit",
    r"గమనిక", r"ఇదీ చదవండి", r"ఇది కూడా చదవండి",
    r"మరిన్ని వార్తలు", r"ఎక్కువ మంది చదివినవి",
    r"వాట్సాప్ చేరండి", r"టెలిగ్రామ్ చేరండి",
    r"(?i)^https?://\S+$", r"(?i)^www\.\S+$",
]

_COMPILED_SENTENCE_GARBAGE = [re.compile(p) for p in _SENTENCE_GARBAGE]

_END_PUNCT  = re.compile(r'[.!?।"\')\]]\s*$')
_SENT_SPLIT = re.compile(r'(?<=[.!?।])\s+')

# Stopwords for paragraph relevance check (Bug 5/6)
_STOPWORDS = {
    'that', 'this', 'with', 'from', 'have', 'been', 'they', 'were',
    'their', 'into', 'will', 'more', 'when', 'then', 'than', 'also',
    'over', 'some', 'what', 'said', 'says', 'after', 'before', 'under',
    'about', 'which', 'would', 'could', 'should', 'there', 'these',
    'those', 'other', 'such', 'even', 'many', 'well', 'just', 'only',
    'very', 'much', 'each', 'both', 'same', 'its',
    'అని', 'అయిన', 'ఉన్న', 'కోసం', 'వల్ల', 'మరియు', 'కానీ',
    'అయితే', 'అక్కడ', 'ఇక్కడ', 'ఇది', 'అది', 'వారు', 'అందులో',
}

# Cutoff words that signal a truncated sentence (Bug 7)
_CUTOFF_WORDS = {
    'and', 'or', 'but', 'with', 'in', 'on', 'at', 'to', 'for',
    'the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'have',
    'of', 'by', 'as', 'if', 'its', 'it', 'he', 'she', 'they',
    'మరియు', 'కానీ', 'అయితే', 'లో', 'తో', 'కి', 'అని',
}


# ─────────────────────────────────────────────────────────────
# Core encoding
# ─────────────────────────────────────────────────────────────

def repair_garbled_telugu(text: str) -> str:
    if not text:
        return ""
    if "à°" not in text and "à±" not in text:
        return text
    cp1252_to_byte = {
        '\u20ac': 0x80, '\u201a': 0x82, '\u0192': 0x83, '\u201e': 0x84,
        '\u2026': 0x85, '\u2020': 0x86, '\u2021': 0x87, '\u02c6': 0x88,
        '\u2030': 0x89, '\u0160': 0x8a, '\u2039': 0x8b, '\u0152': 0x8c,
        '\u017d': 0x8e, '\u2018': 0x91, '\u2019': 0x92, '\u201c': 0x93,
        '\u201d': 0x94, '\u2022': 0x95, '\u2013': 0x96, '\u2014': 0x97,
        '\u02dc': 0x98, '\u2122': 0x99, '\u0161': 0x9a, '\u203a': 0x9b,
        '\u0153': 0x9c, '\u017e': 0x9e, '\u0178': 0x9f
    }
    byte_list = []
    for char in text:
        cp = ord(char)
        if char in cp1252_to_byte:
            byte_list.append(cp1252_to_byte[char])
        elif cp <= 0xff:
            byte_list.append(cp)
        else:
            byte_list.append(cp & 0xff)
    try:
        return bytes(byte_list).decode('utf-8')
    except Exception:
        for enc in ('cp1252', 'latin-1'):
            try:
                return text.encode(enc, errors='ignore').decode('utf-8')
            except Exception:
                continue
    return text


def fix_encoding(text: str) -> str:
    if not text:
        return ""
    text = repair_garbled_telugu(text)
    text = _ENCODING_GARBAGE.sub(' ', text)
    try:
        text = unicodedata.normalize('NFC', text)
    except Exception:
        pass
    text = _HTML_ENTITIES.sub(' ', text)
    text = _CSS_JS_FRAGMENT.sub('', text)
    return text


def strip_arrow_and_garbage_chars(text: str) -> str:
    if not text:
        return text
    text = _ARROW_CHARS.sub(' ', text)
    text = _ARROW_SEQUENCES.sub(' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'(?m)^\s*$\n', '', text)
    return text.strip()


# ─────────────────────────────────────────────────────────────
# Bug 2 — Remove summary blocks
# ─────────────────────────────────────────────────────────────

def remove_summary_blocks(text: str) -> str:
    """
    Bug 2: Remove English Summary / AI Summary / Machine Summary / Translation
    Summary section headers AND the bullet content that follows them.
    """
    if not text:
        return text
    block_pats = [
        r'(?im)^(?:english\s+)?summary\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^ai\s+(?:generated\s+)?summary\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^machine\s+summary\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^translation\s+summary\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^automated?\s+summary\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^in\s+brief\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^quick\s+facts?\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^at\s+a\s+glance\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^key\s+takeaways?\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^what\s+you\s+need\s+to\s+know\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
        r'(?im)^tl\s*;\s*dr\s*[:\-]?\s*\n(?:[ \t]*[^\n]+\n)*',
    ]
    for pat in block_pats:
        text = re.sub(pat, '\n', text)
    inline_pats = [
        r'(?i)(?:english\s+)?summary\s*[:\-]\s*[^\n.।]{3,}',
        r'(?i)ai\s+(?:generated\s+)?summary\s*[:\-]?\s*[^\n.।]{3,}',
        r'(?i)machine\s+summary\s*[:\-]?\s*[^\n.।]{3,}',
        r'(?i)translation\s+summary\s*[:\-]?\s*[^\n.।]{3,}',
    ]
    for pat in inline_pats:
        text = re.sub(pat, '', text)
    return text.strip()


# ─────────────────────────────────────────────────────────────
# Existing functions (all preserved)
# ─────────────────────────────────────────────────────────────

def clean_metadata(text: str) -> str:
    if not text:
        return ""
    text = fix_encoding(text)
    for pattern in _COMPILED_META:
        text = pattern.sub("", text)
    for pattern in _JUNK_LINE_PAT:
        text = pattern.sub("", text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def is_garbage_sentence(sentence: str) -> bool:
    s = sentence.strip()
    if not s:
        return True
    if len(s) < 5:
        return True
    if re.match(r'^https?://\S+$', s) or re.match(r'^www\.\S+$', s):
        return True
    return any(p.search(s) for p in _COMPILED_SENTENCE_GARBAGE)


def deduplicate_sentences(text_blocks: list[str]) -> list[str]:
    seen_normalized: set[str] = set()
    clean_paragraphs: list[str] = []
    for block in text_blocks:
        block = fix_encoding(block)
        block = re.sub(r'\s+', ' ', block).strip()
        if not block:
            continue
        sentences = _SENT_SPLIT.split(block)
        kept: list[str] = []
        for sent in sentences:
            s = sent.strip()
            if not s or len(s) < 8:
                continue
            if is_garbage_sentence(s):
                continue
            norm = re.sub(r'[^a-zA-Z0-9\u0C00-\u0C7F]', '', s).lower()
            if len(norm) < 6:
                continue
            if norm not in seen_normalized:
                seen_normalized.add(norm)
                kept.append(s)
        if kept:
            clean_paragraphs.append(" ".join(kept))
    return clean_paragraphs


def ensure_complete_ending(text: str, language: str = "en") -> str:
    if not text:
        return text
    text = text.strip()
    if not text:
        return text
    if _END_PUNCT.search(text):
        return text
    term = "." if language == "en" else "।"
    last_char = text[-1] if text else ""
    if last_char.isalnum() or last_char in (',', ';', ':'):
        terminators = list(re.finditer(r'[.!?।]', text))
        if terminators:
            last_term_pos = terminators[-1].end()
            trailing = text[last_term_pos:].strip()
            if len(trailing) <= 80:
                return text[:last_term_pos].strip()
            return text + term
        return text + term
    return text + term


def build_clean_article(raw_text: str, language: str = "en",
                        min_words: int = 5) -> Optional[str]:
    if not raw_text:
        return None
    text = fix_encoding(raw_text)
    text = clean_metadata(text)
    if not text.strip():
        return None
    blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]
    if not blocks:
        blocks = [b.strip() for b in text.split('\n') if b.strip()]
    clean_blocks = deduplicate_sentences(blocks)
    if not clean_blocks:
        return None
    result = "\n\n".join(clean_blocks)
    result = ensure_complete_ending(result, language)
    if len(result.split()) < min_words:
        return None
    return result


def is_content_sufficient(text: str, min_words: int = 40) -> bool:
    if not text:
        return False
    return len(text.split()) >= min_words


def remove_repeated_paragraphs(text: str) -> str:
    if not text:
        return text
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for p in paras:
        norm = re.sub(r'\s+', ' ', p).lower().strip()
        key  = norm[:120]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return "\n\n".join(unique)


def validate_content_matches_title(content: str, title: str,
                                    min_overlap: int = 1) -> bool:
    if not content or not title:
        return bool(content)
    title_words   = set(re.findall(r'[a-zA-Z\u0C00-\u0C7F]{4,}', title.lower()))
    content_lower = content.lower()
    matches = sum(1 for w in title_words if w in content_lower)
    return matches >= min_overlap


def validate_image_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False
    img_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')
    url_lower = url.lower().split('?')[0]
    if any(url_lower.endswith(ext) for ext in img_extensions):
        return True
    img_cdn_patterns = [
        'images.', 'img.', 'cdn.', 'media.', 'photos.',
        '/image/', '/images/', '/img/', '/photo/', '/photos/',
        'googleusercontent', 'gstatic', 'twimg.com', 'fbcdn.net',
        'cloudfront.net', 'akamaized.net', 'wp-content/uploads',
        'static.', 'assets.',
    ]
    return any(p in url.lower() for p in img_cdn_patterns)


def clean_html_output(html: str) -> str:
    if not html:
        return ""
    html = fix_encoding(html)
    html = re.sub(r'<(p|h1|h2|h3|div|span)[^>]*>\s*</\1>', '', html)
    html = re.sub(r'>[ \t]+<', '><', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


NO_DETAILS_TEXT = {
    "te": ("ఈ వార్తకు సంబంధించి అదనపు వివరాలు ఇప్పుడు అందుబాటులో లేవు. "
           "పూర్తి కథనం కోసం 'బ్రౌజర్‌లో తెరవండి' బటన్‌ను నొక్కండి."),
    "en": ("No further details are available for this article right now. "
           "Tap 'Open in Browser' to read the full source article."),
}


def no_details_message(language: str = "en") -> str:
    return NO_DETAILS_TEXT.get(language, NO_DETAILS_TEXT["en"])


def is_no_details_message(text: str) -> bool:
    return (text or "").strip() in NO_DETAILS_TEXT.values()


def is_duplicate_of_title(body: str, title: str) -> bool:
    b = re.sub(r'\s+', ' ', (body or "").strip().lower())
    t = re.sub(r'\s+', ' ', (title or "").strip().lower())
    if not b or not t:
        return False
    if b == t:
        return True
    return b.rstrip(".!?। ") == t.rstrip(".!?। ")


# ─────────────────────────────────────────────────────────────
# Bug 4 — Remove trailing junk
# ─────────────────────────────────────────────────────────────

def remove_trailing_junk(text: str) -> str:
    """
    Bug 4: Remove orphaned short headlines / navigation labels at the END
    of scraped article text ("Google Maps Tips", "Horoscope", "OTT", etc.).
    """
    if not text:
        return text
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paras) <= 1:
        return text

    removed = True
    while removed and len(paras) > 1:
        removed  = False
        last     = paras[-1]
        wc       = len(last.split())
        no_punct = not re.search(r'[.!?।]', last)
        if no_punct and wc <= 8:
            if _TRAILING_JUNK_RE.match(last.strip()):
                paras.pop(); removed = True; continue
            if wc <= 3 and not re.search(r'[\u0C00-\u0C7F]', last):
                paras.pop(); removed = True; continue
            if re.match(r'^https?://\S+$', last) or re.match(r'^www\.\S+$', last):
                paras.pop(); removed = True; continue

    return '\n\n'.join(paras)


# ─────────────────────────────────────────────────────────────
# Bug 5 / 6 — Filter unrelated paragraphs
# ─────────────────────────────────────────────────────────────

def filter_relevant_paragraphs(text: str, title: str,
                                 min_keep: int = 2) -> str:
    """
    Bug 5/6: Remove short paragraphs whose content has zero keyword
    overlap with the article title.  Long paragraphs (≥20 words) and
    the first (lead) paragraph are always kept.
    """
    if not text or not title:
        return text
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paras) <= min_keep:
        return text

    title_kw = {
        w.lower() for w in re.findall(r'[a-zA-Z\u0C00-\u0C7F]{4,}', title)
        if w.lower() not in _STOPWORDS
    }
    if not title_kw:
        return text

    kept: list[str] = []
    for i, para in enumerate(paras):
        if i == 0:                       # always keep lead
            kept.append(para); continue
        if len(para.split()) >= 20:      # long paras always kept
            kept.append(para); continue
        para_kw = {
            w.lower() for w in re.findall(r'[a-zA-Z\u0C00-\u0C7F]{4,}', para)
        }
        if para_kw & title_kw:
            kept.append(para)
        elif len(kept) < min_keep:       # safety floor
            kept.append(para)

    return '\n\n'.join(kept) if kept else text


# ─────────────────────────────────────────────────────────────
# Bug 7 — Detect truncated articles
# ─────────────────────────────────────────────────────────────

def is_article_complete(text: str) -> bool:
    """Bug 7: Return True when article appears complete (proper ending)."""
    if not text:
        return False
    text = text.strip()
    if len(text.split()) < 20:
        return False
    if not _END_PUNCT.search(text):
        return False
    words = text.rstrip('.!?।"\'() ').split()
    if words:
        lw = words[-1].lower().rstrip('.,;:')
        if lw in _CUTOFF_WORDS:
            return False
    return True


# ─────────────────────────────────────────────────────────────
# Private pipeline helpers
# ─────────────────────────────────────────────────────────────

def _deduplicate_lines(text: str) -> str:
    lines = text.split('\n')
    seen: set[str] = set()
    out:  list[str] = []
    for line in lines:
        norm = re.sub(r'\s+', ' ', line).strip().lower()
        if norm and norm in seen:
            continue
        if norm:
            seen.add(norm)
        out.append(line)
    return '\n'.join(out)


def _remove_broken_words(text: str) -> str:
    paras   = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    cleaned = []
    for p in paras:
        p = re.sub(r'^[a-z]{1,2}\s+', '', p)
        p = re.sub(r'\s+[a-z]{1,2}$', '', p)
        if p.strip():
            cleaned.append(p.strip())
    return '\n\n'.join(cleaned)


def _remove_empty_paragraphs(text: str) -> str:
    good = []
    for p in re.split(r'\n{2,}', text):
        s = p.strip()
        if not s:
            continue
        if re.match(r'^[\s\-_=*•·.,:;|/\\]+$', s):
            continue
        if len(s.split()) < 3 and not re.search(r'[\u0C00-\u0C7F]', s):
            continue
        good.append(s)
    return '\n\n'.join(good)


# ─────────────────────────────────────────────────────────────
# Master pipeline
# ─────────────────────────────────────────────────────────────

def final_clean_pipeline(text: str, language: str = "en",
                          title: str = "") -> str:
    """
    Master cleaning pipeline — call BEFORE rendering or caching.

    Order:
      1  repair_garbled_telugu
      2  strip_arrow_and_garbage_chars
      3  remove_summary_blocks          (Bug 2)
      4  clean_metadata                 (Bugs 1, 12, 13)
      5  remove_repeated_paragraphs     (Bug 16)
      6  _deduplicate_lines             (Bug 16)
      7  _remove_broken_words
      8  remove_trailing_junk           (Bug 4)
      9  filter_relevant_paragraphs     (Bugs 5, 6)  — only when title given
      10 ensure_complete_ending         (Bug 7)
      11 _remove_empty_paragraphs
      12 whitespace normalise
    """
    if not text or not text.strip():
        return text or ""

    text = repair_garbled_telugu(text)
    text = strip_arrow_and_garbage_chars(text)
    text = remove_summary_blocks(text)
    text = clean_metadata(text)
    text = remove_repeated_paragraphs(text)
    text = _deduplicate_lines(text)
    text = _remove_broken_words(text)
    text = remove_trailing_junk(text)
    if title:
        text = filter_relevant_paragraphs(text, title)
    text = ensure_complete_ending(text, language)
    text = _remove_empty_paragraphs(text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
