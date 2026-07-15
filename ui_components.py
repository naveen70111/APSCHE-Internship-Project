"""
ui_components.py  —  Chronicle Intelligence  v9-BUGFIX

REDESIGNED DIRECTLY MATCHING THE PRESCRIBED VISUAL SPECIFICATIONS:
- High-fidelity gradient backgrounds (Teal to Blue) drawn dynamically via Canvas.
- High-fidelity rounded tablet chassis matching the mockup bezel radius.
- Sophisticated vector graphics on left panel (grid matrix, speech bubble, detailed orbit globe, 3D paper, play circle).
- Modern input fields with active placeholder texts and native vector icons.
- Custom interactive canvas-rendered checkbox elements.
- Preservation of all original functional APIs, settings parameters, state flags, and Bugfixes 1-20.
"""

import io
import re
import threading
import webbrowser
import math

import requests
import urllib3
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext

import api_manager
import content_cleaner
import database
import rss_manager
import config


def _dprint(*args, **kwargs):
    if config.DEBUG_LOGGING:
        print(*args, **kwargs)


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FF       = config.FONT_FAMILY
HEADER_H = 65


# ─────────────────────────────────────────────────────────────
# UI string tables
# ─────────────────────────────────────────────────────────────

SECTION_TEXT = {
    "English": {
        "back":           "← Back to Feed",
        "loading":        "Loading…",
        "fetch":          "Fetching latest news…",
        "no_articles":    "No articles found. Check your internet connection.",
        "fetch_error":    "Could not load articles. Tap Refresh to try again.",
        "searching":      "Searching…",
        "key_highlights": "Key Highlights",
        "open_browser":   "Open in Browser  ↗",
        "preparing":      "Preparing article…",
        "read_article":   "Read More  →",
    },
    "Telugu": {
        "back":           "← వెనుకకు",
        "loading":        "లోడ్ అవుతోంది…",
        "fetch":          "తాజా వార్తలను సేకరిస్తోంది…",
        "no_articles":    "వార్తలు కనుగొనబడలేదు. ఇంటర్నెట్ తనిఖీ చేయండి.",
        "fetch_error":    "వార్తలు లోడ్ కాలేదు. రిఫ్రెష్ నొక్కండి.",
        "searching":      "వెతుకుోంది…",
        "key_highlights": "ముఖ్య విషయాలు",
        "open_browser":   "బ్రౌజర్‌లో తెరవండి  ↗",
        "preparing":      "వ్యాసం సిద్ధమవుతోంది…",
        "read_article":   "Read More  →",
    },
}

# Accurate Visual Color Schemes
LIGHT = {
    "bg": "#0D9488",             # Teal
    "gradient_end": "#1E1B4B",   # Royal Indigo/Navy
    "surface": "#FFFFFF",
    "surface2": "#F1F5F9",
    "surface3": "#E2E8F0",
    "card_bg": "#FFFFFF",
    "card_hover": "#F8FAFC",
    "text": "#0F172A",
    "text2": "#334155",
    "subtext": "#64748B",
    "muted": "#94A3B8",
    "accent": "#2563EB",         # Royal Blue Accent
    "accent_hover": "#1D4ED8",
    "accent_light": "#EFF6FF",
    "border": "#E2E8F0",
    "border2": "#CBD5E1",
    "header_bg": "#0F172A",
    "header_fg": "#F1F5F9",
    "sep": "#CBD5E1",
    "btn_back": "#334155",
    "input_bg": "#F8FAFC",
    "success": "#10B981",
    "danger": "#EF4444",
}

DARK = {
    "bg": "#060A16",
    "gradient_end": "#02040A",
    "surface": "#0F172A",
    "surface2": "#1E293B",
    "surface3": "#334155",
    "card_bg": "#0F172A",
    "card_hover": "#1E293B",
    "text": "#F9FAFB",
    "text2": "#D1D5DB",
    "subtext": "#9CA3AF",
    "muted": "#6B7280",
    "accent": "#3B82F6",
    "accent_hover": "#2563EB",
    "accent_light": "#1E3A8A",
    "border": "#1E293B",
    "border2": "#334155",
    "header_bg": "#02040A",
    "header_fg": "#F9FAFB",
    "sep": "#334155",
    "btn_back": "#334155",
    "input_bg": "#1E293B",
    "success": "#10B981",
    "danger": "#EF4444",
}

CATEGORY_COLORS = {
    "general": "#EF4444", "technology": "#2563EB", "business": "#F59E0B",
    "sports": "#10B981", "science": "#8B5CF6", "eenadu": "#06B6D4",
    "sakshi": "#EC4899", "andhrajyothi": "#F97316",
}

_PILL_BG_LIGHT = {
    "general": "#FEE2E2", "technology": "#EFF6FF", "business": "#FFFBEB",
    "sports": "#ECFDF5", "science": "#F5F3FF", "eenadu": "#ECFEFF",
    "sakshi": "#FDF2F8", "andhrajyothi": "#FFF7ED",
}


# ─────────────────────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────────────────────

def _cc_is_dup(body: str, title: str) -> bool:
    fn = getattr(content_cleaner, "is_duplicate_of_title", None)
    if fn:
        return fn(body, title)
    b = re.sub(r"\s+", " ", (body or "").strip().lower()).rstrip(".!?। ")
    t = re.sub(r"\s+", " ", (title or "").strip().lower()).rstrip(".!?। ")
    return b == t


def _cc_strip_arrows(text: str) -> str:
    fn = getattr(content_cleaner, "strip_arrow_and_garbage_chars", None)
    if fn:
        return fn(text)
    return re.sub(r"[\u2190-\u21FF\u25A0-\u25FF\u2794-\u27BF→←↔►▶»«]+",
                  " ", text or "").strip()


def _cc_final_clean(text: str, lang: str = "en", title: str = "") -> str:
    if not text:
        return text or ""
    fn = getattr(content_cleaner, "final_clean_pipeline", None)
    if fn:
        try:
            return fn(text, lang, title=title)
        except TypeError:
            return fn(text, lang)
    text = content_cleaner.clean_metadata(text)
    if hasattr(content_cleaner, "remove_repeated_paragraphs"):
        text = content_cleaner.remove_repeated_paragraphs(text)
    if hasattr(content_cleaner, "ensure_complete_ending"):
        text = content_cleaner.ensure_complete_ending(text, lang)
    return text.strip()


def _bind_hover(w, normal, hover):
    w.bind("<Enter>", lambda _: w.config(bg=hover))
    w.bind("<Leave>", lambda _: w.config(bg=normal))


def _lang_ui(lv: tk.StringVar) -> dict:
    k = lv.get() if lv.get() in SECTION_TEXT else "English"
    return SECTION_TEXT[k]


def _lang_code(lv: tk.StringVar) -> str:
    return config.LANG_MAP.get(lv.get(), "en")


def _key_highlights(text: str, n: int = 5) -> list[str]:
    if not text:
        return []
    text = content_cleaner.clean_metadata(text)
    sents = re.split(r'(?<=[.!?।])\s+', text.strip())
    out:        list[str] = []
    seen_norms: list[str] = []
    for s in sents:
        s = s.strip()
        wc = len(s.split())
        if wc < 8 or wc > 40:
            continue
        if content_cleaner.is_garbage_sentence(s):
            continue
        norm = re.sub(r'[^a-z0-9\u0C00-\u0C7F]', '', s.lower())
        if len(norm) < 10:
            continue
        if norm in seen_norms:
            continue
        if any(norm in ex or ex in norm for ex in seen_norms):
            continue
        seen_norms.append(norm)
        out.append(s)
        if len(out) >= n:
            break
    return out


def _split_paragraphs(text: str, target_wc: int = 80) -> list[str]:
    sentences = re.split(r'(?<=[.!?।])\s+', text.strip())
    paras: list[str] = []
    cur:   list[str] = []
    cw = 0
    for s in sentences:
        cur.append(s)
        cw += len(s.split())
        if cw >= target_wc:
            paras.append(" ".join(cur))
            cur, cw = [], 0
    if cur:
        paras.append(" ".join(cur))
    return [p for p in paras if p.strip()]


