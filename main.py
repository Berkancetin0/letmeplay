"""
Let Me Play  v4.0
- No emojis (SVG icons only)
- Fixed collapse button
- Fixed settings panel (no duplicate open)
- Anti-aliased borders and text
- Clean readable layout
"""

import sys, json, time, base64, random, struct, zlib, math
import threading, webbrowser, urllib.parse, http.server
from pathlib import Path

import requests

try:
    from pynput import keyboard as _kb
    HAS_HK = True
except ImportError:
    HAS_HK = False

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QSlider,
    QHBoxLayout, QVBoxLayout, QLineEdit, QFrame,
    QGraphicsDropShadowEffect, QSpinBox,
)
from PyQt6.QtCore  import Qt, QTimer, QThread, pyqtSignal, QPoint, QRect, QSize
from PyQt6.QtGui   import (
    QPixmap, QImage, QPainter, QColor, QPainterPath,
    QBrush, QPen, QIcon, QCursor, QFont, QFontMetrics,
    QLinearGradient, QRadialGradient,
)
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray

# ══════════════════════════════════════════════════
#  COLOUR PALETTE
# ══════════════════════════════════════════════════
GREEN       = "#1ed760"
GREEN_DARK  = "#17b84e"
GREEN_DIM   = "rgba(30,215,96,0.15)"
GREEN_GLOW  = "rgba(30,215,96,0.25)"

BG          = "#07090a"
CARD        = "#0d1210"
CARD2       = "#141e18"
BORDER      = "rgba(255,255,255,0.08)"
BORDER_G    = "rgba(30,215,96,0.28)"

TEXT        = "#e4f0e8"
TEXT_DIM    = "rgba(228,240,232,0.52)"
TEXT_MUTED  = "rgba(228,240,232,0.28)"
DANGER      = "#f04040"
DANGER_DIM  = "rgba(240,64,64,0.15)"

APP  = "Let Me Play"
VER  = "4.0"
BASE_W  = 300
ART_SZ  = 44
PORT    = 8888

AUTH_F = Path.home() / ".lmp_auth.json"
CFG_F  = Path.home() / ".lmp_cfg.json"

DEFAULT_CFG = {
    "x": -1, "y": -1,
    "opacity": 94,
    "scale":   100,
    "hk_play":     "<ctrl>+<shift>+p",
    "hk_next":     "<ctrl>+<shift>+n",
    "hk_prev":     "<ctrl>+<shift>+b",
    "hk_collapse": "<ctrl>+<shift>+m",
    "hk_settings": "<ctrl>+<shift>+s",
}

CLIENT_ID     = "SENIN_CLIENT_ID"
CLIENT_SECRET = "SENIN_CLIENT_SECRET"
REDIRECT_URI  = "http://127.0.0.1:8888/callback"
SCOPES        = ("user-read-currently-playing "
                 "user-read-playback-state "
                 "user-modify-playback-state")

def load_cfg():
    try:
        if CFG_F.exists():
            return {**DEFAULT_CFG, **json.loads(CFG_F.read_text())}
    except Exception: pass
    return dict(DEFAULT_CFG)

def save_cfg(d):
    try: CFG_F.write_text(json.dumps(d))
    except Exception: pass

