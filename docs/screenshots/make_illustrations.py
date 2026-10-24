"""Generate the step-by-step setup illustrations used in README.md.

These are simplified diagrams of each screen (not real screenshots), so they stay readable
and never go stale with small UI changes. Run:  python docs/screenshots/make_illustrations.py
To use real screenshots instead, save PNGs with the same base names and update README links.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
W, H = 1200, 675
SANS = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace"

INK = "#111827"
MUTED = "#6b7280"
FAINT = "#9ca3af"
LINE = "#e5e7eb"
SOFT = "#f3f4f6"
BG = "#f8fafc"
CARD = "#ffffff"
ACCENT = "#2563eb"
ACCENT_SOFT = "#dbeafe"
MARK = "#f97316"
GOOD = "#16a34a"
WARN = "#b45309"
WARN_SOFT = "#fef3c7"
DARK = "#0f172a"


class Svg:
    def __init__(self, w: int = W, h: int = H):
        self.w, self.h = w, h
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, fill=CARD, stroke=None, rx=8, sw=1, dash=None, opacity=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{st}{da}{op}/>')

    def text(self, x, y, s, size=14, weight=400, fill=INK, anchor="start", family=SANS, italic=False):
        it = ' font-style="italic"' if italic else ""
        self.add(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{it} xml:space="preserve" style="white-space:pre">{escape(str(s))}</text>'
        )

    def line(self, x1, y1, x2, y2, stroke=LINE, sw=1, dash=None):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{da}/>')

    def circle(self, cx, cy, r, fill, stroke=None, sw=1):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"{st}/>')

    def path(self, d, stroke=MUTED, sw=2, fill="none", marker=False, dash=None):
        mk = ' marker-end="url(#arrow)"' if marker else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"{mk}{da} stroke-linecap="round" stroke-linejoin="round"/>')

    # ---- widgets
    def badge(self, n, x, y):
        self.circle(x, y, 13, MARK, "#ffffff", 2.5)
        self.text(x, y + 5, n, 14, 700, "#ffffff", "middle")

    def highlight(self, x, y, w, h):
        self.rect(x - 5, y - 5, w + 10, h + 10, "none", MARK, rx=10, sw=2.5, dash="6 4")

    def button(self, x, y, label, kind="primary", w=None):
        w = w or max(84, len(label) * 8 + 32)
        if kind == "primary":
            self.rect(x, y, w, 34, ACCENT, rx=6)
            self.text(x + w / 2, y + 22, label, 13, 600, "#ffffff", "middle")
        elif kind == "outline":
            self.rect(x, y, w, 34, CARD, ACCENT, rx=6)
            self.text(x + w / 2, y + 22, label, 13, 600, ACCENT, "middle")
        else:
            self.text(x + w / 2, y + 22, label, 13, 600, ACCENT, "middle")
        return w

    def field(self, x, y, w, label, value, mono=False, dropdown=False):
        self.text(x, y, label, 12, 500, MUTED)
        self.rect(x, y + 8, w, 38, CARD, "#d1d5db", rx=6)
        self.text(x + 12, y + 33, value, 14, 400, INK, family=MONO if mono else SANS)
        if dropdown:
            self.path(f"M{x + w - 24} {y + 23} l6 6 l6 -6", MUTED, 2)

    def browser(self, x, y, w, h, url, app=None):
        self.rect(x, y, w, h, CARD, LINE, rx=12)
        self.add(f'<path d="M{x} {y + 12} a12 12 0 0 1 12 -12 h{w - 24} a12 12 0 0 1 12 12 v30 h-{w} z" fill="{SOFT}"/>')
        for i, c in enumerate(("#f87171", "#fbbf24", "#34d399")):
            self.circle(x + 20 + i * 18, y + 21, 5.5, c)
        self.rect(x + 82, y + 9, w - 100, 24, CARD, LINE, rx=12)
        self.add(f'<path d="M{x + 96} {y + 19} v-2 a3 3 0 0 1 6 0 v2" stroke="{FAINT}" stroke-width="1.5" fill="none"/>')
        self.rect(x + 94, y + 19, 10, 8, FAINT, rx=1.5)
        self.text(x + 112, y + 26, url, 12, 400, MUTED, family=MONO)
        self.line(x, y + 42, x + w, y + 42)
        if app:
            self.rect(x + 1, y + 43, w - 2, 44, CARD, rx=0)
            self.text(x + 20, y + 71, app, 16, 600, INK)
            self.line(x, y + 87, x + w, y + 87)
            return y + 87
        return y + 42

    def sidebar(self, x, y, h, items, active):
        self.rect(x, y, 200, h, BG, rx=0)
        self.line(x + 200, y, x + 200, y + h)
        for i, item in enumerate(items):
            yy = y + 18 + i * 36
            if item == active:
                self.rect(x + 8, yy - 4, 184, 30, ACCENT_SOFT, rx=15)
                self.text(x + 24, yy + 16, item, 13, 600, ACCENT)
            else:
                self.text(x + 24, yy + 16, item, 13, 400, INK)

    def steps(self, x, y, w, items, tip=None):
        self.rect(x, y, w, H - y - 40, CARD, LINE, rx=12)
        self.text(x + 20, y + 32, "What to do", 13, 700, MUTED)
        yy = y + 58
        for n, title, detail in items:
            self.badge(n, x + 33, yy + 2)
            self.text(x + 56, yy + 7, title, 15, 600, INK)
            for j, ln in enumerate(detail):
                self.text(x + 56, yy + 29 + j * 19, ln, 13, 400, MUTED)
            yy += 40 + 19 * len(detail) + 6
        if tip:
            ty = H - 40 - 18 - 22 * len(tip) - 18
            self.rect(x + 14, ty, w - 28, 22 * len(tip) + 26, WARN_SOFT, rx=8)
            for j, ln in enumerate(tip):
                self.text(x + 28, ty + 25 + j * 22, ln, 12.5, 500 if j == 0 else 400, WARN)

    def frame(self, step, title, subtitle):
        self.rect(0, 0, self.w, self.h, BG, rx=18)
        self.rect(0.5, 0.5, self.w - 1, self.h - 1, "none", LINE, rx=18)
        self.rect(40, 26, 96, 28, DARK, rx=14)
        self.text(88, 45, step, 12, 700, "#ffffff", "middle")
        self.text(150, 47, title, 22, 700, INK)
        self.text(self.w - 40, 46, subtitle, 12, 400, FAINT, "end", italic=True)

    def render(self) -> str:
        defs = (
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{MUTED}"/></marker>'
            '<filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="6" stdDeviation="10" flood-opacity="0.12"/></filter></defs>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img">'
            + defs + "".join(self.parts) + "</svg>\n"
        )


ILLUSTRATION = "Simplified illustration — labels match the real screens"
BX, BY, BW, BH = 40, 76, 760, 559  # browser box
SX, SY, SW = 824, 76, 336  # steps panel


def s01_project():
    s = Svg()
    s.frame("STEP 1", "Create a Google Cloud project", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "console.cloud.google.com/projectcreate")
    s.rect(BX + 1, top + 1, BW - 2, 46, CARD, rx=0)
    s.text(BX + 20, top + 30, "Google Cloud console", 15, 600, INK)
    s.rect(BX + 210, top + 9, 190, 30, SOFT, LINE, rx=6)
    s.text(BX + 224, top + 29, "Select a project", 13, 500, INK)
    s.path(f"M{BX + 380} {top + 20} l5 5 l5 -5", MUTED, 2)
    s.highlight(BX + 210, top + 9, 190, 30)
    s.badge("1", BX + 410, top + 10)
    s.line(BX, top + 47, BX + BW, top + 47)
    # dialog
    dx, dy = BX + 90, top + 80
    s.add('<g filter="url(#shadow)">')
    s.rect(dx, dy, 580, 360, CARD, LINE, rx=10)
    s.add("</g>")
    s.text(dx + 28, dy + 44, "New Project", 20, 600)
    s.button(dx + 420, dy + 20, "NEW PROJECT", "outline", 136)
    s.highlight(dx + 420, dy + 20, 136, 34)
    s.badge("2", dx + 566, dy + 18)
    s.field(dx + 28, dy + 96, 520, "Project name *", "sam-gsc-mcp")
    s.highlight(dx + 28, dy + 104, 520, 38)
    s.badge("3", dx + 558, dy + 110)
    s.text(dx + 28, dy + 168, "Project ID: sam-gsc-mcp-123456 (auto-generated)", 12, 400, MUTED)
    s.field(dx + 28, dy + 200, 520, "Location", "No organization", dropdown=True)
    s.button(dx + 28, dy + 290, "CREATE", "primary", 100)
    s.highlight(dx + 28, dy + 290, 100, 34)
    s.badge("4", dx + 138, dy + 292)
    s.button(dx + 140, dy + 290, "CANCEL", "text", 100)
    s.steps(SX, SY, SW, [
        ("1", "Open the project picker", ["At the top of console.cloud.google.com"]),
        ("2", "Click NEW PROJECT", ["Any Google account works"]),
        ("3", "Name it", ["e.g. sam-gsc-mcp — the name is", "only for you"]),
        ("4", "Click CREATE", ["Then select the new project in the", "picker before the next step"]),
    ], tip=["Free:", "Search Console API calls cost nothing."])
    return s


def s02_api():
    s = Svg()
    s.frame("STEP 2", "Enable the Search Console API", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "console.cloud.google.com/apis/library", "APIs & Services  ›  Library")
    s.rect(BX + 30, top + 22, 700, 40, CARD, "#d1d5db", rx=20)
    s.circle(BX + 54, top + 41, 7, "none", MUTED, 2)
    s.line(BX + 59, top + 46, BX + 64, top + 51, MUTED, 2)
    s.text(BX + 76, top + 47, "Google Search Console API", 14, 400, INK)
    s.highlight(BX + 30, top + 22, 700, 40)
    s.badge("1", BX + 742, top + 24)
    cy = top + 90
    s.rect(BX + 30, cy, 700, 170, CARD, LINE, rx=10)
    s.rect(BX + 50, cy + 22, 56, 56, ACCENT_SOFT, rx=10)
    s.path(f"M{BX + 64} {cy + 62} l10 -12 l8 7 l12 -16", ACCENT, 3)
    s.text(BX + 124, cy + 44, "Google Search Console API", 18, 600)
    s.text(BX + 124, cy + 68, "View Google Search Console data for your verified sites.", 13, 400, MUTED)
    s.button(BX + 124, cy + 100, "ENABLE", "primary", 104)
    s.highlight(BX + 124, cy + 100, 104, 34)
    s.badge("2", BX + 240, cy + 102)
    s.button(BX + 246, cy + 100, "TRY THIS API", "text", 130)
    cy2 = cy + 194
    s.rect(BX + 30, cy2, 700, 130, CARD, LINE, rx=10, dash="5 4")
    s.text(BX + 50, cy2 + 34, "Optional — Web Search Indexing API", 15, 600)
    s.text(BX + 50, cy2 + 58, "Only needed for request_indexing (JobPosting / BroadcastEvent pages).", 13, 400, MUTED)
    s.button(BX + 50, cy2 + 76, "ENABLE", "outline", 104)
    s.badge("3", BX + 166, cy2 + 78)
    s.steps(SX, SY, SW, [
        ("1", "Search the API Library", ["APIs & Services › Library ›", "\"Google Search Console API\""]),
        ("2", "Click ENABLE", ["Wait a few seconds until the API", "dashboard opens"]),
        ("3", "Indexing API (optional)", ["Enable only if you set", "GSC_ENABLE_INDEXING_API=true"]),
    ], tip=["Error \"API has not been used in project\"?", "You enabled it in a different project —", "check the project picker."])
    return s


def s03_consent():
    s = Svg()
    s.frame("STEP 3", "Configure the OAuth consent screen", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "console.cloud.google.com/auth/audience", "Google Auth Platform")
    s.sidebar(BX + 1, top + 1, BH - (top - BY) - 2, ["Overview", "Branding", "Audience", "Clients", "Data access", "Verification center"], "Audience")
    cx = BX + 230
    s.text(cx, top + 40, "Audience", 20, 600)
    s.text(cx, top + 76, "Publishing status", 12, 500, MUTED)
    s.text(cx, top + 98, "Testing", 15, 600)
    s.button(cx + 110, top + 76, "PUBLISH APP", "outline", 128)
    s.badge("4", cx + 250, top + 78)
    s.text(cx, top + 140, "User type", 12, 500, MUTED)
    s.text(cx, top + 162, "External", 15, 600)
    s.highlight(cx, top + 126, 120, 44)
    s.badge("2", cx + 134, top + 132)
    s.line(cx, top + 192, cx + 500, top + 192)
    s.text(cx, top + 222, "Test users", 16, 600)
    s.button(cx + 380, top + 202, "+ ADD USERS", "outline", 120)
    s.highlight(cx + 380, top + 202, 120, 34)
    s.badge("3", cx + 512, top + 204)
    s.rect(cx, top + 248, 500, 44, SOFT, rx=6)
    s.text(cx + 16, top + 276, "you@gmail.com", 14, 400, INK, family=MONO)
    s.rect(cx, top + 322, 500, 70, ACCENT_SOFT, rx=8)
    s.text(cx + 16, top + 348, "First time? Click Get started on Overview:", 13, 600, ACCENT)
    s.text(cx + 16, top + 372, "App name \"Sam GSC MCP\", your email, External, agree.", 13, 400, ACCENT)
    s.badge("1", cx + 512, top + 336)
    s.steps(SX, SY, SW, [
        ("1", "Get started (Branding)", ["App name: Sam GSC MCP", "Support + contact email: yours"]),
        ("2", "Audience: External", ["Works with any Gmail or", "Workspace account"]),
        ("3", "Add yourself as Test user", ["The Google account that can see", "your Search Console properties"]),
        ("4", "Publish app (recommended)", ["Avoids weekly re-login"]),
    ], tip=["Why publish?", "In Testing mode Google expires refresh", "tokens after 7 days. Publishing your own", "app is fine — you'll just see an", "\"unverified app\" notice once."])
    return s


def s04_client():
    s = Svg()
    s.frame("STEP 4", "Create the OAuth client (Desktop app)", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "console.cloud.google.com/auth/clients/create", "Google Auth Platform  ›  Clients  ›  Create client")
    fx = BX + 40
    s.field(fx, top + 40, 420, "Application type *", "Desktop app", dropdown=True)
    s.highlight(fx, top + 48, 420, 38)
    s.badge("1", fx + 432, top + 54)
    s.field(fx, top + 120, 420, "Name *", "Sam GSC MCP Desktop")
    s.button(fx, top + 196, "CREATE", "primary", 100)
    s.badge("2", fx + 112, top + 198)
    mx, my = BX + 300, top + 250
    s.add('<g filter="url(#shadow)">')
    s.rect(mx, my, 420, 210, CARD, LINE, rx=10)
    s.add("</g>")
    s.circle(mx + 34, my + 38, 12, "#dcfce7")
    s.path(f"M{mx + 28} {my + 38} l4 4 l8 -8", GOOD, 2.5)
    s.text(mx + 56, my + 44, "OAuth client created", 17, 600)
    s.text(mx + 24, my + 80, "Client ID", 12, 500, MUTED)
    s.text(mx + 24, my + 100, "1234567890-abc…apps.googleusercontent.com", 12.5, 400, INK, family=MONO)
    s.button(mx + 24, my + 140, "DOWNLOAD JSON", "outline", 150)
    s.highlight(mx + 24, my + 140, 150, 34)
    s.badge("3", mx + 186, my + 142)
    s.button(mx + 300, my + 140, "OK", "text", 90)
    s.steps(SX, SY, SW, [
        ("1", "Application type: Desktop app", ["Clients › + Create client", "(not \"Web application\")"]),
        ("2", "Click CREATE", []),
        ("3", "DOWNLOAD JSON", ["Save it somewhere permanent, e.g.", "~/secure/client_secrets.json"]),
        ("4", "Copy the full path", ["You'll paste it into", "GSC_OAUTH_CLIENT_SECRETS_FILE"]),
    ], tip=["Keep this file private.", "Never commit it to GitHub — the repo's", ".gitignore already blocks common names."])
    return s


def s05_service_account():
    s = Svg()
    s.frame("ALT", "Service account key (teams / automation)", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "console.cloud.google.com/iam-admin/serviceaccounts", "IAM & Admin  ›  Service accounts  ›  gsc-bot")
    cx = BX + 30
    s.text(cx, top + 38, "gsc-bot@sam-gsc-mcp-123456.iam.gserviceaccount.com", 14, 500, INK, family=MONO)
    s.highlight(cx, top + 20, 470, 26)
    s.badge("4", cx + 512, top + 24)
    for i, tab in enumerate(["DETAILS", "PERMISSIONS", "KEYS", "METRICS"]):
        tx = cx + i * 130
        s.text(tx, top + 84, tab, 13, 600, ACCENT if tab == "KEYS" else MUTED)
        if tab == "KEYS":
            s.rect(tx - 4, top + 92, 52, 3, ACCENT, rx=1)
    s.line(BX, top + 96, BX + BW, top + 96)
    s.button(cx - 12, top + 116, "ADD KEY", "outline", 120)
    s.path(f"M{cx + 94} {top + 130} l5 5 l5 -5", ACCENT, 2)
    s.badge("2", cx + 132, top + 118)
    mx, my = BX + 220, top + 180
    s.add('<g filter="url(#shadow)">')
    s.rect(mx, my, 420, 250, CARD, LINE, rx=10)
    s.add("</g>")
    s.text(mx + 24, my + 40, "Create private key for \"gsc-bot\"", 16, 600)
    s.text(mx + 24, my + 70, "Key type", 12, 500, MUTED)
    s.circle(mx + 34, my + 98, 8, CARD, ACCENT, 2)
    s.circle(mx + 34, my + 98, 4, ACCENT)
    s.text(mx + 52, my + 103, "JSON (recommended)", 14)
    s.circle(mx + 34, my + 130, 8, CARD, "#d1d5db", 2)
    s.text(mx + 52, my + 135, "P12", 14, 400, MUTED)
    s.highlight(mx + 20, my + 84, 200, 28)
    s.badge("3", mx + 232, my + 90)
    s.button(mx + 290, my + 190, "CREATE", "primary", 100)
    s.steps(SX, SY, SW, [
        ("1", "Create a service account", ["IAM & Admin › Service accounts ›", "+ Create (no project roles needed)"]),
        ("2", "Keys › Add key", ["› Create new key"]),
        ("3", "Choose JSON › Create", ["The key file downloads — store it", "safely (absolute path)"]),
        ("4", "Copy the client_email", ["Add it as a user in Search Console", "(next illustration)"]),
    ], tip=["Org policy blocks key creation?", "Use OAuth instead, or ask your admin", "to allow service account keys."])
    return s


def s06_gsc_user():
    s = Svg()
    s.frame("ALT", "Add the service account in Search Console", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "search.google.com/search-console/users", "Search Console  ·  sc-domain:example.com")
    s.path(f"M{BX + 368} {top - 26} l5 5 l5 -5", MUTED, 2)
    s.badge("1", BX + 400, top - 22)
    s.sidebar(BX + 1, top + 1, BH - (top - BY) - 2, ["Overview", "Performance", "URL inspection", "Pages", "Sitemaps", "Settings"], "Settings")
    cx = BX + 230
    s.text(cx, top + 40, "Settings  ›  Users and permissions", 18, 600)
    s.badge("2", cx + 330, top + 34)
    s.button(cx + 390, top + 60, "ADD USER", "primary", 110)
    for i, (who, role) in enumerate([("you@gmail.com", "Owner")]):
        yy = top + 110 + i * 44
        s.rect(cx, yy, 500, 40, SOFT, rx=6)
        s.text(cx + 14, yy + 26, who, 13.5, 400, INK, family=MONO)
        s.text(cx + 486, yy + 26, role, 13, 500, MUTED, "end")
    mx, my = cx + 10, top + 180
    s.add('<g filter="url(#shadow)">')
    s.rect(mx, my, 480, 250, CARD, LINE, rx=10)
    s.add("</g>")
    s.text(mx + 24, my + 40, "Add user", 17, 600)
    s.field(mx + 24, my + 70, 432, "Email address", "gsc-bot@sam-gsc-mcp-123456.iam.gse…", mono=True)
    s.field(mx + 24, my + 146, 200, "Permission", "Full", dropdown=True)
    s.highlight(mx + 24, my + 78, 432, 38)
    s.badge("3", mx + 466, my + 84)
    s.button(mx + 356, my + 200, "ADD", "primary", 100)
    s.steps(SX, SY, SW, [
        ("1", "Pick the property", ["Domain (sc-domain:) or URL-prefix"]),
        ("2", "Settings › Users and permissions", []),
        ("3", "ADD USER", ["Paste the service account email,", "Permission: Full. Owner only if you", "use the Indexing API."]),
        ("4", "Repeat for each property", []),
    ], tip=["Using OAuth (Steps 3–4)?", "Skip this — your own Google account", "already has access."])
    return s


def s07_config():
    s = Svg()
    s.frame("STEP 5", "Add Sam GSC MCP to your AI client", ILLUSTRATION)
    x, y, w, h = BX, BY, BW, BH
    s.rect(x, y, w, h, "#0b1220", rx=12)
    s.text(x + 20, y + 28, "claude_desktop_config.json", 13, 600, "#e5e7eb", family=MONO)
    s.text(x + w - 20, y + 28, "Settings › Developer › Edit Config", 12, 400, "#94a3b8", "end")
    s.line(x, y + 42, x + w, y + 42, "#1f2937")
    code = [
        ('{', "#e5e7eb"),
        ('  "mcpServers": {', "#e5e7eb"),
        ('    "sam-gsc": {', "#93c5fd"),
        ('      "command": "/Users/you/.local/bin/uvx",', "#fde68a"),
        ('      "args": ["--from",', "#e5e7eb"),
        ('        "git+https://github.com/krishanthsam/sam-gsc-mcp",', "#86efac"),
        ('        "sam-gsc-mcp"],', "#86efac"),
        ('      "env": {', "#e5e7eb"),
        ('        "GSC_OAUTH_CLIENT_SECRETS_FILE":', "#c4b5fd"),
        ('          "/Users/you/secure/client_secrets.json",', "#c4b5fd"),
        ('        "GSC_SITE_URL": "sc-domain:example.com"', "#f9a8d4"),
        ('      }', "#e5e7eb"),
        ('    }', "#e5e7eb"),
        ('  }', "#e5e7eb"),
        ('}', "#e5e7eb"),
    ]
    for i, (ln, col) in enumerate(code):
        yy = y + 76 + i * 28
        s.text(x + 22, yy, str(i + 1).rjust(2), 13, 400, "#475569", family=MONO)
        s.text(x + 60, yy, ln, 14, 400, col, family=MONO)
    s.rect(x + 52, y + 76 + 3 * 28 - 20, 470, 28, "none", MARK, rx=6, sw=2, dash="6 4")
    s.badge("2", x + 534, y + 76 + 3 * 28 - 6)
    s.rect(x + 52, y + 76 + 8 * 28 - 20, 520, 56, "none", MARK, rx=6, sw=2, dash="6 4")
    s.badge("3", x + 584, y + 76 + 8 * 28 + 6)
    s.badge("1", x + w - 238, y + 22)
    s.steps(SX, SY, SW, [
        ("1", "Open the config file", ["Claude Desktop: Settings › Developer", "› Edit Config. Cursor: ~/.cursor/mcp.json"]),
        ("2", "Use the FULL path to uvx", ["macOS/Linux: which uvx", "Windows: where uvx"]),
        ("3", "Point env at your JSON", ["Absolute path. Service account?", "Use GSC_CREDENTIALS_PATH instead"]),
        ("4", "Fully quit and reopen", ["Cmd+Q / right-click tray icon › Quit", "— closing the window isn't enough"]),
    ])
    return s


def s08_signin():
    s = Svg()
    s.frame("STEP 6", "Sign in with Google (first run only)", ILLUSTRATION)
    top = s.browser(BX, BY, BW, BH, "accounts.google.com/signin/oauth/…")
    # left card: unverified warning
    lx, ly = BX + 24, top + 26
    s.rect(lx, ly, 344, 330, CARD, LINE, rx=10)
    s.circle(lx + 36, ly + 38, 14, WARN_SOFT)
    s.text(lx + 36, ly + 44, "!", 16, 800, WARN, "middle")
    s.text(lx + 62, ly + 44, "Google hasn't verified this app", 15, 600)
    s.text(lx + 20, ly + 84, "The app is requesting access to", 13, 400, MUTED)
    s.text(lx + 20, ly + 104, "sensitive info in your Google Account.", 13, 400, MUTED)
    s.text(lx + 20, ly + 150, "Advanced", 13, 600, ACCENT)
    s.highlight(lx + 18, ly + 134, 70, 22)
    s.badge("2", lx + 102, ly + 140)
    s.text(lx + 20, ly + 186, "Go to Sam GSC MCP (unsafe)", 13, 600, ACCENT)
    s.highlight(lx + 18, ly + 170, 200, 22)
    s.text(lx + 20, ly + 230, "Shown because it's your own", 12, 400, FAINT, italic=True)
    s.text(lx + 20, ly + 248, "unverified OAuth app — expected.", 12, 400, FAINT, italic=True)
    s.button(lx + 230, ly + 278, "BACK", "primary", 90)
    # right card: consent
    rx_, ry = BX + 392, top + 26
    s.rect(rx_, ry, 344, 330, CARD, LINE, rx=10)
    s.text(rx_ + 20, ry + 40, "Sam GSC MCP wants access", 15, 600)
    s.text(rx_ + 20, ry + 60, "to your Google Account", 15, 600)
    s.text(rx_ + 20, ry + 92, "you@gmail.com", 13, 400, MUTED, family=MONO)
    s.rect(rx_ + 20, ry + 120, 304, 70, SOFT, rx=8)
    s.rect(rx_ + 34, ry + 140, 16, 16, ACCENT, rx=3)
    s.path(f"M{rx_ + 37} {ry + 148} l3 3 l6 -6", "#ffffff", 2)
    s.text(rx_ + 60, ry + 152, "View and manage Search Console", 13)
    s.text(rx_ + 60, ry + 172, "data for your verified sites", 13)
    s.highlight(rx_ + 20, ry + 120, 304, 70)
    s.badge("3", rx_ + 336, ry + 128)
    s.button(rx_ + 224, ry + 278, "Continue", "primary", 100)
    # success toast
    tx, ty = BX + 24, top + 380
    s.rect(tx, ty, 712, 64, "#f0fdf4", "#bbf7d0", rx=10)
    s.circle(tx + 32, ty + 32, 12, "#dcfce7")
    s.path(f"M{tx + 26} {ty + 32} l4 4 l8 -8", GOOD, 2.5)
    s.text(tx + 56, ty + 28, "localhost — Sam GSC MCP is connected to Google Search Console.", 13.5, 600, "#166534")
    s.text(tx + 56, ty + 48, "You can close this tab and return to your AI assistant.", 13, 400, "#166534")
    s.badge("4", tx + 700, ty + 4)
    s.badge("1", BX + 740, top - 30)
    s.steps(SX, SY, SW, [
        ("1", "A browser tab opens by itself", ["On the first tool call, or when you", "run the reauthenticate tool"]),
        ("2", "Unverified app? Advanced", ["› Go to Sam GSC MCP — it's your", "own OAuth client"]),
        ("3", "Allow Search Console access", ["Pick the account that owns or", "can see your properties"]),
        ("4", "Close the tab", ["Token is saved; no more logins"]),
    ], tip=["\"Error 403: access_denied\"?", "Add your Gmail as a Test user (Step 3)", "or publish the app."])
    return s


def s09_chat():
    s = Svg()
    s.frame("STEP 7", "Ask your first question", ILLUSTRATION)
    x, y, w, h = BX, BY, BW, BH
    s.rect(x, y, w, h, CARD, LINE, rx=12)
    s.rect(x + 1, y + 1, w - 2, 44, SOFT, rx=12)
    s.text(x + 20, y + 29, "AI assistant  ·  sam-gsc connected", 13, 600, MUTED)
    s.circle(x + w - 30, y + 23, 5, GOOD)
    # user bubble
    s.rect(x + 300, y + 66, 436, 64, ACCENT, rx=14)
    s.text(x + 320, y + 93, "List my GSC properties, then give me a", 14, 500, "#ffffff")
    s.text(x + 320, y + 115, "28-day summary for example.com", 14, 500, "#ffffff")
    s.badge("1", x + 290, y + 70)
    # tool chips
    for i, (name, note) in enumerate([("list_properties", "3 properties"), ("get_site_summary", "28 vs previous 28 days")]):
        yy = y + 152 + i * 40
        s.rect(x + 24, yy, 420, 32, SOFT, LINE, rx=16)
        s.circle(x + 44, yy + 16, 6, GOOD)
        s.text(x + 60, yy + 21, f"sam-gsc · {name}", 13, 600, INK, family=MONO)
        s.text(x + 432, yy + 21, note, 12, 400, MUTED, "end")
    s.badge("2", x + 456, y + 160)
    # answer
    ay = y + 250
    s.text(x + 24, ay, "Here's example.com for the last 28 days (vs the previous 28):", 14, 600)
    cols = [("Metric", 24), ("This period", 220), ("Previous", 380), ("Change", 540)]
    s.rect(x + 24, ay + 16, 712, 34, SOFT, rx=6)
    for label, cx in cols:
        s.text(x + cx + 12, ay + 38, label, 12.5, 600, MUTED)
    rows = [("Clicks", "12,480", "11,512", "+8.4%"), ("Impressions", "402,300", "371,020", "+8.4%"),
            ("CTR", "3.10%", "3.10%", "±0.00 pts"), ("Avg position", "14.2", "15.0", "↑ 0.8")]
    for i, r in enumerate(rows):
        yy = ay + 74 + i * 32
        for (label, cx), val in zip(cols, r):
            col = GOOD if val.startswith(("+", "↑")) else INK
            s.text(x + cx + 12, yy, val, 13.5, 600 if cx == 24 else 400, col)
        s.line(x + 24, yy + 10, x + 736, yy + 10)
    s.text(x + 24, ay + 220, "Quick wins: 14 queries sit at positions 4–20 with 50+ impressions…", 13.5, 400, MUTED)
    s.text(x + w - 20, y + h - 16, "sample data", 11, 400, FAINT, "end", italic=True)
    s.badge("3", x + 505, ay - 5)
    s.steps(SX, SY, SW, [
        ("1", "Ask in plain English", ["\"List my GSC properties\" is the", "best first test"]),
        ("2", "Allow the tool calls", ["Your client may ask once per tool", "(\"Always allow\" is fine for reads)"]),
        ("3", "Keep going", ["Try the Sample Prompts section or", "the built-in prompts / skills"]),
        ("4", "Something off?", ["Ask: \"call get_capabilities\" — it", "shows auth status and settings"]),
    ])
    return s


def s00_how_it_works():
    s = Svg(1200, 560)
    s.rect(0, 0, 1200, 560, BG, rx=18)
    s.rect(0.5, 0.5, 1199, 559, "none", LINE, rx=18)
    s.text(40, 52, "How Sam GSC MCP works", 22, 700)
    s.text(40, 78, "Runs on your computer. Your Google credentials never leave it.", 13, 400, MUTED)

    def box(x, y, w, h, title, lines, fill=CARD, stroke=LINE, title_col=INK):
        s.rect(x, y, w, h, fill, stroke, rx=12)
        s.text(x + 18, y + 32, title, 15, 700, title_col)
        for i, ln in enumerate(lines):
            s.text(x + 18, y + 58 + i * 21, ln, 12.5, 400, MUTED)

    box(40, 120, 250, 340, "AI client", ["Claude Desktop / Claude Code", "Cursor · VS Code · Windsurf", "Codex CLI · Gemini CLI", "Any MCP client", "", "You ask in plain English:", "\"Which pages lost clicks", " this month?\""])
    s.rect(360, 110, 470, 360, CARD, ACCENT, rx=14, sw=2)
    s.text(380, 142, "Sam GSC MCP server", 16, 700, ACCENT)
    s.text(380, 164, "Python · MCP SDK 1.x or 2.x · stdio or HTTP", 12, 400, MUTED)
    groups = [("Setup & auth", "OAuth · service account · ADC"), ("Analytics", "queries, pages, periods, hourly, CSV"),
              ("SEO insights", "quick wins, cannibalization, brand"), ("Inspection", "index status, coverage, canonicals"),
              ("Sitemaps", "list · submit · delete (guarded)"), ("Indexing API", "opt-in URL notifications"),
              ("Skills + prompts", "11 playbooks · 6 workflows")]
    for i, (g, d) in enumerate(groups):
        col, row = i % 2, i // 2
        gx, gy = 380 + col * 222, 186 + row * 66
        s.rect(gx, gy, 210, 56, ACCENT_SOFT if g != "Indexing API" else SOFT, rx=8)
        s.text(gx + 12, gy + 23, g, 13, 700, ACCENT if g != "Indexing API" else MUTED)
        s.text(gx + 12, gy + 42, d, 11, 400, MUTED)
    box(900, 120, 260, 340, "Google", ["Search Console API", "  · Search Analytics", "  · URL Inspection", "  · Sites & Sitemaps", "Web Search Indexing API", "  (optional)", "", "Your sitemap.xml (read-only)"])
    s.path("M292 250 H352", MUTED, 2, marker=True)
    s.path("M352 300 H298", MUTED, 2, marker=True)
    s.text(322, 238, "tool call", 11, 500, MUTED, "middle")
    s.text(322, 318, "JSON", 11, 500, MUTED, "middle")
    s.path("M832 250 H892", MUTED, 2, marker=True)
    s.path("M892 300 H838", MUTED, 2, marker=True)
    s.text(862, 238, "HTTPS", 11, 500, MUTED, "middle")
    s.text(862, 318, "data", 11, 500, MUTED, "middle")
    s.rect(360, 486, 800, 46, SOFT, rx=10)
    s.text(380, 514, "Local files:  token.json + config.json (OS config folder)  ·  CSV exports (~/Documents/sam-gsc-exports)  ·  no telemetry", 12.5, 500, INK)
    return s


def s10_tools():
    sys.path.insert(0, str(OUT.parents[1]))
    from sam_gsc_mcp import server  # noqa: E402

    groups: dict[str, list[dict]] = {}
    for t in server.TOOL_REGISTRY:
        if t["alias"]:
            continue
        groups.setdefault(server.CATEGORY_LABELS[t["toolset"]], []).append(t)
    s = Svg(1200, 720)
    s.rect(0, 0, 1200, 720, "#0b1220", rx=18)
    s.text(40, 50, "$ get_capabilities", 16, 600, "#86efac", family=MONO)
    total = sum(len(v) for v in groups.values())
    on = sum(1 for v in groups.values() for t in v if t["enabled"])
    s.text(1160, 50, f"real output · {total} tools ({on} on by default)", 13, 400, "#94a3b8", "end", family=MONO)
    layout = [
        ["Setup & server", "Reference (schema)", "SEO skills (playbooks)", "Properties"],
        ["Search analytics & reporting", "SEO insights"],
        ["URL inspection & indexing status", "Indexing API (opt-in)", "Sitemaps"],
    ]
    cols = [[(g, groups[g]) for g in col if g in groups] for col in layout]
    for c, groups_in_col in enumerate(cols):
        x = 40 + c * 380
        y = 92
        for g, items in groups_in_col:
            s.text(x, y, g, 13.5, 700, "#93c5fd", family=MONO)
            y += 24
            for t in items:
                col = "#e5e7eb" if t["enabled"] else "#64748b"
                mark = "●" if t["enabled"] else "○"
                s.text(x + 4, y, f"{mark} {t['name']}", 13, 400, col, family=MONO)
                if t["destructive"]:
                    s.text(x + 330, y, "guarded", 10.5, 600, "#fca5a5", "end", family=MONO)
                elif not t["enabled"]:
                    s.text(x + 330, y, "opt-in", 10.5, 600, "#fbbf24", "end", family=MONO)
                y += 21
            y += 16
    s.text(40, 700, "● on by default   ○ opt-in (GSC_ENABLE_INDEXING_API)   guarded = needs GSC_ALLOW_DESTRUCTIVE   + 6 compatibility aliases (GSC_COMPAT_ALIASES)", 12, 400, "#94a3b8", family=MONO)
    return s


SCENES = {
    "00-how-it-works": s00_how_it_works,
    "01-create-project": s01_project,
    "02-enable-search-console-api": s02_api,
    "03-oauth-consent-screen": s03_consent,
    "04-oauth-client-desktop-app": s04_client,
    "05-service-account-key": s05_service_account,
    "06-search-console-add-user": s06_gsc_user,
    "07-client-config": s07_config,
    "08-google-sign-in": s08_signin,
    "09-first-prompt": s09_chat,
    "10-tools-list": s10_tools,
}


if __name__ == "__main__":
    only = set(sys.argv[1:])
    for name, fn in SCENES.items():
        if only and name not in only:
            continue
        (OUT / f"{name}.svg").write_text(fn().render(), encoding="utf-8")
        print("wrote", name)