# ─────────────────────────────────────────────────────────────
# Dynamic Gradient Canvas Background with Glowing Ripple Vectors
# ─────────────────────────────────────────────────────────────

class GradientBackgroundCanvas(tk.Canvas):
    def __init__(self, parent, colors, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self.colors = colors
        self.bind("<Configure>", self._draw)

    def update_theme(self, colors):
        self.colors = colors
        self._draw()

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        c1 = self.colors["bg"]
        c2 = self.colors["gradient_end"]

        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)

        for i in range(h):
            t = i / max(1, h - 1)
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            col = f"#{r:02x}{g:02x}{b:02x}"
            self.create_line(0, i, w, i, fill=col)

        ripple_col = "#155E75" if self.colors == LIGHT else "#0B1528"
        for rad in [140, 200, 260, 320, 380, 440, 500]:
            self.create_oval(-50 - rad, -50 - rad, -50 + rad, -50 + rad, outline=ripple_col, width=1)

        orb_col_1 = "#1A6B85" if self.colors == LIGHT else "#1E2A4A"
        orb_col_2 = "#144D60" if self.colors == LIGHT else "#0B1528"

        self._draw_ambient_circle(140, 140, 110, orb_col_1)
        self._draw_ambient_circle(w - 140, h // 2 + 100, 130, orb_col_2)
        self._draw_ambient_circle(200, h - 140, 60, orb_col_1)

    def _draw_ambient_circle(self, x, y, r, base_color):
        for scale in range(12, 0, -1):
            alpha_r = int(r * (scale / 12.0))
            self.create_oval(x - alpha_r, y - alpha_r, x + alpha_r, y + alpha_r,
                             fill=base_color, outline="")


# ─────────────────────────────────────────────────────────────
# Custom Rounded Polygon Renderer for Glass Frames and Capsule Pills
# ─────────────────────────────────────────────────────────────

def draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1+r, y1, x1+r, y1,
        x2-r, y1, x2-r, y1,
        x2, y1, x2, y1+r, x2, y1+r,
        x2, y2-r, x2, y2-r,
        x2, y2, x2-r, y2, x2-r, y2,
        x1+r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y2-r,
        x1, y1+r, x1, y1+r,
        x1, y1
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class CapsulePill(tk.Canvas):
    def __init__(self, parent, bg_col, border_col, radius=10, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=parent["bg"], **kwargs)
        self.bg_col = bg_col
        self.border_col = border_col
        self.radius = radius
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 1 and h > 1:
            draw_rounded_rect(self, 1, 1, w-2, h-2, self.radius, fill=self.bg_col, outline=self.border_col, width=1)


class CapsuleButton(tk.Canvas):
    def __init__(self, parent, text, command, bg_color="#2563EB", fg_color="#FFFFFF", hover_bg="#1D4ED8", font=(FF, 9, "bold"), radius=18, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=parent["bg"], cursor="hand2", **kwargs)
        self.text = text
        self.command = command
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_bg = hover_bg
        self.font = font
        self.radius = radius
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", lambda _: self.command())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 1 and h > 1:
            draw_rounded_rect(self, 0, 0, w, h, self.radius, fill=self.bg_color, outline="")
            self.create_text(w // 2, h // 2, text=self.text, fill=self.fg_color, font=self.font)

    def _on_enter(self, _):
        w = self.winfo_width()
        h = self.winfo_height()
        self.delete("all")
        draw_rounded_rect(self, 0, 0, w, h, self.radius, fill=self.hover_bg, outline="")
        self.create_text(w // 2, h // 2, text=self.text, fill=self.fg_color, font=self.font)

    def _on_leave(self, _):
        self._draw()


class DropdownPill(tk.Canvas):
    def __init__(self, parent, icon, label, options, var, callback, bg_color="#FFFFFF", border_col="#E2E8F0", radius=10, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=parent["bg"], cursor="hand2", **kwargs)
        self.icon = icon
        self.label = label
        self.options = options
        self.var = var
        self.callback = callback
        self.bg_color = bg_color
        self.border_col = border_col
        self.radius = radius
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", self._show_menu)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 1 and h > 1:
            draw_rounded_rect(self, 1, 1, w-1, h-1, self.radius, fill=self.bg_color, outline=self.border_col, width=1)
            self.create_text(22, h//2, text=self.icon, font=(FF, 11), fill="#2563EB")
            txt_val = f"{self.label}: {self.var.get()}" if self.var.get() else self.label
            self.create_text(w//2 + 5, h//2, text=txt_val, font=(FF, 9, "bold"), fill="#334155" if self.bg_color == "#FFFFFF" else "#F1F5F9")
            self.create_text(w - 20, h//2, text="˅", font=(FF, 10, "bold"), fill="#2563EB")

    def _show_menu(self, event=None):
        menu = tk.Menu(self, tearoff=0, bg="#FFFFFF", fg="#0F172A", activebackground="#EFF6FF", activeforeground="#2563EB", font=(FF, 10), bd=1, relief="flat")
        for opt in self.options:
            menu.add_command(label=opt, command=lambda o=opt: self._select_opt(o))
        menu.post(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())

    def _select_opt(self, opt):
        self.var.set(opt)
        self._draw()
        self.callback()


class SearchCapsule(tk.Canvas):
    def __init__(self, parent, var, bg_color="#FFFFFF", border_col="#E2E8F0", radius=10, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=parent["bg"], **kwargs)
        self.var = var
        self.bg_color = bg_color
        self.border_col = border_col
        self.radius = radius
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 1 and h > 1:
            draw_rounded_rect(self, 1, 1, w-1, h-1, self.radius, fill=self.bg_color, outline=self.border_col, width=1)
            self.create_text(22, h//2, text="🔍", font=(FF, 10), fill="#64748B")
            
            if not hasattr(self, "entry"):
                self.entry = tk.Entry(self, textvariable=self.var, bg=self.bg_color, fg="#0F172A" if self.bg_color=="#FFFFFF" else "#F8FAFC", insertbackground="#2563EB", bd=0, font=(FF, 10))
                self.create_window(w//2 + 10, h//2, window=self.entry, width=w - 55, height=20)


# ─────────────────────────────────────────────────────────────
# High-Fidelity Custom Vector Illustration Canvas
# ─────────────────────────────────────────────────────────────

class NewsIllustrationCanvas(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, highlightthickness=0, bg="#FFFFFF", **kwargs)
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        # 1. Subtle Radial / Circular background structures
        self.create_oval(-100, h//5, w + 120, h + 150, fill="#F3F8FF", outline="")
        self.create_oval(w//2 - 120, h//2 - 120, w//2 + 120, h//2 + 120, outline="#E8F1FC", width=1)

        # 2. Grid Matrix Dot pattern (Top Right quadrant)
        dot_color = "#E2E8F0"
        grid_start_x, grid_start_y = w - 80, 110
        for row in range(5):
            for col in range(4):
                px = grid_start_x + (col * 10)
                py = grid_start_y + (row * 10)
                self.create_oval(px-1.5, py-1.5, px+1.5, py+1.5, fill=dot_color, outline="")

        # 3. Dynamic Orbit Globe with Coordinate Rings
        globe_cx, globe_cy, globe_r = 145, h//2 + 35, 58
        self.create_oval(globe_cx - globe_r, globe_cy - globe_r, globe_cx + globe_r, globe_cy + globe_r, fill="#4285F4", outline="")
        # Overlay translucent globe grid detailing (latitude/longitude coordinates)
        self.create_oval(globe_cx - globe_r + 8, globe_cy - globe_r + 4, globe_cx + globe_r - 8, globe_cy + globe_r - 4, outline="#E8F1FC", width=1)
        self.create_oval(globe_cx - 24, globe_cy - globe_r, globe_cx + 24, globe_cy + globe_r, outline="#E8F1FC", width=1)
        self.create_line(globe_cx - globe_r, globe_cy, globe_cx + globe_r, globe_cy, fill="#E8F1FC", width=1)
        
        # Outer Orbit path wrapping beautifully
        self.create_oval(globe_cx - globe_r - 18, globe_cy - 16, globe_cx + globe_r + 18, globe_cy + 16, outline="#64B5F6", width=1)
        self.create_oval(globe_cx - 14, globe_cy - globe_r - 18, globe_cx + 14, globe_cy + globe_r + 18, outline="#64B5F6", width=1)
        # Orb Nodes
        self.create_oval(globe_cx - globe_r - 21, globe_cy - 3, globe_cx - globe_r - 15, globe_cy + 3, fill="#4285F4", outline="#FFFFFF", width=1)
        self.create_oval(globe_cx + globe_r + 15, globe_cy - 3, globe_cx + globe_r + 21, globe_cy + 3, fill="#4285F4", outline="#FFFFFF", width=1)

        # 4. Smartphone device positioning
        phone_w, phone_h = 125, 230
        phone_x, phone_y = w//2 + 25, h//2 - 60
        draw_rounded_rect(self, phone_x, phone_y, phone_x + phone_w, phone_y + phone_h, 20, fill="#1A1D20", outline="")
        draw_rounded_rect(self, phone_x + 4, phone_y + 4, phone_x + phone_w - 4, phone_y + phone_h - 4, 18, fill="#FFFFFF", outline="")
        
        # Camera notch layout
        self.create_oval(phone_x + phone_w//2 - 18, phone_y + 10, phone_x + phone_w//2 + 18, phone_y + 16, fill="#1A1D20", outline="")
        
        # Phone Screen Content: App Brand Capsule
        draw_rounded_rect(self, phone_x + 10, phone_y + 24, phone_x + phone_w - 10, phone_y + 46, 5, fill="#2B66E2", outline="")
        self.create_text(phone_x + phone_w//2, phone_y + 35, text="NEWS", fill="#FFFFFF", font=(FF, 8, "bold"))
        
        # Phone Screen Content: Picture layout
        draw_rounded_rect(self, phone_x + 10, phone_y + 54, phone_x + phone_w - 10, phone_y + 130, 8, fill="#E6F0FA", outline="")
        # Minimal landscape vector inside screen image
        self.create_polygon([phone_x + 10, phone_y + 130, phone_x + 40, phone_y + 90, phone_x + 72, phone_y + 130], fill="#BFDBFE", outline="")
        self.create_polygon([phone_x + 46, phone_y + 130, phone_x + 82, phone_y + 82, phone_x + phone_w - 10, phone_y + 130], fill="#93C5FD", outline="")
        self.create_oval(phone_x + phone_w - 28, phone_y + 68, phone_x + phone_w - 18, phone_y + 78, fill="#FDBA74", outline="")
        
        # Phone Screen Content: News rows placeholders
        offsets = [140, 148, 156, 164, 172, 180, 188, 196, 204]
        for idx, dy in enumerate(offsets):
            col = "#E2E8F0" if idx % 3 != 0 else "#CBD5E1"
            w_line = phone_w - 20 if idx % 4 != 0 else (phone_w - 20) * 0.6
            self.create_line(phone_x + 10, phone_y + dy, phone_x + 10 + w_line, phone_y + dy, fill=col, width=2.5)

        # 5. Rounded Physical Newspaper (Overlaying base of the smartphone)
        paper_x, paper_y = 75, h - 90
        # Layer effects
        draw_rounded_rect(self, paper_x - 10, paper_y - 5, paper_x + 120, paper_y + 50, 6, fill="#A4B3C6", outline="")
        draw_rounded_rect(self, paper_x, paper_y, paper_x + 130, paper_y + 55, 6, fill="#FFFFFF", outline="")
        # Brand title
        self.create_text(paper_x + 42, paper_y + 15, text="NEWS", font=(FF, 13, "bold"), fill="#1F2937")
        self.create_rectangle(paper_x + 88, paper_y + 8, paper_x + 122, paper_y + 32, fill="#E1EFFE", outline="")
        self.create_line(paper_x + 8, paper_y + 36, paper_x + 122, paper_y + 36, fill="#64748B", width=1.5)
        self.create_line(paper_x + 8, paper_y + 42, paper_x + 122, paper_y + 42, fill="#64748B", width=1.5)
        self.create_line(paper_x + 8, paper_y + 48, paper_x + 75, paper_y + 48, fill="#64748B", width=1.5)

        # 6. Dynamic Chat Bubble (Upper Left)
        bubble_x, bubble_y = 80, h//2 - 110
        draw_rounded_rect(self, bubble_x, bubble_y, bubble_x + 55, bubble_y + 38, 10, fill="#3B82F6", outline="")
        self.create_polygon([bubble_x + 15, bubble_y + 36, bubble_x + 20, bubble_y + 45, bubble_x + 28, bubble_y + 36], fill="#3B82F6", outline="")
        for idx, offset_x in enumerate([14, 27, 40]):
            self.create_oval(bubble_x + offset_x - 2.5, bubble_y + 17, bubble_x + offset_x + 2.5, bubble_y + 22, fill="#FFFFFF", outline="")

        # 7. Media Play Button (Right)
        play_x, play_y, play_r = w - 75, h//2 - 25, 20
        # Beautiful play circle with circular blue styling
        self.create_oval(play_x - play_r, play_y - play_r, play_x + play_r, play_y + play_r, fill="#3B82F6", outline="")
        self.create_polygon([play_x - 5, play_y - 8, play_x + 8, play_y, play_x - 5, play_y + 8], fill="#FFFFFF", outline="")


# ─────────────────────────────────────────────────────────────
# Modern Canvas-Rendered Input Capsule with Placeholder and Icon Support
# ─────────────────────────────────────────────────────────────

class ModernInputCapsule(tk.Canvas):
    def __init__(self, parent, icon_char, placeholder, is_password=False, **kwargs):
        super().__init__(parent, highlightthickness=0, bg="#1E52C1", **kwargs)
        self.placeholder = placeholder
        self.is_password = is_password
        self.icon_char = icon_char
        self.is_placeholder_active = True
        
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        
        # Draw high-fidelity white capsule container background
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, 10, fill="#FFFFFF", outline="")
        
        # Render the custom vector outline-style icon
        self.create_text(26, h // 2, text=self.icon_char, font=(FF, 12), fill="#2563EB")
        
        # Instantiate Entry safely inside the vector bounds
        if not hasattr(self, "entry"):
            self.entry = tk.Entry(self, font=(FF, 10), bg="#FFFFFF", fg="#94A3B8", bd=0, insertbackground="#2563EB")
            self.entry.insert(0, self.placeholder)
            
            self.entry.bind("<FocusIn>", self._on_focus_in)
            self.entry.bind("<FocusOut>", self._on_focus_out)
            
            # Position the entry vertically centered with appropriate offsets
            self.create_window(w // 2 + 15, h // 2, window=self.entry, width=w - 60, height=24)

    def _on_focus_in(self, event):
        if self.is_placeholder_active:
            self.entry.delete(0, tk.END)
            self.entry.config(fg="#1E293B")
            if self.is_password:
                self.entry.config(show="•")
            self.is_placeholder_active = False

    def _on_focus_out(self, event):
        val = self.entry.get().strip()
        if not val:
            self.entry.config(fg="#94A3B8")
            if self.is_password:
                self.entry.config(show="")
            self.entry.insert(0, self.placeholder)
            self.is_placeholder_active = True

    def get_value(self):
        if self.is_placeholder_active:
            return ""
        return self.entry.get().strip()


# ─────────────────────────────────────────────────────────────
# Modern Canvas-Rendered Checkbox Widget
# ─────────────────────────────────────────────────────────────

class ModernCheckbox(tk.Canvas):
    def __init__(self, parent, text, command=None, **kwargs):
        super().__init__(parent, highlightthickness=0, bg="#1E52C1", cursor="hand2", **kwargs)
        self.text = text
        self.command = command
        self.is_checked = False
        
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", self._on_toggle)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        box_size = 14
        box_y = (h - box_size) // 2
        
        # Draw clean square checkbox
        if self.is_checked:
            draw_rounded_rect(self, 0, box_y, box_size, box_y + box_size, 3, fill="#3B82F6", outline="#3B82F6")
            self.create_text(box_size // 2, box_y + (box_size // 2) + 1, text="✓", font=(FF, 9, "bold"), fill="#FFFFFF")
        else:
            draw_rounded_rect(self, 0, box_y, box_size, box_y + box_size, 3, fill="#FFFFFF", outline="#CBD5E1")
            
        # Draw accompanying checkbox label
        self.create_text(box_size + 10, h // 2 + 1, text=self.text, font=(FF, 9), fill="#E0E7FF", anchor="w")

    def _on_toggle(self, event):
        self.is_checked = not self.is_checked
        self._draw()
        if self.command:
            self.command(self.is_checked)


# ─────────────────────────────────────────────────────────────
# Login Frame (Fully Redesigned Tablet Split Screen)
# ─────────────────────────────────────────────────────────────

class LoginFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#080E1C")
        self.controller = controller
        self._build()

    def _build(self):
        # 1. Base Deep Space Canvas Background
        self.bg_canvas = GradientBackgroundCanvas(self, colors=DARK)
        self.bg_canvas.pack(fill="both", expand=True)

        # 2. Main Tablet Container Card Frame (Rounded Mockup Bezel)
        self.container = tk.Canvas(self, highlightthickness=0, bg="#080E1C")
        self.container.place(relx=0.5, rely=0.5, anchor="center", width=1020, height=640)
        self.container.bind("<Configure>", self._draw_bezel)

    def _draw_bezel(self, event=None):
        self.container.delete("all")
        w = self.container.winfo_width()
        h = self.container.winfo_height()
        if w <= 1 or h <= 1:
            return

        # Draw Tablet/Window mockup heavily rounded black border bezel (Radius 40px)
        draw_rounded_rect(self.container, 0, 0, w, h, 40, fill="#050811", outline="")
        
        # Draw main workspace surface frame (clipped inside chassis bezel)
        draw_rounded_rect(self.container, 10, 10, w - 10, h - 10, 32, fill="#FFFFFF", outline="")
        
        # Instantiate actual sub-panels overlaying the rounded chassis structure
        if not hasattr(self, "left_panel"):
            self.left_panel = tk.Frame(self.container, bg="#FFFFFF")
            self.container.create_window(10 + 245, h // 2, window=self.left_panel, width=490, height=h - 20)
            self.illustration = NewsIllustrationCanvas(self.left_panel)
            self.illustration.pack(fill="both", expand=True)
            
        if not hasattr(self, "right_panel"):
            self.right_panel = tk.Frame(self.container, bg="#1E52C1")
            self.container.create_window(w - 10 - 255, h // 2, window=self.right_panel, width=510, height=h - 20)
            self._build_login_form()

    def _build_login_form(self):
        inner = tk.Frame(self.right_panel, bg="#1E52C1")
        inner.pack(fill="both", expand=True, padx=48, pady=40)

        # Row 1: Header Welcome Statement
        tk.Label(inner, text="Welcome Back!", font=(FF, 26, "bold"),
                 fg="#FFFFFF", bg="#1E52C1").pack(anchor="w", pady=(24, 2))
        
        # Subtitle Row linking direct registration routing
        sub_row = tk.Frame(inner, bg="#1E52C1")
        sub_row.pack(anchor="w", pady=(0, 32))
        
        tk.Label(sub_row, text="Don't have an account yet?", font=(FF, 9),
                 fg="#E0E7FF", bg="#1E52C1").pack(side="left")
        
        reg_link = tk.Label(sub_row, text=" SignUp", font=(FF, 9, "bold", "underline"),
                            fg="#FFFFFF", bg="#1E52C1", cursor="hand2")
        reg_link.pack(side="left", padx=4)
        reg_link.bind("<Button-1>", lambda _: self.controller.show_frame("RegisterFrame"))

        # Row 2: Username Label & High-Fidelity Input Box Capsule
        tk.Label(inner, text="Username", font=(FF, 9, "bold"),
                 fg="#E0E7FF", bg="#1E52C1").pack(anchor="w", pady=(0, 6))
        
        self.username_capsule = ModernInputCapsule(inner, icon_char="👤", placeholder="Enter your username", height=40)
        self.username_capsule.pack(fill="x", pady=(0, 18))

        # Row 3: Password Label & High-Fidelity Input Box Capsule
        tk.Label(inner, text="Password", font=(FF, 9, "bold"),
                 fg="#E0E7FF", bg="#1E52C1").pack(anchor="w", pady=(0, 6))
        
        self.password_capsule = ModernInputCapsule(inner, icon_char="🔒", placeholder="Enter your password", is_password=True, height=40)
        self.password_capsule.pack(fill="x", pady=(0, 18))

        # Row 4: Custom Checkbox & Forgot Password Action Label
        opt_row = tk.Frame(inner, bg="#1E52C1")
        opt_row.pack(fill="x", pady=(2, 32))

        self.keep_logged_checkbox = ModernCheckbox(opt_row, text="Keep me logged in", width=150, height=20)
        self.keep_logged_checkbox.pack(side="left")

        tk.Label(opt_row, text="Forgot Password?", font=(FF, 9, "underline"),
                 fg="#E0E7FF", bg="#1E52C1", cursor="hand2").pack(side="right")

        # Row 5: Submit Action Capsule Button
        self.btn_submit = CapsuleButton(inner, text="Login", command=self._login,
                                         bg_color="#3B82F6", hover_bg="#2563EB", radius=10, height=44)
        self.btn_submit.pack(fill="x")

    def _login(self):
        u = self.username_capsule.get_value()
        p = self.password_capsule.get_value()
        if database.authenticate_user(u, p):
            self.controller.session.login_session(u)
            self.controller.launch_dashboard()
        else:
            messagebox.showerror("Sign In Failed", "Invalid username or password.")


# ─────────────────────────────────────────────────────────────
# Register Frame (Fully Redesigned Tablet Split Screen Matching Login)
# ─────────────────────────────────────────────────────────────

class RegisterFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#080E1C")
        self.controller = controller
        self._build()

    def _build(self):
        self.bg_canvas = GradientBackgroundCanvas(self, colors=DARK)
        self.bg_canvas.pack(fill="both", expand=True)

        self.container = tk.Canvas(self, highlightthickness=0, bg="#080E1C")
        self.container.place(relx=0.5, rely=0.5, anchor="center", width=1020, height=640)
        self.container.bind("<Configure>", self._draw_bezel)

    def _draw_bezel(self, event=None):
        self.container.delete("all")
        w = self.container.winfo_width()
        h = self.container.winfo_height()
        if w <= 1 or h <= 1:
            return

        draw_rounded_rect(self.container, 0, 0, w, h, 40, fill="#050811", outline="")
        draw_rounded_rect(self.container, 10, 10, w - 10, h - 10, 32, fill="#FFFFFF", outline="")
        
        if not hasattr(self, "left_panel"):
            self.left_panel = tk.Frame(self.container, bg="#FFFFFF")
            self.container.create_window(10 + 245, h // 2, window=self.left_panel, width=490, height=h - 20)
            self.illustration = NewsIllustrationCanvas(self.left_panel)
            self.illustration.pack(fill="both", expand=True)
            
        if not hasattr(self, "right_panel"):
            self.right_panel = tk.Frame(self.container, bg="#1E52C1")
            self.container.create_window(w - 10 - 255, h // 2, window=self.right_panel, width=510, height=h - 20)
            self._build_register_form()

    def _build_register_form(self):
        inner = tk.Frame(self.right_panel, bg="#1E52C1")
        inner.pack(fill="both", expand=True, padx=48, pady=40)

        tk.Label(inner, text="Create Account!", font=(FF, 26, "bold"),
                 fg="#FFFFFF", bg="#1E52C1").pack(anchor="w", pady=(24, 2))
        
        sub_row = tk.Frame(inner, bg="#1E52C1")
        sub_row.pack(anchor="w", pady=(0, 32))
        
        tk.Label(sub_row, text="Already have an account?", font=(FF, 9),
                 fg="#E0E7FF", bg="#1E52C1").pack(side="left")
        
        login_link = tk.Label(sub_row, text=" SignIn", font=(FF, 9, "bold", "underline"),
                              fg="#FFFFFF", bg="#1E52C1", cursor="hand2")
        login_link.pack(side="left", padx=4)
        login_link.bind("<Button-1>", lambda _: self.controller.show_frame("LoginFrame"))

        tk.Label(inner, text="Choose Username", font=(FF, 9, "bold"),
                 fg="#E0E7FF", bg="#1E52C1").pack(anchor="w", pady=(0, 6))
        
        self.username_capsule = ModernInputCapsule(inner, icon_char="👤", placeholder="Enter your username", height=40)
        self.username_capsule.pack(fill="x", pady=(0, 18))

        tk.Label(inner, text="Choose Password", font=(FF, 9, "bold"),
                 fg="#E0E7FF", bg="#1E52C1").pack(anchor="w", pady=(0, 6))
        
        self.password_capsule = ModernInputCapsule(inner, icon_char="🔒", placeholder="Enter your password", is_password=True, height=40)
        self.password_capsule.pack(fill="x", pady=(0, 32))

        self.btn_submit = CapsuleButton(inner, text="Register", command=self._register,
                                         bg_color="#3B82F6", hover_bg="#2563EB", radius=10, height=44)
        self.btn_submit.pack(fill="x")

    def _register(self):
        u = self.username_capsule.get_value()
        p = self.password_capsule.get_value()
        res = database.register_user(u, p)
        if res == "success":
            messagebox.showinfo("Account Created", "Account created successfully. Please sign in.")
            self.controller.show_frame("LoginFrame")
        elif res == "exists":
            messagebox.showerror("Registration Failed", "Username already taken.")
        else:
            messagebox.showerror("Registration Failed", "Enter a valid username and password.")


# ─────────────────────────────────────────────────────────────
# Dashboard Frame (Fully Redesigned Glassmorphic Workspace)
# ─────────────────────────────────────────────────────────────

class DashboardFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller     = controller
        self.all_articles:   list            = []
        self.reader_frame:   tk.Frame | None = None
        self._fetch_error:   bool            = False
        self._card_img_refs: list            = []

        prefs = database.get_user_preferences(controller.session.current_user)
        self.is_dark = prefs.get("dark_mode", False)
        self.T       = DARK if self.is_dark else LIGHT
        self.config(bg=self.T["bg"])

        self._build_ui()
        self._restore_prefs(prefs)
        self._async_fetch()

    def _setup_styles(self):
        T     = self.T
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("CI.TCombobox",
                        fieldbackground=T["surface"], background=T["surface"],
                        foreground=T["text"], arrowcolor=T["accent"],
                        bordercolor=T["surface"], lightcolor=T["surface"],
                        darkcolor=T["surface"], relief="flat", padding=4)
        style.map("CI.TCombobox",
                  fieldbackground=[("readonly", T["surface"])],
                  selectbackground=[("readonly", T["surface"])],
                  selectforeground=[("readonly", T["text"])])
        style.configure("CI.Vertical.TScrollbar",
                        troughcolor=T["surface"], background=T["border2"],
                        arrowcolor=T["subtext"], bordercolor=T["surface"],
                        relief="flat")

    def _build_ui(self):
        self._setup_styles()

        self.bg_canvas = GradientBackgroundCanvas(self, colors=self.T)
        self.bg_canvas.pack(fill="both", expand=True)

        self._build_header(self.T)

        self.bg_canvas.bind("<Configure>", self._on_resize_canvas)

        self.workspace = tk.Frame(self, bg=self.T["surface"], highlightthickness=0)
        self.workspace.place(relx=0.5, rely=0.55, anchor="center", width=1140, height=630)

        self._build_toolbar(self.T)
        self._build_feed(self.T)

    def _on_resize_canvas(self, event=None):
        self.bg_canvas._draw()
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        draw_rounded_rect(self.bg_canvas, 30, 105, w-30, h-30, 16, fill=self.T["surface"], outline="")

    def _build_header(self, T):
        self.header = tk.Frame(self, bg=T["bg"])
        self.header.place(relx=0.5, rely=0.06, anchor="center", width=1140, height=HEADER_H)

        left = tk.Frame(self.header, bg=T["bg"])
        left.pack(side="left", fill="y")

        menu_pill = CapsulePill(left, bg_col="#2563EB", border_col="#2563EB", radius=8, width=42, height=42)
        menu_pill.pack(side="left", pady=10)
        menu_pill.pack_propagate(False)
        menu_btn = tk.Button(menu_pill, text=" ☰ ", font=(FF, 12, "bold"),
                             bg="#2563EB", fg="#FFFFFF", bd=0, cursor="hand2", relief="flat")
        menu_btn.pack(fill="both", expand=True)
        _bind_hover(menu_btn, "#2563EB", "#1D4ED8")

        right = tk.Frame(self.header, bg=T["bg"])
        right.pack(side="right", fill="y")

        so_pill = CapsulePill(right, bg_col=T["surface3"] if T==LIGHT else "#1E293B", border_col=T["border"], radius=10, width=44, height=44)
        so_pill.pack(side="right", pady=10, padx=(6, 0))
        so_pill.pack_propagate(False)
        so_btn = tk.Button(so_pill, text="➔", font=(FF, 11, "bold"),
                           bg=T["surface3"] if T==LIGHT else "#1E293B", fg=T["text2"], bd=0,
                           cursor="hand2", relief="flat", command=self._logout)
        so_btn.pack(fill="both", expand=True)

        prof_pill = CapsulePill(right, bg_col=T["surface3"] if T==LIGHT else "#1E293B", border_col=T["border"], radius=10, width=44, height=44)
        prof_pill.pack(side="right", pady=10, padx=4)
        prof_pill.pack_propagate(False)
        profile_btn = tk.Button(prof_pill, text="👤", font=(FF, 11),
                                bg=T["surface3"] if T==LIGHT else "#1E293B", fg="#2563EB" if T==LIGHT else "#93C5FD", bd=0,
                                cursor="hand2", relief="flat")
        profile_btn.pack(fill="both", expand=True)

        theme_pill = CapsulePill(right, bg_col=T["surface3"] if T==LIGHT else "#1E293B", border_col=T["border"], radius=10, width=72, height=44)
        theme_pill.pack(side="right", pady=10, padx=4)
        theme_pill.pack_propagate(False)
        theme_icon = "🌙" if self.is_dark else "☀️"
        self.theme_btn = tk.Button(
            theme_pill, text=theme_icon + "  ⚬", font=(FF, 10, "bold"),
            bg=T["surface3"] if T==LIGHT else "#1E293B", fg=T["header_fg"], bd=0,
            cursor="hand2", relief="flat", command=self._toggle_theme)
            
        if self.is_dark:
            self.theme_btn.config(text="⚬  🌙")
        self.theme_btn.pack(fill="both", expand=True)

    def _build_toolbar(self, T):
        bar = tk.Frame(self.workspace, bg=T["surface"])
        bar.pack(side="top", fill="x", padx=18, pady=(18, 8))

        self.cat_var = tk.StringVar(value="General")
        cat_pill = DropdownPill(bar, icon="㗊", label="Category", options=list(config.CATEGORY_MAP.keys()), 
                                var=self.cat_var, callback=self._on_cat, 
                                bg_color=T["surface"], border_col=T["border"], radius=10, width=155, height=38)
        cat_pill.pack(side="left", padx=(0, 10))

        self.lang_var = tk.StringVar(value="English")
        lang_pill = DropdownPill(bar, icon="🌐", label="Language", options=list(config.LANG_MAP.keys()),
                                 var=self.lang_var, callback=self._on_lang,
                                 bg_color=T["surface"], border_col=T["border"], radius=10, width=145, height=38)
        lang_pill.pack(side="left", padx=(0, 14))

        self.search_var = tk.StringVar()
        search_pill = SearchCapsule(bar, var=self.search_var, bg_color=T["surface2"], border_col=T["border"], radius=10, width=285, height=38)
        search_pill.pack(side="left", padx=(0, 6))

        s_btn = CapsuleButton(bar, text="Search", command=self._search,
                              bg_color="#2563EB", hover_bg="#1D4ED8", radius=10, width=90, height=38)
        s_btn.pack(side="left")

        r_btn = CapsuleButton(bar, text="↻ Refresh", command=self._on_refresh,
                              bg_color=T["surface"], fg_color=T["accent"], hover_bg=T["surface2"], radius=10, width=105, height=38)
        r_btn.pack(side="right")

        self.loading_lbl = tk.Label(bar, text="", font=(FF, 9, "italic"),
                                    fg=T["accent"], bg=T["surface"])
        self.loading_lbl.pack(side="right", padx=10)

    def _build_feed(self, T):
        self.feed_outer = tk.Frame(self.workspace, bg=T["surface"])
        self.feed_outer.pack(side="bottom", fill="both", expand=True,
                             padx=2, pady=(4, 12))
        self.canvas = tk.Canvas(self.feed_outer, bg=T["surface"], highlightthickness=0)
        
        self.sb = ttk.Scrollbar(self.feed_outer, orient="vertical",
                                command=self.canvas.yview,
                                style="CI.Vertical.TScrollbar")
        self.sb.pack(side="right", fill="y")
        
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.scroll_frame = tk.Frame(self.canvas, bg=T["surface"])
        self.scroll_frame.bind(
            "<Configure>",
            lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.scroll_frame,
                                               anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _restore_prefs(self, prefs):
        self.cat_var.set(prefs.get("category", "General"))
        self.lang_var.set(prefs.get("language", "English"))

    def _on_cat(self, *_):
        database.save_user_preference(
            self.controller.session.current_user, "category", self.cat_var.get())
        self._async_fetch()

    def _on_lang(self, *_):
        database.save_user_preference(
            self.controller.session.current_user, "language", self.lang_var.get())
        self._async_fetch()

    def _on_refresh(self):
        try:
            api_manager.invalidate_cache(self.cat_var.get(), self.lang_var.get())
        except Exception:
            pass
        self._async_fetch()

    def _logout(self):
        self.controller.session.logout_session()
        self.controller.show_frame("LoginFrame")

    def _async_fetch(self):
        self.loading_lbl.config(text=_lang_ui(self.lang_var)["fetch"])
        self._fetch_error = False
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            raw = api_manager.sync_latest_news(
                self.cat_var.get(), self.lang_var.get())
        except Exception:
            import traceback
            traceback.print_exc()
            raw = []
            self._fetch_error = True
        self.all_articles = raw
        self.after(0, lambda: self._render_feed(raw))

    def _render_feed(self, articles):
        self._card_img_refs.clear()
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.loading_lbl.config(text="")
        T  = self.T
        ui = _lang_ui(self.lang_var)
        if not articles:
            msg = ui["fetch_error"] if self._fetch_error else ui["no_articles"]
            empty = tk.Frame(self.scroll_frame, bg=T["surface"])
            empty.pack(fill="both", expand=True, pady=120)
            tk.Label(empty, text="📭", font=(FF, 36), fg=T["muted"], bg=T["surface"]).pack()
            tk.Label(empty, text=msg, font=(FF, 11), fg=T["subtext"], bg=T["surface"],
                     wraplength=500, justify="center").pack(pady=(12, 0))
            return
        for art in articles[:30]:
            self._render_card(art)

    def _render_card(self, article: dict):
        T       = self.T
        ui      = _lang_ui(self.lang_var)
        cat     = article.get("category", "general").lower()
        cat_col = CATEGORY_COLORS.get(cat, T["accent"])
        pill_bg = (_PILL_BG_LIGHT.get(cat, T["accent_light"])
                   if not self.is_dark else T["surface2"])
        img_url = article.get("image_url", "")
        has_img = bool(img_url and content_cleaner.validate_image_url(img_url))

        card = tk.Frame(self.scroll_frame, bg=T["card_bg"], bd=0)
        card.pack(fill="x", padx=0, pady=6)

        divider = tk.Frame(self.scroll_frame, bg=T["border"], height=1)
        divider.pack(fill="x", padx=0, pady=1)

        if has_img:
            img_container = tk.Frame(card, bg=T["surface2"], width=210, height=140)
            img_container.pack(side="left", padx=(0, 15), pady=10)
            img_container.pack_propagate(False)
            img_lbl = tk.Label(img_container, bg=T["surface2"], cursor="hand2")
            img_lbl.pack(fill="both", expand=True)
            img_lbl.bind("<Button-1>", lambda _, a=article: self._open_reader(a))
            threading.Thread(target=self._load_card_image,
                             args=(img_url, img_lbl), daemon=True).start()

        btn_wrap = tk.Frame(card, bg=T["card_bg"])
        btn_wrap.pack(side="right", padx=(0, 0), pady=10)
        btn = CapsuleButton(btn_wrap, text="Read More  ➔",
                             command=lambda a=article: self._open_reader(a),
                             bg_color="#2563EB", hover_bg="#1D4ED8", radius=16, width=125, height=38)
        btn.pack()

        content = tk.Frame(card, bg=T["card_bg"])
        content.pack(side="left", fill="both", expand=True, padx=(5, 15), pady=10)

        pill_row = tk.Frame(content, bg=T["card_bg"])
        pill_row.pack(anchor="w", pady=(0, 6))
        
        tag_canvas = CapsulePill(pill_row, bg_col=pill_bg, border_col=pill_bg, radius=4, width=100, height=22)
        tag_canvas.pack(side="left")
        tag_canvas.pack_propagate(False)
        tk.Label(tag_canvas, text=cat.upper(), font=(FF, 8, "bold"),
                 fg=cat_col, bg=pill_bg).pack(fill="both", expand=True)

        title = content_cleaner.repair_garbled_telugu(
            article.get("title", "").strip())
        title = _cc_strip_arrows(title)
        wrap_title = 660 if has_img else 860
        title_lbl  = tk.Label(content, text=title, font=(FF, 13, "bold"),
                               fg=T["text"], bg=T["card_bg"],
                               wraplength=wrap_title, justify="left",
                               cursor="hand2", anchor="w")
        title_lbl.pack(anchor="w", pady=(0, 6))
        title_lbl.bind("<Button-1>", lambda _, a=article: self._open_reader(a))

        desc = content_cleaner.repair_garbled_telugu(
            article.get("description", "").strip())
        if desc and not _cc_is_dup(desc, title):
            if len(desc) > 170:
                desc = desc[:170].rsplit(" ", 1)[0] + "…"
            wrap_desc = 660 if has_img else 860
            tk.Label(content, text=desc, font=(FF, 9), fg=T["text2"],
                     bg=T["card_bg"], wraplength=wrap_desc,
                     justify="left").pack(anchor="w", pady=(0, 8))

        meta_row = tk.Frame(content, bg=T["card_bg"])
        meta_row.pack(fill="x", pady=(2, 0))

        pub_at = article.get("published_at", "")
        pub_short = pub_at[:10] if pub_at else "2026-07-14"
        tk.Label(meta_row, text=f" 📅  {pub_short} ", font=(FF, 9),
                 fg=T["subtext"], bg=T["card_bg"]).pack(side="left")

        def _on_enter(_):
            title_lbl.config(fg="#2563EB")

        def _on_leave(_):
            title_lbl.config(fg=T["text"])

        for w in (card, content, title_lbl, pill_row):
            w.bind("<Enter>", _on_enter)
            w.bind("<Leave>", _on_leave)

    def _load_card_image(self, url: str, label: tk.Label):
        try:
            from PIL import Image, ImageTk
            r = requests.get(url, timeout=6, verify=False)
            if r.status_code != 200:
                return
            img = Image.open(io.BytesIO(r.content))
            
            mask = Image.new('L', (210, 140), 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([(0, 0), (210, 140)], radius=8, fill=255)
            
            img = img.resize((210, 140), Image.Resampling.LANCZOS)
            img.putalpha(mask)

            def _apply():
                try:
                    photo = ImageTk.PhotoImage(img)
                    label.config(image=photo, bg=label.master["bg"])
                    self._card_img_refs.append(photo)
                except Exception:
                    pass

            self.after(0, _apply)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # Gemini system prompts (Bug 9: single-language enforcement)
    # ─────────────────────────────────────────────────────────

    _SYSTEM_EN = (
        "You are a senior news journalist writing for a premium English newspaper.\n\n"
        "LANGUAGE RULE: Output MUST be 100% in English. If source is in Telugu or "
        "any other language, translate it fully. NEVER output Telugu script.\n\n"
        "ANTI-HALLUCINATION: Use ONLY facts from the source. No invented quotes, "
        "names, statistics, or dates.\n\n"
        "RULES:\n"
        "1. At least 350 words. End at a complete sentence.\n"
        "2. Strong opening paragraph, detailed body, clear closing.\n"
        "3. Remove: dates, bylines, author names, publisher names, ads, "
        "social links, navigation, copyright, 'Read More', arrow symbols.\n"
        "4. Third person. No 'click here', 'subscribe', 'follow us'.\n"
        "5. Article body ONLY. No headline. No preamble. Start with paragraph 1.\n"
        "6. Final sentence MUST end with a period."
    )

    _SYSTEM_TE = (
        "మీరు ఒక ప్రొఫెషనల్ తెలుగు న్యూస్ ఎడిటర్.\n\n"
        "భాష నియమం: మీ జవాబు పూర్తిగా తెలుగులో మాత్రమే ఉండాలి. "
        "ఒక్క ఆంగ్ల వాక్యం కూడా రాయకండి. పేర్లు మరియు స్థలాలు "
        "తెలుగులో లిప్యంతరీకరణ చేయండి.\n\n"
        "నియమాలు:\n"
        "1. 100-120 పదాలు మాత్రమే. ఈ పరిమితి దాటకండి.\n"
        "2. 2-3 స్పష్టమైన పేరాగ్రాఫ్లు ఇవ్వండి.\n"
        "3. తేదీలు, రచయిత పేర్లు, 'Read More', ప్రకటనలు అన్నీ తీసివేయండి.\n"
        "4. పూర్తి వాక్యంతో ముగించండి.\n"
        "5. కేవలం వ్యాసం మాత్రమే. శీగ్రీక వద్దు."
    )

    def _call_gemini(self, user_prompt: str, lang: str) -> str:
        from config import GEMINI_API_KEYS, AI_TEMPERATURE
        if not GEMINI_API_KEYS:
            return ""
        key        = GEMINI_API_KEYS[0]
        models     = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
        sys_prompt = self._SYSTEM_TE if lang == "te" else self._SYSTEM_EN
        max_tokens = 6000 if lang == "te" else 2500
        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature":     AI_TEMPERATURE,
                "maxOutputTokens": max_tokens,
                "topP": 0.92, "topK": 40,
            },
        }
        for model in models:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key}")
            try:
                resp = requests.post(url, json=payload, timeout=90, verify=False)
                _dprint(f"[GEMINI] {model} status={resp.status_code}")
                if resp.status_code == 200:
                    data       = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        continue
                    raw = parts[0].get("text", "").strip()
                    if not raw:
                        continue
                    cleaned = _cc_final_clean(raw, lang)
                    wc      = len(cleaned.split())
                    min_wc  = 80 if lang == "te" else 280
                    if wc >= min_wc:
                        return cleaned
                    _dprint(f"[GEMINI] {model} too short ({wc}), retrying…")
                    retry_prompt = (
                        f"{user_prompt}\n\n"
                        f"IMPORTANT: Write at least "
                        f"{'100-120' if lang == 'te' else '350'} words. "
                        f"Complete every sentence.")
                    resp2 = requests.post(
                        url,
                        json={**payload,
                              "contents": [{"parts": [{"text": retry_prompt}]}]},
                        timeout=90, verify=False)
                    if resp2.status_code == 200:
                        data2  = resp2.json()
                        cands2 = data2.get("candidates", [])
                        if cands2:
                            parts2 = cands2[0].get("content", {}).get("parts", [])
                            if parts2:
                                raw2 = parts2[0].get("text", "").strip()
                                if raw2:
                                    cleaned2 = _cc_final_clean(raw2, lang)
                                    if len(cleaned2.split()) > wc:
                                        return cleaned2
                    return cleaned
                elif resp.status_code == 429:
                    continue
                else:
                    continue
            except Exception as e:
                _dprint(f"[GEMINI] Exception on {model}: {str(e)[:80]}")
                continue
        return ""

    def _open_reader(self, article: dict):
        current_lang = _lang_code(self.lang_var)
        ui   = _lang_ui(self.lang_var)
        self.loading_lbl.config(text=ui["preparing"])

        def _bg_worker():
            article_id = article.get("article_id", "")
            url        = article.get("url", "")
            title      = article.get("title", "")
            source     = article.get("source", "")
            pub_at     = article.get("published_at", "")

            min_cache_words = 80 if current_lang == "te" else 280
            cached = database.get_cached_ai(article_id)
            cached_body = ""
            if cached:
                raw_cached = (cached.get("content") or "").strip()
                if len(raw_cached.split()) >= min_cache_words:
                    if content_cleaner.validate_content_matches_title(
                            raw_cached, title, min_overlap=1):
                        cached_body = _cc_final_clean(raw_cached, current_lang, title=title)
                    else:
                        _dprint(f"[BUG17] Cache mismatch: {title[:60]}")
                        try:
                            database._delete_cached_ai(article_id)
                        except Exception:
                            pass

            scraped_text = ""
            scraped_img  = ""
            if not cached_body:
                try:
                    scraped_text, scraped_img = rss_manager.scrape_full_text(url)
                except Exception as e:
                    _dprint(f"[READER] Scrape error: {str(e)[:60]}")

            if not content_cleaner.validate_image_url(scraped_img):
                scraped_img = ""
            stored_img = article.get("image_url", "")
            if not content_cleaner.validate_image_url(stored_img):
                stored_img = ""
            effective_img = scraped_img or stored_img

            photo_obj = None
            if effective_img:
                try:
                    from PIL import Image
                    r = requests.get(effective_img, timeout=8, verify=False)
                    if r.status_code == 200:
                        img = Image.open(io.BytesIO(r.content))
                        img.thumbnail((760, 380))
                        photo_obj = img
                except Exception:
                    pass

            body = cached_body
            if not body:
                best = scraped_text or ""
                if not content_cleaner.is_content_sufficient(
                        best, config.MIN_CONTENT_WORDS):
                    best = content_cleaner.clean_metadata(
                        article.get("content", "")
                        or article.get("description", ""))
                src_wc       = len((best or "").split())
                target_words = "100 to 120" if current_lang == "te" else "350"

                if src_wc >= 150:
                    user_prompt = (
                        f"ARTICLE TITLE: {title}\n\nSOURCE ({src_wc} words):\n{best}\n\n"
                        f"Rewrite as a clean article of at least {target_words} words "
                        f"about the title topic. Remove all noise. "
                        f"End with a complete sentence.")
                elif src_wc >= 40:
                    user_prompt = (
                        f"ARTICLE TITLE: {title}\n\nSOURCE ({src_wc} words):\n{best or title}\n\n"
                        f"Write a news article of at least {target_words} words about: {title}. "
                        f"Use source facts. Expand background and significance. "
                        f"Do NOT invent facts. End with a complete sentence.")
                else:
                    user_prompt = (
                        f"ARTICLE TITLE: {title}\n\nSOURCE ({src_wc} words):\n{best or title}\n\n"
                        f"Write a news article of at least {target_words} words about: {title}. "
                        f"Explain background, significance, and context. "
                        f"Do NOT invent names, quotes, or numbers. "
                        f"End with a complete sentence.")

                body = self._call_gemini(user_prompt, current_lang)

                if (body and not content_cleaner.is_no_details_message(body)
                        and not content_cleaner.validate_content_matches_title(
                            body, title, min_overlap=1)):
                    _dprint(f"[BUG17] Body mismatch, retrying: {title[:60]}")
                    focus_prompt = (
                        f"ARTICLE TITLE: {title}\n\n"
                        f"Write ONLY about: {title}\n"
                        f"At least {target_words} words. Stay on topic. "
                        f"General knowledge only — no invented facts.")
                    retry_body = self._call_gemini(focus_prompt, current_lang)
                    if (retry_body and
                            content_cleaner.validate_content_matches_title(
                                retry_body, title, min_overlap=1)):
                        body = retry_body

                if not body:
                    fallback = content_cleaner.clean_metadata(
                        scraped_text or article.get("content", "")
                        or article.get("description", "") or title)
                    fallback = _cc_final_clean(fallback, current_lang, title=title)
                    if _cc_is_dup(fallback, title):
                        fallback = content_cleaner.no_details_message(current_lang)
                    body = fallback

                if (body and not content_cleaner.is_no_details_message(body)
                        and content_cleaner.validate_content_matches_title(
                            body, title, min_overlap=1)):
                    bundle = {"content": body, "ai_headline": ""}
                    try:
                        if database.validate_article_bundle(bundle):
                            database.save_cached_ai(article_id, bundle)
                    except Exception:
                        pass

            if body and not content_cleaner.is_no_details_message(body):
                body = _cc_final_clean(body, current_lang, title=title)

            self.after(0, lambda: self._render_reader(
                article, body, photo_obj, source, pub_at, url, current_lang))

        threading.Thread(target=_bg_worker, daemon=True).start()

    def _render_reader(self, article: dict, body: str, photo_pil,
                       source: str, pub_at: str, url: str, lang: str):
        self.loading_lbl.config(text="")
        T   = self.T
        ui  = _lang_ui(self.lang_var)
        cat = article.get("category", "general").lower()
        cat_col = CATEGORY_COLORS.get(cat, T["accent"])

        if self.reader_frame:
            self.reader_frame.destroy()

        self.reader_frame = tk.Frame(self, bg=T["bg"])
        self.reader_frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        self.reader_bg_canvas = GradientBackgroundCanvas(self.reader_frame, colors=T)
        self.reader_bg_canvas.pack(fill="both", expand=True)

        self.reader_workspace = tk.Frame(self.reader_frame, bg=T["surface"])
        self.reader_workspace.place(relx=0.5, rely=0.5, anchor="center", width=1160, height=740)

        nav = tk.Frame(self.reader_workspace, bg=T["surface"])
        nav.pack(fill="x", padx=14, pady=(15, 0))

        back_btn = tk.Button(nav, text=ui["back"], font=(FF, 9, "bold"),
                             bg="#1E293B" if self.is_dark else T["btn_back"], fg="#FFFFFF", bd=0, padx=18, pady=9,
                             cursor="hand2", relief="flat",
                             activebackground=T["surface3"],
                             command=self._close_reader)
        back_btn.pack(side="left", padx=10, pady=8)
        _bind_hover(back_btn, "#1E293B" if self.is_dark else T["btn_back"], T["surface3"])

        if url:
            ob_btn = tk.Button(nav, text=ui["open_browser"], font=(FF, 9),
                               bg=T["surface"], fg=T["accent"], bd=0,
                               padx=14, pady=9, cursor="hand2", relief="flat",
                               activebackground=T["accent_light"],
                               activeforeground=T["accent_hover"],
                               command=lambda: webbrowser.open(url))
            ob_btn.pack(side="right", padx=10, pady=8)
            _bind_hover(ob_btn, T["surface"], T["accent_light"])

        pane = tk.Frame(self.reader_workspace, bg=T["surface"])
        pane.pack(fill="both", expand=True, padx=14, pady=(5, 15))

        txt = scrolledtext.ScrolledText(
            pane, font=(FF, 13), wrap=tk.WORD, bd=0,
            bg=T["surface"], fg=T["text"],
            spacing1=6, spacing2=4, spacing3=12, padx=60, pady=32)
        txt.pack(fill="both", expand=True)

        txt.tag_configure("cat_dot", font=(FF, 10, "bold"),
                          foreground=cat_col, spacing1=4, spacing3=6)
        txt.tag_configure("headline", font=(FF, 24, "bold"),
                          foreground=T["text"], spacing1=4, spacing3=10)
        txt.tag_configure("meta", font=(FF, 10), foreground=T["subtext"],
                          spacing1=2, spacing3=14)
        txt.tag_configure("sep", font=(FF, 8), foreground=T["sep"],
                          spacing1=2, spacing3=20)
        txt.tag_configure("para", font=(FF, 13), foreground=T["text2"],
                          spacing1=6, spacing2=3, spacing3=16)
        txt.tag_configure("note", font=(FF, 11, "italic"),
                          foreground=T["subtext"], spacing1=10, spacing3=10)
        txt.tag_configure("hl_hdr", font=(FF, 12, "bold"),
                          foreground=T["accent"], spacing1=24, spacing3=10)
        txt.tag_configure("hl_item", font=(FF, 12), foreground=T["text2"],
                          lmargin1=28, lmargin2=44, spacing1=6, spacing3=8)

        txt.config(state=tk.NORMAL)

        txt.insert(tk.END, f"  ●  {cat.upper()}\n\n", "cat_dot")

        orig_title = content_cleaner.repair_garbled_telugu(
            article.get("title", "").strip())
        orig_title = _cc_strip_arrows(orig_title)
        txt.insert(tk.END, orig_title + "\n", "headline")

        meta_parts = []
        if source:
            meta_parts.append(source)
        if pub_at:
            meta_parts.append(pub_at[:10])
        if meta_parts:
            txt.insert(tk.END, "  •  ".join(meta_parts) + "\n", "meta")

        txt.insert(tk.END, "\n" + "─" * 90 + "\n\n", "sep")

        if photo_pil is not None:
            try:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(photo_pil)
                txt.image_create(tk.END, image=photo, pady=14)
                if not hasattr(txt, "_imgs"):
                    txt._imgs = []
                txt._imgs.append(photo)
                txt.insert(tk.END, "\n\n")
            except Exception:
                pass

        if body:
            wc = len(body.split())
            if content_cleaner.is_no_details_message(body):
                txt.insert(tk.END, body + "\n", "note")
            elif wc < 60:
                hl = _key_highlights(body, n=6)
                if hl:
                    txt.insert(tk.END, f"  {ui['key_highlights']}\n\n", "hl_hdr")
                    for h in hl:
                        txt.insert(tk.END, f"  •  {h}\n", "hl_item")
                    txt.insert(tk.END, "\n")
                else:
                    txt.insert(tk.END, body + "\n", "para")
            else:
                paras = [p.strip() for p in body.split("\n\n") if p.strip()]
                if not paras:
                    paras = _split_paragraphs(body)
                for p in paras:
                    p = p.strip()
                    if not p:
                        continue
                    p = _cc_strip_arrows(p)
                    p = content_cleaner.repair_garbled_telugu(p)
                    if p:
                        txt.insert(tk.END, p + "\n\n", "para")
                if wc >= 200:
                    hl = _key_highlights(body, n=4)
                    if hl:
                        txt.insert(tk.END, "─" * 90 + "\n\n", "sep")
                        txt.insert(tk.END, f"  {ui['key_highlights']}\n\n", "hl_hdr")
                        for h in hl:
                            txt.insert(tk.END, f"  •  {h}\n", "hl_item")
                        txt.insert(tk.END, "\n")

        txt.config(state=tk.DISABLED)
        txt.see("1.0")

    def _close_reader(self):
        if self.reader_frame:
            self.reader_frame.destroy()
            self.reader_frame = None

    def _search(self):
        q = self.search_var.get().strip().lower()
        if not q:
            self._render_feed(self.all_articles)
            return
        filtered = [
            a for a in self.all_articles
            if q in a.get("title", "").lower()
            or q in a.get("description", "").lower()
        ]
        if filtered:
            self._render_feed(filtered)
            return
        self.loading_lbl.config(text=_lang_ui(self.lang_var)["searching"])

        def _sw():
            try:
                res = api_manager.search_news(
                    q, _lang_code(self.lang_var), self.cat_var.get())
            except Exception:
                res = []
            self.after(0, lambda: self._render_feed(res))

        threading.Thread(target=_sw, daemon=True).start()

    def _toggle_theme(self):
        self.is_dark = not self.is_dark
        self.T       = DARK if self.is_dark else LIGHT
        database.save_user_preference(
            self.controller.session.current_user, "dark_mode", int(self.is_dark))
        arts = list(self.all_articles)
        for w in self.winfo_children():
            w.destroy()
        self.reader_frame   = None
        self._card_img_refs = []
        self.config(bg=self.T["bg"])
        self._build_ui()
        self.all_articles = arts
        self._render_feed(arts)