# ══════════════════════════════════════════════════
#  SVG ICON HELPER  — no emojis anywhere
# ══════════════════════════════════════════════════
def _svg_pix(svg_body: str, size: int, color: str = "#e4f0e8") -> QPixmap:
    """Render an inline SVG path to a QPixmap at given size."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 24 24" width="{size}" height="{size}">'
        f'<path fill="{color}" d="{svg_body}"/>'
        f'</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return pix

# SVG path data (Material Design icons)
# All icon colors must be hex strings — rgba() doesn't work in SVG fill
ICO_DIM   = "#7a9982"   # muted for prev/next
ICO_MUTED = "#4a6650"   # very muted for shuffle/repeat off
ICO_TEXT  = "#c8e0cc"   # bright for hover

ICO = {
    "play":     "M8 5v14l11-7z",
    "pause":    "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "next":     "m6 18 8.5-6L6 6v12zm10-12v12h2V6h-2z",
    "prev":     "M6 6h2v12H6zm3.5 6 8.5 6V6z",
    "shuffle":  "M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
    "repeat":   "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
    "vol_lo":   "M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z",
    "vol_hi":   "M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
    "collapse": "M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z",
    "expand":   "M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6 1.41 1.41z",
    "settings": "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.57 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z",
    "logout":   "M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z",
    "note":     "M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z",
    "chevron_down": "M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z",
    "chevron_right": "M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z",
}

def ico(name: str, size: int = 16, color: str = TEXT) -> QPixmap:
    return _svg_pix(ICO[name], size, color)


# ══════════════════════════════════════════════════
#  APP ICON (pure Python PNG/ICO)
# ══════════════════════════════════════════════════
def _clamp(v): return max(0, min(255, int(v)))

def _make_png(size: int) -> bytes:
    BG_C = (7, 9, 10); A1 = (30, 215, 96); A2 = (130, 240, 160)
    cx = cy = size / 2.0; r = size / 2.0; rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dist = math.hypot(x - cx, y - cy)
            if dist >= r: row += [0,0,0,0]; continue
            t = (dist / r) * 0.5
            R  = _clamp(BG_C[0] + 40*t); G = _clamp(BG_C[1] + 55*t); B = _clamp(BG_C[2] + 30*t)
            ring, rw = r * 0.80, r * 0.08
            if abs(dist - ring) < rw:
                b2 = 1.0 - abs(dist - ring) / rw
                R = _clamp(R*(1-b2*.8)+A1[0]*b2*.8)
                G = _clamp(G*(1-b2*.8)+A1[1]*b2*.8)
                B = _clamp(B*(1-b2*.8)+A1[2]*b2*.8)
            ts = r * 0.38; rx = (x - cx) + ts * 0.06; ry = y - cy
            my = ts * (0.60 + rx * 0.52 / ts) if ts > 0 else 0
            if -ts*.54 <= rx <= ts*.64 and abs(ry) <= my:
                p2 = _clamp((rx + ts*.54) / (ts*1.18) * 255)
                R = _clamp(A1[0]*(1-p2/255*.1) + A2[0]*(p2/255*.1))
                G = _clamp(A1[1]*(1-p2/255*.05))
                B = _clamp(A1[2]*(1-p2/255*.2))
            alpha = _clamp(255*(r-dist)) if dist > r-1.5 else 255
            row += [_clamp(R), _clamp(G), _clamp(B), alpha]
        rows.append(row)
    def ck(n, d):
        crc = zlib.crc32(n+d) & 0xffffffff
        return struct.pack('>I',len(d)) + n + d + struct.pack('>I',crc)
    png  = b'\x89PNG\r\n\x1a\n'
    png += ck(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
    raw  = b''.join(b'\x00' + bytes(row) for row in rows)
    png += ck(b'IDAT', zlib.compress(raw, 6))
    png += ck(b'IEND', b'')
    return png

def app_icon() -> QIcon:
    icon = QIcon()
    for s in [16, 32, 48, 64, 128, 256]:
        pm = QPixmap(); pm.loadFromData(_make_png(s)); icon.addPixmap(pm)
    return icon

def icon_pix(size: int) -> QPixmap:
    pm = QPixmap(); pm.loadFromData(_make_png(size)); return pm


# ══════════════════════════════════════════════════
#  TOKEN MANAGER
# ══════════════════════════════════════════════════
class Tokens:
    def __init__(self):
        self.access = self.refresh = None
        self.expiry = 0.0; self._load()

    def _load(self):
        try:
            if AUTH_F.exists():
                d = json.loads(AUTH_F.read_text())
                self.access  = d.get("access")
                self.refresh = d.get("refresh")
                self.expiry  = d.get("expiry", 0.0)
        except Exception: pass

    def _save(self):
        try:
            AUTH_F.write_text(json.dumps({
                "access": self.access, "refresh": self.refresh, "expiry": self.expiry,
            }))
        except Exception: pass

    def get(self):
        if self.refresh and time.time() > self.expiry - 60:
            self._refresh()
        return self.access

    def _refresh(self):
        try:
            creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
            r = requests.post("https://accounts.spotify.com/api/token",
                data={"grant_type":"refresh_token","refresh_token":self.refresh},
                headers={"Authorization":f"Basic {creds}"}, timeout=6)
            if r.ok:
                d = r.json(); self.access = d["access_token"]
                self.expiry = time.time() + d["expires_in"]; self._save()
        except Exception: pass

    def exchange(self, code: str) -> bool:
        try:
            creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
            r = requests.post("https://accounts.spotify.com/api/token",
                data={"grant_type":"authorization_code","code":code,"redirect_uri":REDIRECT_URI},
                headers={"Authorization":f"Basic {creds}"}, timeout=6)
            if r.ok:
                d = r.json(); self.access = d["access_token"]
                self.refresh = d.get("refresh_token","")
                self.expiry = time.time() + d["expires_in"]; self._save(); return True
        except Exception: pass
        return False

    def revoke(self):
        self.access = self.refresh = None
        self.expiry = 0.0; AUTH_F.unlink(missing_ok=True)

    @property
    def ok(self): return bool(self.refresh or self.access)

_tok = Tokens()


# ══════════════════════════════════════════════════
#  OAUTH SERVER
# ══════════════════════════════════════════════════
_auth_ev   = threading.Event()
_auth_code = [None]

class _OAuthH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _auth_code[0] = qs.get("code", [None])[0]
        body = (b"<html><body style='background:#07090a;color:#1ed760;"
                b"font-family:Segoe UI;display:flex;align-items:center;"
                b"justify-content:center;height:100vh;margin:0;font-size:1.2rem;'>"
                b"<p>Login successful &mdash; you can close this tab.</p></body></html>")
        self.send_response(200); self.send_header("Content-Type","text/html;charset=utf-8")
        self.end_headers(); self.wfile.write(body); _auth_ev.set()

def _oauth_server():
    s = http.server.HTTPServer(("127.0.0.1", PORT), _OAuthH)
    s.timeout = 120; s.handle_request()


# ══════════════════════════════════════════════════
#  SPOTIFY HELPERS
# ══════════════════════════════════════════════════
class Poller(QThread):
    data = pyqtSignal(dict)
    def __init__(self): super().__init__(); self._on = True
    def run(self):
        while self._on: self.poll(); time.sleep(4)
    def poll(self):
        tok = _tok.get()
        if not tok: return
        try:
            r = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {tok}"}, timeout=5)
            if r.status_code == 204: self.data.emit({"idle": True}); return
            if not r.ok: return
            d = r.json(); item = d.get("item") or {}
            imgs = item.get("album",{}).get("images",[])
            self.data.emit({
                "name":    item.get("name",""),
                "artist":  ", ".join(a["name"] for a in item.get("artists",[])),
                "art":     imgs[-1]["url"] if imgs else None,
                "pos":     d.get("progress_ms",0),
                "dur":     item.get("duration_ms",1),
                "playing": d.get("is_playing",False),
            })
        except Exception: pass
    def stop(self): self._on = False

def sp(method, path, body=None):
    tok = _tok.get()
    if not tok: return
    try:
        requests.request(method, f"https://api.spotify.com/v1/me/player{path}",
            headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"},
            json=body, timeout=5)
    except Exception: pass

class ArtLoader(QThread):
    ready = pyqtSignal(QPixmap)
    def __init__(self, url): super().__init__(); self.url = url
    def run(self):
        try:
            data = requests.get(self.url, timeout=5).content
            img  = QImage(); img.loadFromData(data)
            raw  = QPixmap.fromImage(img).scaled(
                ART_SZ, ART_SZ,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            out = QPixmap(ART_SZ, ART_SZ); out.fill(Qt.GlobalColor.transparent)
            p = QPainter(out); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip = QPainterPath(); clip.addRoundedRect(0,0,ART_SZ,ART_SZ,7,7)
            p.setClipPath(clip); p.drawPixmap(0,0,raw); p.end()
            self.ready.emit(out)
        except Exception: pass


# ══════════════════════════════════════════════════
#  HOTKEY MANAGER
# ══════════════════════════════════════════════════
class HotkeyMgr:
    def __init__(self):
        self._combos:  dict = {}
        self._pressed: set  = set()
        self._fired:   set  = set()
        self._listener      = None

    def register(self, hk: str, cb):
        if not HAS_HK: return
        keys = self._parse(hk)
        if keys: self._combos[frozenset(keys)] = cb

    def _parse(self, s):
        km = {"<ctrl>":_kb.Key.ctrl,"<shift>":_kb.Key.shift,"<alt>":_kb.Key.alt}
        out = []
        for p in s.lower().split("+"):
            p = p.strip()
            if p in km: out.append(km[p])
            elif len(p) == 1: out.append(_kb.KeyCode.from_char(p))
        return out

    def _norm(self, k):
        al = {_kb.Key.ctrl_l:_kb.Key.ctrl, _kb.Key.ctrl_r:_kb.Key.ctrl,
              _kb.Key.shift_l:_kb.Key.shift,_kb.Key.shift_r:_kb.Key.shift,
              _kb.Key.alt_l:_kb.Key.alt,   _kb.Key.alt_r:_kb.Key.alt}
        return al.get(k, k)

    def start(self):
        if not HAS_HK or self._listener: return
        def on_press(k):
            nk = self._norm(k); self._pressed.add(nk)
            for combo, cb in list(self._combos.items()):
                if combo.issubset(self._pressed) and combo not in self._fired:
                    self._fired.add(combo); QTimer.singleShot(0, cb)
        def on_release(k):
            nk = self._norm(k); self._pressed.discard(nk)
            self._fired = {c for c in self._fired if c.issubset(self._pressed)}
        self._listener = _kb.Listener(on_press=on_press, on_release=on_release, suppress=False)
        self._listener.daemon = True; self._listener.start()

    def stop(self):
        if self._listener: self._listener.stop(); self._listener = None
        self._combos.clear(); self._pressed.clear(); self._fired.clear()

_hk = HotkeyMgr()


# ══════════════════════════════════════════════════
#  PROGRESS BAR
# ══════════════════════════════════════════════════
class ProgBar(QWidget):
    seeked = pyqtSignal(float)
    def __init__(self):
        super().__init__()
        self._v = 0.0; self._hov = False
        self.setFixedHeight(4)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)
    def set_value(self, v):
        self._v = max(0.0, min(1.0, v)); self.update()
    def enterEvent(self, _): self._hov = True;  self.update()
    def leaveEvent(self, _): self._hov = False; self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # track
        p.setBrush(QBrush(QColor(255,255,255,20))); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 1, w, 2, 1, 1)
        # fill
        fw = int(w * self._v)
        if fw > 0:
            g = QLinearGradient(0,0,fw,0)
            g.setColorAt(0, QColor(GREEN_DARK)); g.setColorAt(1, QColor(GREEN))
            p.setBrush(QBrush(g)); p.drawRoundedRect(0, 1, fw, 2, 1, 1)
            # thumb on hover
            if self._hov:
                p.setBrush(QBrush(QColor(TEXT)))
                p.drawEllipse(max(0, fw-4), 0, 8, 4)
        p.end()
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.seeked.emit(max(0.0, min(1.0, e.position().x() / self.width())))


# ══════════════════════════════════════════════════
#  EQ BARS
# ══════════════════════════════════════════════════
class EQBars(QWidget):
    def __init__(self):
        super().__init__()
        self._on = False; self._h = [0.3,0.7,0.5,0.9]; self._d = [1,-1,1,-1]
        t = QTimer(self); t.timeout.connect(self._step); t.start(90)
    def set_on(self, v): self._on = v
    def _step(self):
        if self._on:
            self._h = [max(0.1,min(1.0,h+self._d[i]*random.uniform(0.07,0.28)))
                       for i,h in enumerate(self._h)]
            self._d = [1 if h<=0.1 else(-1 if h>=1.0 else d)
                       for h,d in zip(self._h,self._d)]
        else: self._h = [0.15]*4
        self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bw, gap = 2, 2; xo = (w-(4*bw+3*gap))//2; p.setPen(Qt.PenStyle.NoPen)
        for i, fh in enumerate(self._h):
            bh = max(2, int(h*fh)); x = xo+i*(bw+gap)
            if self._on:
                g = QLinearGradient(0,h-bh,0,h)
                g.setColorAt(0, QColor("#80e8a8")); g.setColorAt(1, QColor(GREEN_DARK))
                p.setBrush(QBrush(g))
            else: p.setBrush(QBrush(QColor(50,80,55)))
            p.drawRoundedRect(x, h-bh, bw, bh, 1, 1)
        p.end()


# ══════════════════════════════════════════════════
#  ICON BUTTON  — uses SVG, no emoji
# ══════════════════════════════════════════════════
class IconBtn(QPushButton):
    """A QPushButton that shows an SVG icon, with hover tint."""
    def __init__(self, icon_name: str, size: int = 32,
                 color=TEXT_DIM, hover_color=TEXT, parent=None):
        super().__init__(parent)
        self._name   = icon_name
        self._sz     = size
        self._col    = color
        self._hcol   = hover_color
        self._toggle = False
        self._on     = False
        self.setFixedSize(size, size)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlat(True)
        self.setStyleSheet("QPushButton{background:transparent;border:none;}")
        self._update_icon()

    def set_icon(self, name: str):
        self._name = name; self._update_icon()

    def set_on(self, on: bool):
        self._on = on; self._update_icon()

    def _update_icon(self):
        c = GREEN if (self._toggle and self._on) else self._col
        self.setIcon(QIcon(ico(self._name, self._sz - 8, c)))
        self.setIconSize(QSize(self._sz - 8, self._sz - 8))

    def enterEvent(self, e):
        c = GREEN if (self._toggle and self._on) else self._hcol
        self.setIcon(QIcon(ico(self._name, self._sz - 8, c)))
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._update_icon(); super().leaveEvent(e)

    def set_toggle(self, v: bool):
        self._toggle = True; self._on = v; self._update_icon()


class PlayBtn(QPushButton):
    """Green circle play/pause button."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._playing = False
        self.setFixedSize(38, 38)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN};
                border: none;
                border-radius: 19px;
            }}
            QPushButton:hover   {{ background: #28e86a; }}
            QPushButton:pressed {{ background: {GREEN_DARK}; }}
        """)
        self._refresh()

    def set_playing(self, v: bool):
        self._playing = v; self._refresh()

    def _refresh(self):
        name = "pause" if self._playing else "play"
        self.setIcon(QIcon(ico(name, 20, "#000000")))
        self.setIconSize(QSize(20, 20))


# ══════════════════════════════════════════════════
#  SPLASH SCREEN
# ══════════════════════════════════════════════════
class Splash(QWidget):
    done = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 220)
        sc = QApplication.primaryScreen().geometry()
        self.move(sc.center() - QPoint(160, 110))
        self._a = 0; self._phase = 0; self._ticks = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(14)

    def _tick(self):
        self._ticks += 1
        if self._phase == 0:
            self._a = min(255, self._a + 10)
            if self._a >= 255: self._phase = 1
        elif self._phase == 1:
            if self._ticks > 85: self._phase = 2
        else:
            self._a = max(0, self._a - 9)
            if self._a == 0:
                self._timer.stop()
                self.close()
                self.done.emit()
                return
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); a = self._a
        # card
        path = QPainterPath(); path.addRoundedRect(16, 16, w-32, h-32, 16, 16)
        p.setBrush(QBrush(QColor(7, 9, 10, a)))
        p.setPen(QPen(QColor(30, 215, 96, min(a, 80)), 1))
        p.drawPath(path)
        # glow
        glow = QRadialGradient(w/2, h/2-18, 58)
        glow.setColorAt(0, QColor(30, 215, 96, min(a, 45)))
        glow.setColorAt(1, QColor(30, 215, 96, 0))
        p.setBrush(QBrush(glow)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(w/2-58), int(h/2-76), 116, 116)
        # icon
        p.setOpacity(a / 255)
        p.drawPixmap(w//2 - 28, h//2 - 68, icon_pix(56))
        # title
        p.setPen(QColor(228, 240, 232, a))
        f = QFont("Segoe UI", 17, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRect(0, h//2-4, w, 30), Qt.AlignmentFlag.AlignHCenter, APP)
        # sub
        p.setPen(QColor(30, 215, 96, min(a, 150)))
        f2 = QFont("Segoe UI", 8); f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        p.setFont(f2)
        p.drawText(QRect(0, h//2+28, w, 20), Qt.AlignmentFlag.AlignHCenter,
                   "GAMING MUSIC OVERLAY")
        p.setOpacity(1.0); p.end()


# ══════════════════════════════════════════════════
#  SETUP WINDOW
# ══════════════════════════════════════════════════
class SetupWindow(QWidget):
    logged_in = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP} — Sign In")
        self.setWindowIcon(app_icon())
        self.setFixedSize(420, 500)
        self.setStyleSheet(f"""
            QWidget      {{ background:{BG}; color:{TEXT};
                           font-family:'Segoe UI',sans-serif; font-size:12px; }}
            QLabel       {{ background:transparent; }}
            QLineEdit    {{ background:{CARD}; border:1px solid rgba(30,215,96,0.2);
                           border-radius:8px; color:{TEXT};
                           font-size:12px; padding:10px 12px;
                           font-family:Consolas,monospace; }}
            QLineEdit:focus {{ border:1px solid {GREEN}; }}
            QPushButton#btn {{ background:{GREEN}; color:#000; border:none;
                border-radius:9px; font-size:13px; font-weight:700; padding:13px; }}
            QPushButton#btn:hover   {{ background:#28e86a; }}
            QPushButton#btn:pressed {{ background:{GREEN_DARK}; }}
        """)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(34,34,34,34); lay.setSpacing(16)
        # header
        hdr = QHBoxLayout(); hdr.setSpacing(14)
        ico_lbl = QLabel(); ico_lbl.setPixmap(icon_pix(44)); ico_lbl.setFixedSize(44,44)
        hdr.addWidget(ico_lbl)
        col = QVBoxLayout(); col.setSpacing(3)
        t1  = QLabel(APP); t1.setStyleSheet(f"font-size:17px;font-weight:700;color:{TEXT};")
        t2  = QLabel(f"Gaming Music Overlay  ·  v{VER}")
        t2.setStyleSheet(f"font-size:10px;color:{GREEN};letter-spacing:0.5px;")
        col.addWidget(t1); col.addWidget(t2); hdr.addLayout(col); hdr.addStretch()
        lay.addLayout(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{CARD2};"); lay.addWidget(sep)
        # steps
        box = QFrame()
        box.setStyleSheet(f"background:{CARD};border-radius:10px;"
                          f"border:1px solid rgba(30,215,96,0.12);")
        bl = QVBoxLayout(box); bl.setContentsMargins(16,14,16,14); bl.setSpacing(10)
        lh = QLabel("HOW TO GET STARTED")
        lh.setStyleSheet(f"font-size:9px;font-weight:700;color:{GREEN};letter-spacing:2px;")
        bl.addWidget(lh)
        for n, txt in [
            ("1", "Open developer.spotify.com/dashboard  →  Create App"),
            ("2", "Add Redirect URI:  http://127.0.0.1:8888/callback"),
            ("3", "Copy your Client ID & Client Secret below"),
            ("4", "Click Sign In  →  approve in browser  →  done!"),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            nb  = QLabel(n); nb.setFixedSize(22,22); nb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nb.setStyleSheet(f"background:rgba(30,215,96,0.15);color:{GREEN};"
                             f"border-radius:11px;font-size:10px;font-weight:700;")
            tb  = QLabel(txt); tb.setWordWrap(True)
            tb.setStyleSheet(f"font-size:11px;color:{TEXT_DIM};")
            row.addWidget(nb); row.addWidget(tb,1); bl.addLayout(row)
        lay.addWidget(box)
        # inputs
        for attr, lbl, ph, pwd in [
            ("_id",  "Client ID",     "Paste your Client ID…",     False),
            ("_sec", "Client Secret", "Paste your Client Secret…", True),
        ]:
            l = QLabel(lbl); l.setStyleSheet(f"font-size:11px;font-weight:600;color:{TEXT_DIM};")
            lay.addWidget(l)
            inp = QLineEdit(); inp.setPlaceholderText(ph)
            if pwd: inp.setEchoMode(QLineEdit.EchoMode.Password)
            setattr(self, attr, inp); lay.addWidget(inp)
        self._err = QLabel(""); self._err.setStyleSheet(f"font-size:10px;color:{DANGER};min-height:14px;")
        lay.addWidget(self._err)
        btn = QPushButton("Sign in with Spotify"); btn.setObjectName("btn")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(self._login); self._btn = btn; lay.addWidget(btn)

    def _login(self):
        cid = self._id.text().strip(); sec = self._sec.text().strip()
        if not cid or not sec: self._err.setText("Both fields are required."); return
        global CLIENT_ID, CLIENT_SECRET
        CLIENT_ID = cid; CLIENT_SECRET = sec
        self._err.setText(""); self._btn.setText("Opening browser…"); self._btn.setEnabled(False)
        threading.Thread(target=self._flow, daemon=True).start()

    def _flow(self):
        _auth_ev.clear(); _auth_code[0] = None
        threading.Thread(target=_oauth_server, daemon=True).start()
        url = ("https://accounts.spotify.com/authorize?" +
               urllib.parse.urlencode({"client_id":CLIENT_ID,"response_type":"code",
                                       "redirect_uri":REDIRECT_URI,"scope":SCOPES}))
        webbrowser.open(url); _auth_ev.wait(timeout=120)
        if _auth_code[0] and _tok.exchange(_auth_code[0]):
            self.logged_in.emit()
        else:
            self._err.setText("Login failed — please try again.")
            self._btn.setText("Sign in with Spotify"); self._btn.setEnabled(True)


# ══════════════════════════════════════════════════
#  SETTINGS PANEL
# ══════════════════════════════════════════════════
class SettingsPanel(QWidget):
    applied = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"{APP} — Settings")
        self.setWindowIcon(app_icon())
        self.setFixedSize(360, 700)
        self.setStyleSheet(f"""
            QWidget        {{ background:{BG}; color:{TEXT};
                             font-family:'Segoe UI',sans-serif; font-size:12px; }}
            QLabel         {{ background:transparent; }}
            QSpinBox       {{ background:{CARD}; border:1px solid rgba(30,215,96,0.18);
                             border-radius:7px; color:{TEXT}; font-size:12px;
                             padding:7px 10px; font-family:Consolas,monospace; }}
            QSpinBox:focus {{ border:1px solid {GREEN}; }}
            QSpinBox::up-button, QSpinBox::down-button
                           {{ background:{CARD2}; border:none; width:20px; }}
            QLineEdit      {{ background:{CARD}; border:1px solid rgba(30,215,96,0.18);
                             border-radius:6px; color:{TEXT}; font-size:11px;
                             padding:7px 10px; font-family:Consolas,monospace; }}
            QLineEdit:focus {{ border:1px solid {GREEN}; }}
            QSlider::groove:horizontal {{ height:4px;
                background:rgba(255,255,255,0.10); border-radius:2px; }}
            QSlider::sub-page:horizontal {{ background:{GREEN}; border-radius:2px; }}
            QSlider::handle:horizontal {{ width:14px; height:14px; margin:-5px 0;
                background:{TEXT}; border-radius:7px; }}
            QSlider::handle:horizontal:hover {{ background:{GREEN}; }}
            QPushButton#apply  {{ background:{GREEN}; color:#000; border:none;
                border-radius:8px; font-size:12px; font-weight:700; padding:11px; }}
            QPushButton#apply:hover   {{ background:#28e86a; }}
            QPushButton#apply:pressed {{ background:{GREEN_DARK}; }}
            QPushButton#cancel {{ background:transparent;
                border:1px solid rgba(255,255,255,0.12);
                border-radius:8px; color:{TEXT_DIM}; font-size:12px; padding:11px; }}
            QPushButton#cancel:hover {{ border-color:rgba(255,255,255,0.3); color:{TEXT}; }}
        """)
        self._cfg = dict(cfg); self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(14)
        # header
        hdr = QHBoxLayout(); hdr.setSpacing(10)
        il  = QLabel(); il.setPixmap(icon_pix(28)); il.setFixedSize(28,28); hdr.addWidget(il)
        t   = QLabel("Settings")
        t.setStyleSheet(f"font-size:15px;font-weight:700;color:{TEXT};margin-left:4px;")
        hdr.addWidget(t); hdr.addStretch(); lay.addLayout(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{CARD2};"); lay.addWidget(sep)

        SL = f"""
            QSlider::groove:horizontal {{ height:4px;
                background:rgba(255,255,255,0.10); border-radius:2px; }}
            QSlider::sub-page:horizontal {{ background:{GREEN}; border-radius:2px; }}
            QSlider::handle:horizontal {{ width:14px; height:14px; margin:-5px 0;
                background:{TEXT}; border-radius:7px; }}
            QSlider::handle:horizontal:hover {{ background:{GREEN}; }}
        """
        snap_ss = (f"QPushButton{{background:{CARD};border:1px solid rgba(30,215,96,0.18);"
                   f"border-radius:6px;color:{TEXT_DIM};font-size:10px;padding:5px 0;}}"
                   f"QPushButton:hover{{border-color:{GREEN};color:{GREEN};}}"
                   f"QPushButton:pressed{{background:rgba(30,215,96,0.15);}}")

        # ── POSITION ──
        lay.addWidget(self._sec("POSITION"))
        lay.addWidget(self._hint("Drag the player anywhere — saves automatically.\n"
                                 "Or enter exact pixel coordinates."))
        crd = QHBoxLayout(); crd.setSpacing(12)
        for attr, lbl, key, mx in [("_sx","X  (px)","x",7680),("_sy","Y  (px)","y",4320)]:
            col = QVBoxLayout(); col.setSpacing(5); col.addWidget(self._sub(lbl))
            sb  = QSpinBox(); sb.setRange(0,mx); sb.setValue(max(0,self._cfg.get(key,0)))
            sb.valueChanged.connect(lambda v,k=key: self._cfg.update({k:v}))
            setattr(self,attr,sb); col.addWidget(sb); crd.addLayout(col)
        lay.addLayout(crd)
        lay.addWidget(self._sub("Quick snap:"))
        for row_data in [
            [("Top Left","tl"),("Top Center","tc"),("Top Right","tr")],
            [("Mid Left","ml"),("Center","mc"),    ("Mid Right","mr")],
            [("Bot Left","bl"),("Bot Center","bc"),("Bot Right","br")],
        ]:
            row = QHBoxLayout(); row.setSpacing(5)
            for lbl, k in row_data:
                b = QPushButton(lbl); b.setFixedHeight(30); b.setStyleSheet(snap_ss)
                b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                b.clicked.connect(lambda _,kk=k: self._snap(kk)); row.addWidget(b)
            lay.addLayout(row)

        # ── APPEARANCE ──
        lay.addWidget(self._sec("APPEARANCE"))
        for attr, lbl, key, lo, hi, unit in [
            ("_op","Opacity","opacity",20,100,"%"),
            ("_sc","Width",  "scale",  70,160,"%"),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            lb  = QLabel(lbl); lb.setStyleSheet(f"font-size:11px;color:{TEXT_DIM};min-width:60px;")
            sl  = QSlider(Qt.Orientation.Horizontal); sl.setRange(lo,hi)
            sl.setValue(self._cfg.get(key, 100 if key=="scale" else 94)); sl.setStyleSheet(SL)
            vl  = QLabel(f"{sl.value()}{unit}")
            vl.setStyleSheet(f"font-size:11px;color:{GREEN};min-width:36px;font-family:Consolas;")
            sl.valueChanged.connect(lambda v,k=key,vl2=vl,u=unit:
                                    (self._cfg.update({k:v}),vl2.setText(f"{v}{u}")))
            row.addWidget(lb); row.addWidget(sl,1); row.addWidget(vl)
            lay.addLayout(row)

        # ── HOTKEYS ──
        lay.addWidget(self._sec("KEYBOARD SHORTCUTS"))
        st = "active" if HAS_HK else "install pynput to enable"
        lay.addWidget(self._hint(f"Work in-game ({st}).\nFormat:  <ctrl>+<shift>+letter"))
        inp_s = (f"background:{CARD};border:1px solid rgba(30,215,96,0.18);"
                 f"border-radius:6px;color:{TEXT};font-size:11px;"
                 f"padding:7px 10px;font-family:Consolas;")
        for key, lbl in [
            ("hk_play",     "Play / Pause"),
            ("hk_next",     "Next track"),
            ("hk_prev",     "Previous track"),
            ("hk_collapse", "Collapse"),
            ("hk_settings", "Open settings"),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            lb  = QLabel(lbl); lb.setFixedWidth(112)
            lb.setStyleSheet(f"font-size:11px;color:{TEXT_DIM};")
            inp = QLineEdit(self._cfg.get(key,"")); inp.setStyleSheet(inp_s)
            inp.setEnabled(HAS_HK)
            inp.textChanged.connect(lambda v,k=key: self._cfg.update({k:v}))
            row.addWidget(lb); row.addWidget(inp,1); lay.addLayout(row)

        lay.addStretch()
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{CARD2};"); lay.addWidget(sep2)
        br = QHBoxLayout(); br.setSpacing(10)
        cancel = QPushButton("Cancel"); cancel.setObjectName("cancel")
        cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel.clicked.connect(self.close)
        apply  = QPushButton("Apply changes"); apply.setObjectName("apply")
        apply.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        apply.clicked.connect(self._apply)
        br.addWidget(cancel); br.addWidget(apply,1); lay.addLayout(br)

    def _sec(self,t):
        l=QLabel(t); l.setStyleSheet(f"font-size:9px;font-weight:700;color:{GREEN};"
                                      f"letter-spacing:2px;margin-top:4px;"); return l
    def _hint(self,t):
        l=QLabel(t); l.setWordWrap(True)
        l.setStyleSheet(f"font-size:10px;color:{TEXT_MUTED};line-height:1.6;"); return l
    def _sub(self,t):
        l=QLabel(t); l.setStyleSheet(f"font-size:10px;color:{TEXT_MUTED};"); return l

    def _snap(self, k):
        sc  = QApplication.primaryScreen().availableGeometry()
        pw  = int(BASE_W * self._cfg.get("scale",100)/100); ph = 160; pad = 16
        snaps = {
            "tl":(pad,pad), "tc":(sc.width()//2-pw//2,pad), "tr":(sc.right()-pw-pad,pad),
            "ml":(pad,sc.height()//2-ph//2), "mc":(sc.width()//2-pw//2,sc.height()//2-ph//2),
            "mr":(sc.right()-pw-pad,sc.height()//2-ph//2),
            "bl":(pad,sc.bottom()-ph-pad), "bc":(sc.width()//2-pw//2,sc.bottom()-ph-pad),
            "br":(sc.right()-pw-pad,sc.bottom()-ph-pad),
        }
        x,y = snaps[k]; self._cfg["x"]=x; self._cfg["y"]=y
        self._sx.setValue(x); self._sy.setValue(y)

    def sync_pos(self, x, y):
        self._cfg["x"]=x; self._cfg["y"]=y; self._sx.setValue(x); self._sy.setValue(y)

    def _apply(self):
        save_cfg(self._cfg); self.applied.emit(dict(self._cfg)); self.close()


# ══════════════════════════════════════════════════
#  PLAYER OVERLAY
# ══════════════════════════════════════════════════
class Player(QWidget):

    def __init__(self):
        super().__init__()
        self._cfg       = load_cfg()
        self._collapsed = False
        self._playing   = False
        self._cur       = 0
        self._dur       = 1
        self._drag      = None
        self._art_url   = None
        self._art_job   = None
        self._panel     = None
        self._poller    = None

        self._setup_win()
        self._build()
        self._apply_cfg(self._cfg, first=True)
        self._start_poll()
        self._bind_hk()

        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)

        self._vol_db = QTimer(self)
        self._vol_db.setSingleShot(True)
        self._vol_db.timeout.connect(self._send_vol)

    def _setup_win(self):
        self.setWindowTitle(APP)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _apply_cfg(self, cfg, first=False):
        self._cfg = cfg
        scale = cfg.get("scale",100)/100.0
        self._card.setFixedWidth(int(BASE_W*scale))
        self.adjustSize()
        self.setWindowOpacity(cfg.get("opacity",94)/100.0)
        x,y = cfg.get("x",-1), cfg.get("y",-1)
        if x<0 or y<0 or first:
            sc = QApplication.primaryScreen().availableGeometry()
            if x<0: x = sc.right()  - self.width()  - 16
            if y<0: y = sc.bottom() - self.height() - 16
        self.move(x,y)
        if not first: _hk.stop(); self._bind_hk()
        else: self._update_tips()

    # ── BUILD ────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(6,6,6,6)

        self._card = QWidget(self); self._card.setObjectName("card")
        self._card.setStyleSheet(f"""
            QWidget#card {{
                background: rgba(7,9,10,250);
                border: 1px solid rgba(30,215,96,0.20);
                border-radius: 13px;
            }}
        """)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30); sh.setOffset(0,6); sh.setColor(QColor(0,0,0,200))
        self._card.setGraphicsEffect(sh)
        outer.addWidget(self._card)

        lay = QVBoxLayout(self._card); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # ── TOP BAR ─────────────────────────────
        top = QWidget(); top.setFixedHeight(60)
        tl  = QHBoxLayout(top); tl.setContentsMargins(12,10,12,10); tl.setSpacing(10)

        self._art = QLabel(); self._art.setFixedSize(ART_SZ,ART_SZ)
        self._art.setStyleSheet(f"border-radius:7px;background:{CARD2};")
        self._reset_art(); tl.addWidget(self._art)

        meta = QWidget(); ml = QVBoxLayout(meta); ml.setContentsMargins(0,0,0,0); ml.setSpacing(3)
        self._title  = QLabel("Loading…")
        self._title.setStyleSheet(f"font-size:12px;font-weight:700;color:{TEXT};")
        self._artist = QLabel(APP)
        self._artist.setStyleSheet(f"font-size:10px;color:{TEXT_DIM};font-family:Consolas;")
        self._title.setMaximumWidth(165); self._artist.setMaximumWidth(165)
        ml.addWidget(self._title); ml.addWidget(self._artist); tl.addWidget(meta,1)

        self._eq = EQBars(); self._eq.setFixedSize(26,16); tl.addWidget(self._eq)

        # Collapse button — SVG chevron, no emoji
        self._col_btn = IconBtn("collapse", 26, color="#5a7a60", hover_color="#c8e0cc")
        self._col_btn.clicked.connect(self.toggle_col)
        tl.addWidget(self._col_btn)
        lay.addWidget(top)

        # ── BODY ────────────────────────────────
        self._body = QWidget()
        bl = QVBoxLayout(self._body); bl.setContentsMargins(12,4,12,12); bl.setSpacing(8)

        self._prog = ProgBar(); self._prog.seeked.connect(self._seek); bl.addWidget(self._prog)
        trow = QHBoxLayout()
        self._tc = QLabel("0:00"); self._td = QLabel("0:00")
        for l in (self._tc, self._td):
            l.setStyleSheet(f"font-size:9px;color:{TEXT_MUTED};font-family:Consolas;")
        trow.addWidget(self._tc); trow.addStretch(); trow.addWidget(self._td); bl.addLayout(trow)

        # controls row
        cr = QHBoxLayout(); cr.setSpacing(2)
        self._sh  = IconBtn("shuffle", 32, "#4a6650", "#c8e0cc")
        self._prv = IconBtn("prev",    32, "#7a9982", "#c8e0cc")
        self._ply = PlayBtn()
        self._nxt = IconBtn("next",    32, "#7a9982", "#c8e0cc")
        self._rep = IconBtn("repeat",  32, "#4a6650", "#c8e0cc")
        self._sh.clicked.connect(self._do_shuffle)
        self._prv.clicked.connect(lambda: self._cmd("previous"))
        self._ply.clicked.connect(self._do_play)
        self._nxt.clicked.connect(lambda: self._cmd("next"))
        self._rep.clicked.connect(self._do_repeat)
        cr.addStretch()
        for b in (self._sh,self._prv,self._ply,self._nxt,self._rep): cr.addWidget(b)
        cr.addStretch(); bl.addLayout(cr)

        # volume row — SVG volume icon
        vr = QHBoxLayout(); vr.setSpacing(8)
        vol_ico = QLabel(); vol_ico.setPixmap(ico("vol_lo",16,"#4a6650")); vol_ico.setFixedSize(16,16)
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0,100); self._vol.setValue(70); self._vol.setFixedHeight(16)
        self._vol.setStyleSheet(f"""
            QSlider::groove:horizontal{{height:4px;background:rgba(255,255,255,0.10);border-radius:2px;}}
            QSlider::sub-page:horizontal{{background:{GREEN};border-radius:2px;}}
            QSlider::handle:horizontal{{width:12px;height:12px;margin:-4px 0;
                background:{TEXT};border-radius:6px;}}
            QSlider::handle:horizontal:hover{{background:{GREEN};}}
        """)
        self._vol.valueChanged.connect(self._on_vol)
        self._vp = QLabel("70%")
        self._vp.setStyleSheet(f"font-size:9px;color:{TEXT_MUTED};font-family:Consolas;min-width:28px;")
        vr.addWidget(vol_ico); vr.addWidget(self._vol,1); vr.addWidget(self._vp); bl.addLayout(vr)
        lay.addWidget(self._body)

        # ── STRIP ───────────────────────────────
        strip = QWidget(); strip.setFixedHeight(34)
        strip.setStyleSheet(f"border-top:1px solid rgba(30,215,96,0.10);")
        sl = QHBoxLayout(strip); sl.setContentsMargins(10,0,10,0); sl.setSpacing(6)

        # logo
        il2 = QLabel(); il2.setPixmap(icon_pix(14)); il2.setFixedSize(14,14)
        lb2 = QLabel(APP); lb2.setStyleSheet(
            f"font-size:9px;font-weight:600;color:{TEXT_MUTED};margin-left:3px;")
        sl.addWidget(il2); sl.addWidget(lb2); sl.addStretch()

        # status
        self._status = QLabel("connecting")
        self._status.setStyleSheet(f"font-size:9px;color:{TEXT_MUTED};font-family:Consolas;")
        sl.addWidget(self._status); sl.addSpacing(8)

        # Settings button — text label, clear border
        self._set_btn = QPushButton("Settings")
        self._set_btn.setFixedHeight(24)
        self._set_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(30,215,96,0.10);
                color: {GREEN};
                border: 1px solid rgba(30,215,96,0.30);
                border-radius: 5px;
                font-size: 11px; font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(30,215,96,0.20);
                border-color: {GREEN};
            }}
            QPushButton:pressed {{ background: rgba(30,215,96,0.32); }}
        """)
        self._set_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._set_btn.clicked.connect(self.open_settings)
        sl.addWidget(self._set_btn); sl.addSpacing(6)

        # Sign Out button — red, clear border
        self._out_btn = QPushButton("Sign Out")
        self._out_btn.setFixedHeight(24)
        self._out_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(240,64,64,0.10);
                color: {DANGER};
                border: 1px solid rgba(240,64,64,0.30);
                border-radius: 5px;
                font-size: 11px; font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background: rgba(240,64,64,0.22);
                border-color: {DANGER};
            }}
            QPushButton:pressed {{ background: rgba(240,64,64,0.35); }}
        """)
        self._out_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._out_btn.clicked.connect(self._sign_out)
        sl.addWidget(self._out_btn)

        lay.addWidget(strip)
        self.adjustSize()

    def _reset_art(self):
        px = QPixmap(ART_SZ,ART_SZ); px.fill(QColor(CARD2))
        p = QPainter(px); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(
            (ART_SZ-16)//2, (ART_SZ-16)//2,
            ico("note", 16, "rgba(30,215,96,0.4)")
        )
        p.end(); self._art.setPixmap(px)

    def _is_in_drag_zone(self, pos) -> bool:
        """Only allow drag from the top bar area, not body or strip."""
        top_bar_h = 60
        return pos.y() <= top_bar_h

    # ── POLLING ──────────────────────────────────
    def _start_poll(self):
        self._poller = Poller()
        self._poller.data.connect(self._on_data)
        self._poller.start()

    def _on_data(self, d: dict):
        if d.get("idle"):
            self._title.setText("Nothing playing")
            self._artist.setText("Open Spotify on any device")
            self._status.setText("idle")
            self._playing = False; self._upd_play(); return

        self._title.setText(self._elide(d["name"],22))
        self._artist.setText(self._elide(d["artist"],26))
        self._cur = d["pos"]; self._dur = d["dur"]
        self._playing = d["playing"]
        self._upd_play(); self._upd_prog(); self._status.setText("connected")

        art = d.get("art")
        if art and art != self._art_url:
            self._art_url = art
            if self._art_job: self._art_job.terminate()
            self._art_job = ArtLoader(art)
            self._art_job.ready.connect(self._art.setPixmap)
            self._art_job.start()

    def _tick(self):
        if self._playing: self._cur += 1000; self._upd_prog()

    def _upd_prog(self):
        self._prog.set_value(min(self._cur/self._dur,1.0))
        self._tc.setText(self._ms(self._cur)); self._td.setText(self._ms(self._dur))

    def _upd_play(self):
        self._ply.set_playing(self._playing)
        self._eq.set_on(self._playing)

    # ── CONTROLS ─────────────────────────────────
    def _do_play(self):
        ep = "/pause" if self._playing else "/play"
        threading.Thread(target=sp,args=("PUT",ep),daemon=True).start()
        self._playing = not self._playing; self._upd_play()

    def _cmd(self, action):
        threading.Thread(target=sp,args=("POST",f"/{action}"),daemon=True).start()
        QTimer.singleShot(450, self._poller.poll)

    def _do_shuffle(self):
        on = not self._sh._on
        self._sh.set_toggle(on)
        threading.Thread(target=sp,
            args=("PUT",f"/shuffle?state={str(on).lower()}"),daemon=True).start()

    def _do_repeat(self):
        on = not self._rep._on
        self._rep.set_toggle(on)
        threading.Thread(target=sp,
            args=("PUT",f"/repeat?state={'context' if on else 'off'}"),daemon=True).start()

    def _on_vol(self,v):
        self._vp.setText(f"{v}%"); self._vol_db.start(260)

    def _send_vol(self):
        threading.Thread(target=sp,
            args=("PUT",f"/volume?volume_percent={self._vol.value()}"),daemon=True).start()

    def _seek(self,pct):
        pos=int(pct*self._dur); self._cur=pos; self._upd_prog()
        threading.Thread(target=sp,args=("PUT",f"/seek?position_ms={pos}"),daemon=True).start()

    # ── COLLAPSE ─────────────────────────────────
    def toggle_col(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        # switch chevron direction
        self._col_btn.set_icon("expand" if self._collapsed else "collapse")
        ox,oy = self.x(), self.y()
        self.adjustSize(); self.move(ox,oy)
        s=dict(self._cfg); s["x"]=ox; s["y"]=oy; save_cfg(s)

    # ── SETTINGS ─────────────────────────────────
    def open_settings(self):
        # Guard: never open twice
        if self._panel is not None:
            try:
                if self._panel.isVisible():
                    self._panel.raise_()
                    self._panel.activateWindow()
                    return
            except RuntimeError:
                self._panel = None  # C++ object deleted

        s = dict(self._cfg); s["x"] = self.x(); s["y"] = self.y()
        self._panel = SettingsPanel(s)
        self._panel.applied.connect(self._apply_cfg)
        self._panel.finished_signal = None  # just in case
        # Clear ref when window closes
        def _on_close():
            self._panel = None
        self._panel.destroyed.connect(lambda _=None: _on_close())
        sc = QApplication.primaryScreen().availableGeometry()
        px = self.x()-368 if self.x()>368 else self.x()+self.width()+8
        py = max(sc.top(), min(self.y(), sc.bottom()-700))
        self._panel.move(px, py)
        self._panel.show()

    # ── SIGN OUT ─────────────────────────────────
    def _sign_out(self):
        if self._poller: self._poller.stop()
        _hk.stop(); _tok.revoke(); self.close(); _do_setup()

    # ── HOTKEYS ──────────────────────────────────
    def _bind_hk(self):
        s=self._cfg
        _hk.register(s.get("hk_play",    "<ctrl>+<shift>+p"), self._do_play)
        _hk.register(s.get("hk_next",    "<ctrl>+<shift>+n"), lambda: self._cmd("next"))
        _hk.register(s.get("hk_prev",    "<ctrl>+<shift>+b"), lambda: self._cmd("previous"))
        _hk.register(s.get("hk_collapse","<ctrl>+<shift>+m"), self.toggle_col)
        _hk.register(s.get("hk_settings","<ctrl>+<shift>+s"), self.open_settings)
        _hk.start(); self._update_tips()

    def _update_tips(self):
        s=self._cfg
        def f(k,d):
            return (s.get(k,d).replace("<ctrl>","Ctrl")
                               .replace("<shift>","Shift")
                               .replace("<alt>","Alt").upper())
        pp=f("hk_play","<ctrl>+<shift>+p"); nxt=f("hk_next","<ctrl>+<shift>+n")
        prv=f("hk_prev","<ctrl>+<shift>+b"); col=f("hk_collapse","<ctrl>+<shift>+m")
        stg=f("hk_settings","<ctrl>+<shift>+s"); ok="active" if HAS_HK else "pynput not installed"
        self._ply.setToolTip(f"Play / Pause  [{pp}]")
        self._nxt.setToolTip(f"Next  [{nxt}]")
        self._prv.setToolTip(f"Previous  [{prv}]")
        self._col_btn.setToolTip(f"Collapse / Expand  [{col}]")
        self._set_btn.setToolTip(
            f"Settings  [{stg}]\n─────────────────────\nHotkeys ({ok}):\n"
            f"  Play/Pause  {pp}\n  Next        {nxt}\n  Previous    {prv}\n"
            f"  Collapse    {col}\n  Settings    {stg}")

    # ── DRAG — only from top bar area ────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Only drag from the top-bar zone (first 60px of card)
            local = self._card.mapFrom(self, e.position().toPoint())
            if self._is_in_drag_zone(local):
                # But not if clicking the collapse button
                w = self.childAt(e.position().toPoint())
                if not isinstance(w, (QPushButton, IconBtn, PlayBtn)):
                    self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._drag:
            self._drag = None
            s = dict(self._cfg); s["x"] = self.x(); s["y"] = self.y()
            self._cfg = s; save_cfg(s)
            if self._panel is not None:
                try:
                    if self._panel.isVisible():
                        self._panel.sync_pos(self.x(), self.y())
                except RuntimeError:
                    self._panel = None

    @staticmethod
    def _ms(ms): s=int(ms/1000); return f"{s//60}:{s%60:02d}"
    @staticmethod
    def _elide(t,n): return t if len(t)<=n else t[:n-1]+"…"


# ══════════════════════════════════════════════════
#  APP ENTRY
# ══════════════════════════════════════════════════
_app = _splash = _setup = _player = None

def _do_setup():
    global _setup
    _setup = SetupWindow(); _setup.logged_in.connect(_on_login); _setup.show()

def _on_login():
    global _player
    if _setup: _setup.close()
    _player = Player(); _player.show()

def _after_splash():
    global _player
    if _tok.ok: _player = Player(); _player.show()
    else: _do_setup()

def main():
    global _app, _splash
    _app = QApplication(sys.argv)
    _app.setApplicationName(APP)
    _app.setWindowIcon(app_icon())
    _app.setQuitOnLastWindowClosed(False)
    _splash = Splash()
    _splash.done.connect(_after_splash)
    _splash.show()
    sys.exit(_app.exec())

if __name__ == "__main__":
    main()
