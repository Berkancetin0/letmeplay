"""
Spotify Mini Player — Windows Overlay
Oyunun üzerinde duran, küçültülebilir müzik kontrolü.
"""

import sys
import json
import time
import base64
import random
import threading
import webbrowser
import urllib.parse
import http.server
from pathlib import Path

import requests
try:
    from pynput import keyboard as pynput_kb
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QSlider,
    QHBoxLayout, QVBoxLayout, QLineEdit, QFrame,
    QGraphicsDropShadowEffect, QSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPainterPath,
    QBrush, QPen, QIcon, QCursor, QFont
)

# ─────────────────────────────────────────────
#  CONFIG / PERSISTENCE
# ─────────────────────────────────────────────
CLIENT_ID     = "SENIN_CLIENT_ID"
CLIENT_SECRET = "SENIN_CLIENT_SECRET"
REDIRECT_URI  = "http://localhost:8888/callback"
SCOPES        = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
PORT          = 8888
CONFIG_FILE   = Path.home() / ".spotify_mini_player.json"
SETTINGS_FILE = Path.home() / ".spotify_mini_player_settings.json"

DEFAULT_SETTINGS = {
    "x":       -1,   # -1 = ilk açılış, sağ alta koy
    "y":       -1,
    "opacity": 90,   # %
    "scale":   100,  # genişlik % (70–160)
    # Kısayollar (pynput formatı)
    "hk_settings":  "<ctrl>+<shift>+s",   # Ayar paneli aç/kapat
    "hk_collapse":  "<ctrl>+<shift>+m",   # Küçült / Büyüt
    "hk_playpause": "<ctrl>+<shift>+p",   # Oynat / Duraklat
    "hk_next":      "<ctrl>+<shift>+n",   # Sonraki şarkı
    "hk_prev":      "<ctrl>+<shift>+b",   # Önceki şarkı
}

def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            d = json.loads(SETTINGS_FILE.read_text())
            return {**DEFAULT_SETTINGS, **d}
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)

def save_settings(d: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(d))
    except Exception:
        pass


# ─────────────────────────────────────────────
#  TOKEN MANAGER
# ─────────────────────────────────────────────
class TokenManager:
    def __init__(self):
        self.access_token  = None
        self.refresh_token = None
        self.expiry        = 0
        self._load()

    def _load(self):
        try:
            if CONFIG_FILE.exists():
                d = json.loads(CONFIG_FILE.read_text())
                self.refresh_token = d.get("refresh_token")
                self.access_token  = d.get("access_token")
                self.expiry        = d.get("expiry", 0)
        except Exception:
            pass

    def _save(self):
        try:
            CONFIG_FILE.write_text(json.dumps({
                "access_token":  self.access_token,
                "refresh_token": self.refresh_token,
                "expiry":        self.expiry,
            }))
        except Exception:
            pass

    def get_token(self):
        if time.time() > self.expiry - 60 and self.refresh_token:
            self._refresh()
        return self.access_token

    def _refresh(self):
        try:
            creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
            r = requests.post("https://accounts.spotify.com/api/token", data={
                "grant_type":    "refresh_token",
                "refresh_token": self.refresh_token,
            }, headers={"Authorization": f"Basic {creds}"}, timeout=5)
            if r.ok:
                d = r.json()
                self.access_token = d["access_token"]
                self.expiry = time.time() + d["expires_in"]
                self._save()
        except Exception:
            pass

    def exchange(self, code):
        creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        r = requests.post("https://accounts.spotify.com/api/token", data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        }, headers={"Authorization": f"Basic {creds}"}, timeout=5)
        if r.ok:
            d = r.json()
            self.access_token  = d["access_token"]
            self.refresh_token = d.get("refresh_token", "")
            self.expiry        = time.time() + d["expires_in"]
            self._save()
            return True
        return False

    def revoke(self):
        self.access_token = self.refresh_token = None
        self.expiry = 0
        CONFIG_FILE.unlink(missing_ok=True)

    @property
    def has_token(self):
        return bool(self.refresh_token or self.access_token)


token_mgr = TokenManager()


# ─────────────────────────────────────────────
#  OAUTH CALLBACK SERVER
# ─────────────────────────────────────────────
auth_code_received = threading.Event()
received_code      = [None]

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p    = urllib.parse.urlparse(self.path)
        q    = urllib.parse.parse_qs(p.query)
        code = q.get("code", [None])[0]
        if code:
            received_code[0] = code
            html = b"<html><body style='background:#080b0f;color:#1ed760;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;font-size:18px;'><p>&#10003; Giri&#351; ba&#351;ar&#305;l&#305;! Bu pencereyi kapatabilirsin.</p></body></html>"
        else:
            html = b"<html><body>Hata: izin reddedildi.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html)
        auth_code_received.set()

def start_oauth_server():
    server = http.server.HTTPServer(("localhost", PORT), OAuthHandler)
    server.timeout = 120
    server.handle_request()


# ─────────────────────────────────────────────
#  SPOTIFY POLLER
# ─────────────────────────────────────────────
class SpotifyPoller(QThread):
    track_updated = pyqtSignal(dict)
    error         = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        while self._running:
            self._poll()
            time.sleep(5)

    def _poll(self):
        tok = token_mgr.get_token()
        if not tok:
            return
        try:
            r = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=4,
            )
            if r.status_code == 204:
                self.track_updated.emit({"nothing": True})
                return
            if not r.ok:
                self.error.emit(f"API hatası: {r.status_code}")
                return
            d    = r.json()
            item = d.get("item") or {}
            imgs = item.get("album", {}).get("images", [])
            self.track_updated.emit({
                "name":        item.get("name", ""),
                "artist":      ", ".join(a["name"] for a in item.get("artists", [])),
                "art_url":     imgs[-1]["url"] if imgs else None,
                "progress_ms": d.get("progress_ms", 0),
                "duration_ms": item.get("duration_ms", 1),
                "is_playing":  d.get("is_playing", False),
            })
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._running = False


def spotify_cmd(method, path, body=None):
    tok = token_mgr.get_token()
    if not tok:
        return
    try:
        requests.request(
            method,
            f"https://api.spotify.com/v1/me/player{path}",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=body,
            timeout=4,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
#  ALBUM ART LOADER
# ─────────────────────────────────────────────
class ArtLoader(QThread):
    loaded = pyqtSignal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            r   = requests.get(self.url, timeout=4)
            img = QImage()
            img.loadFromData(r.content)
            pix = QPixmap.fromImage(img).scaled(
                34, 34,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            rounded = QPixmap(34, 34)
            rounded.fill(Qt.GlobalColor.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 34, 34, 5, 5)
            p.setClipPath(path)
            p.drawPixmap(0, 0, pix)
            p.end()
            self.loaded.emit(rounded)
        except Exception:
            pass


# ─────────────────────────────────────────────
#  CUSTOM WIDGETS
# ─────────────────────────────────────────────
class ProgressBar(QWidget):
    seeked = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self._value = 0.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def set_value(self, v):
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QBrush(QColor(255, 255, 255, 20)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, 2, 2)
        fw = int(w * self._value)
        if fw > 0:
            p.setBrush(QBrush(QColor("#1ed760")))
            p.drawRoundedRect(0, 0, fw, h, 2, 2)
        p.end()

    def mousePressEvent(self, e):
        pct = e.position().x() / self.width()
        self.seeked.emit(max(0.0, min(1.0, pct)))


class EQWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._playing = False
        self._heights = [0.3, 0.7, 0.5, 0.9]
        self._dirs    = [1, -1, 1, -1]
        t = QTimer(self)
        t.timeout.connect(self._animate)
        t.start(120)

    def set_playing(self, v):
        self._playing = v

    def _animate(self):
        if self._playing:
            self._heights = [
                max(0.15, min(1.0, h + self._dirs[i] * random.uniform(0.05, 0.2)))
                for i, h in enumerate(self._heights)
            ]
            self._dirs = [
                1 if h <= 0.15 else (-1 if h >= 1.0 else d)
                for h, d in zip(self._heights, self._dirs)
            ]
        else:
            self._heights = [0.2] * 4
        self.update()

    def paintEvent(self, _):
        p     = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h  = self.width(), self.height()
        bar_w = 2; gap = 2
        x_off = (w - (4 * bar_w + 3 * gap)) // 2
        color = QColor("#1ed760") if self._playing else QColor(80, 80, 80)
        p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
        for i, fh in enumerate(self._heights):
            bh = max(2, int(h * fh))
            p.drawRoundedRect(x_off + i * (bar_w + gap), h - bh, bar_w, bh, 1, 1)
        p.end()



# ─────────────────────────────────────────────
#  GLOBAL HOTKEY MANAGER
#  pynput ile oyun içinde bile çalışır
# ─────────────────────────────────────────────
class GlobalHotkeyManager:
    """
    Oyun odaklanmış olsa bile sistem seviyesinde kısayol dinler.
    Callbacks Qt sinyalleri yerine doğrudan çağrılır ama
    QTimer.singleShot ile ana thread'e yönlendirilir.
    """
    def __init__(self):
        self._callbacks: dict[str, callable] = {}
        self._pressed:   set = set()
        self._listener  = None
        self._combos:    dict[frozenset, str] = {}  # frozenset(keys) → action

    def register(self, action: str, hotkey_str: str, callback: callable):
        """
        hotkey_str: "<ctrl>+<shift>+s" formatı
        action:     benzersiz isim
        """
        if not HAS_PYNPUT:
            return
        keys = self._parse(hotkey_str)
        if keys:
            self._combos[frozenset(keys)] = action
            self._callbacks[action] = callback

    def _parse(self, s: str) -> list:
        """'<ctrl>+<shift>+s' → [Key.ctrl, Key.shift, KeyCode('s')]"""
        if not HAS_PYNPUT:
            return []
        parts = [p.strip() for p in s.lower().split("+")]
        result = []
        key_map = {
            "<ctrl>":  pynput_kb.Key.ctrl,
            "<shift>": pynput_kb.Key.shift,
            "<alt>":   pynput_kb.Key.alt,
            "<cmd>":   pynput_kb.Key.cmd,
        }
        for p in parts:
            if p in key_map:
                result.append(key_map[p])
            elif len(p) == 1:
                result.append(pynput_kb.KeyCode.from_char(p))
            else:
                try:
                    result.append(pynput_kb.Key[p.strip("<>")])
                except Exception:
                    pass
        return result

    def start(self):
        if not HAS_PYNPUT or self._listener:
            return
        def on_press(key):
            self._pressed.add(self._norm(key))
            self._check()
        def on_release(key):
            self._pressed.discard(self._norm(key))
        self._listener = pynput_kb.Listener(on_press=on_press, on_release=on_release,
                                             suppress=False)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _norm(self, key):
        # ctrl_l / ctrl_r → ctrl gibi normalize et
        if not HAS_PYNPUT:
            return key
        aliases = {
            pynput_kb.Key.ctrl_l:  pynput_kb.Key.ctrl,
            pynput_kb.Key.ctrl_r:  pynput_kb.Key.ctrl,
            pynput_kb.Key.shift_l: pynput_kb.Key.shift,
            pynput_kb.Key.shift_r: pynput_kb.Key.shift,
            pynput_kb.Key.alt_l:   pynput_kb.Key.alt,
            pynput_kb.Key.alt_r:   pynput_kb.Key.alt,
        }
        return aliases.get(key, key)

    def _check(self):
        for combo, action in self._combos.items():
            if combo.issubset(self._pressed):
                cb = self._callbacks.get(action)
                if cb:
                    # Ana Qt thread'ine yönlendir
                    QTimer.singleShot(0, cb)

hotkey_mgr = GlobalHotkeyManager()


# ─────────────────────────────────────────────
#  SETUP WINDOW
# ─────────────────────────────────────────────
class SetupWindow(QWidget):
    login_success = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Mini Player — Giriş")
        self.setFixedSize(380, 420)
        self.setStyleSheet("QWidget{background:#080b0f;color:#f0f2f5;font-family:'Segoe UI';} QLabel{background:transparent;}")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(14)

        # Logo
        logo = QHBoxLayout()
        dot  = QLabel()
        pm   = QPixmap(28, 28); pm.fill(Qt.GlobalColor.transparent)
        pp   = QPainter(pm); pp.setRenderHint(QPainter.RenderHint.Antialiasing)
        pp.setBrush(QBrush(QColor("#1ed760"))); pp.setPen(Qt.PenStyle.NoPen)
        pp.drawEllipse(0, 0, 28, 28); pp.end()
        dot.setPixmap(pm); logo.addWidget(dot)
        col = QVBoxLayout(); col.setSpacing(1)
        t1  = QLabel("Spotify Mini Player"); t1.setStyleSheet("font-size:14px;font-weight:700;")
        t2  = QLabel("for gamers · windows overlay"); t2.setStyleSheet("font-size:9px;color:#556;letter-spacing:1px;")
        col.addWidget(t1); col.addWidget(t2)
        logo.addLayout(col); logo.addStretch()
        lay.addLayout(logo)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine); div.setStyleSheet("color:#1a1f28;")
        lay.addWidget(div)

        # Steps box
        box = QFrame()
        box.setStyleSheet("background:#0f1318;border-radius:10px;border:1px solid #1a1f28;")
        bl  = QVBoxLayout(box); bl.setContentsMargins(14, 12, 14, 12); bl.setSpacing(8)
        hl  = QLabel("NASIL GİRİŞ YAPILIR"); hl.setStyleSheet("font-size:8px;color:#1ed760;letter-spacing:2px;font-weight:600;")
        bl.addWidget(hl)
        for num, txt in [
            ("1", "developer.spotify.com/dashboard → Create App"),
            ("2", "Redirect URI: http://localhost:8888/callback"),
            ("3", "Client ID & Secret'ı aşağıya gir"),
            ("4", "Giriş Yap → tarayıcıda izin ver → hazır!"),
        ]:
            row = QHBoxLayout(); row.setSpacing(8)
            n   = QLabel(num); n.setFixedSize(18, 18); n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet("background:#1a2d1a;color:#1ed760;border-radius:9px;font-size:9px;font-weight:600;")
            t   = QLabel(txt); t.setStyleSheet("font-size:10px;color:#8899aa;"); t.setWordWrap(True)
            row.addWidget(n); row.addWidget(t, 1); bl.addLayout(row)
        lay.addWidget(box)

        input_style = """
            QLineEdit{background:#0f1318;border:1px solid #1a1f28;border-radius:7px;
                color:#f0f2f5;font-size:11px;padding:8px 10px;font-family:'Consolas','Courier New',monospace;}
            QLineEdit:focus{border:1px solid rgba(30,215,96,0.4);}
        """
        for attr, lbl_txt, ph, pw in [
            ("inp_id",  "Client ID",     "Spotify Client ID",     False),
            ("inp_sec", "Client Secret", "Spotify Client Secret", True),
        ]:
            l = QLabel(lbl_txt); l.setStyleSheet("font-size:10px;color:#556;"); lay.addWidget(l)
            w = QLineEdit(); w.setPlaceholderText(ph); w.setStyleSheet(input_style)
            if pw: w.setEchoMode(QLineEdit.EchoMode.Password)
            if attr == "inp_id"  and CLIENT_ID     != "SENIN_CLIENT_ID":     w.setText(CLIENT_ID)
            if attr == "inp_sec" and CLIENT_SECRET != "SENIN_CLIENT_SECRET": w.setText(CLIENT_SECRET)
            setattr(self, attr, w); lay.addWidget(w)

        self.err = QLabel(""); self.err.setStyleSheet("font-size:10px;color:#e05858;min-height:14px;")
        lay.addWidget(self.err)

        btn = QPushButton("  Spotify ile Giriş Yap  →")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet("""
            QPushButton{background:#1ed760;color:#000;border:none;border-radius:8px;
                font-size:12px;font-weight:700;padding:11px 0;letter-spacing:0.5px;}
            QPushButton:hover{background:#2af074;} QPushButton:pressed{background:#17b84e;}
        """)
        btn.clicked.connect(self._login); self.btn = btn; lay.addWidget(btn)

    def _login(self):
        cid = self.inp_id.text().strip(); sec = self.inp_sec.text().strip()
        if not cid or not sec: self.err.setText("Client ID ve Secret boş olamaz."); return
        global CLIENT_ID, CLIENT_SECRET
        CLIENT_ID = cid; CLIENT_SECRET = sec
        self.err.setText(""); self.btn.setText("Tarayıcı açılıyor..."); self.btn.setEnabled(False)
        threading.Thread(target=self._oauth, daemon=True).start()

    def _oauth(self):
        auth_code_received.clear(); received_code[0] = None
        threading.Thread(target=start_oauth_server, daemon=True).start()
        url = ("https://accounts.spotify.com/authorize?" +
               urllib.parse.urlencode({"client_id": CLIENT_ID, "response_type": "code",
                                       "redirect_uri": REDIRECT_URI, "scope": SCOPES}))
        webbrowser.open(url)
        auth_code_received.wait(timeout=120)
        code = received_code[0]
        if code and token_mgr.exchange(code):
            self.login_success.emit()
        else:
            self.err.setText("Giriş başarısız. Tekrar dene.")
            self.btn.setText("  Spotify ile Giriş Yap  →"); self.btn.setEnabled(True)


# ─────────────────────────────────────────────
#  SETTINGS PANEL
# ─────────────────────────────────────────────
class SettingsPanel(QWidget):
    applied = pyqtSignal(dict)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Player Ayarları")
        self.setFixedSize(340, 680)
        self.setStyleSheet("QWidget{background:#080b0f;color:#f0f2f5;font-family:'Segoe UI';} QLabel{background:transparent;}")
        self._s = dict(settings)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(14)

        t = QLabel("⊹  Player Ayarları"); t.setStyleSheet("font-size:14px;font-weight:700;")
        lay.addWidget(t)

        # ── KONUM ──
        lay.addWidget(self._sec("KONUM"))
        lay.addWidget(self._hint(
            "Player'ı sürükleyip bırak — konum otomatik kaydedilir. "
            "Veya aşağıya piksel koordinatı girerek tam yer belirle."
        ))

        cr = QHBoxLayout(); cr.setSpacing(10)
        for label, key, maxv in [("X  (piksel)", "x", 7680), ("Y  (piksel)", "y", 4320)]:
            col = QVBoxLayout(); col.setSpacing(4)
            lbl = QLabel(label); lbl.setStyleSheet("font-size:9px;color:#556;letter-spacing:1px;")
            sb  = QSpinBox(); sb.setRange(0, maxv); sb.setValue(max(0, self._s.get(key, 0)))
            sb.setStyleSheet("""
                QSpinBox{background:#0f1318;border:1px solid #1a1f28;border-radius:6px;
                    color:#f0f2f5;font-size:11px;padding:6px 8px;font-family:'Consolas';}
                QSpinBox:focus{border-color:rgba(30,215,96,0.4);}
                QSpinBox::up-button,QSpinBox::down-button{width:18px;background:#161b22;border:none;}
            """)
            sb.valueChanged.connect(lambda v, k=key: self._s.update({k: v}))
            setattr(self, f"sb_{key}", sb)
            col.addWidget(lbl); col.addWidget(sb); cr.addLayout(col)
        lay.addLayout(cr)

        # Snap grid
        lay.addWidget(self._hint("Hızlı yerleştir — ekranın köşelerine / kenarlarına snap:"))
        snap_rows = [
            [("↖ Sol Üst","tl"), ("↑ Üst Orta","tc"), ("↗ Sağ Üst","tr")],
            [("← Sol Orta","ml"),("⊙ Merkez","mc"),   ("→ Sağ Orta","mr")],
            [("↙ Sol Alt","bl"), ("↓ Alt Orta","bc"),  ("↘ Sağ Alt","br")],
        ]
        for row_items in snap_rows:
            row = QHBoxLayout(); row.setSpacing(5)
            for label, key in row_items:
                b = QPushButton(label); b.setFixedHeight(28)
                b.setStyleSheet("""
                    QPushButton{background:#0f1318;border:1px solid #1a1f28;border-radius:5px;
                        color:#8899aa;font-size:9px;}
                    QPushButton:hover{border-color:rgba(30,215,96,0.4);color:#1ed760;}
                    QPushButton:pressed{background:#1a2d1a;}
                """)
                b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                b.clicked.connect(lambda _, k=key: self._snap(k))
                row.addWidget(b)
            lay.addLayout(row)

        # ── GÖRÜNÜM ──
        lay.addWidget(self._sec("GÖRÜNÜM"))

        sl_style = """
            QSlider::groove:horizontal{height:3px;background:rgba(255,255,255,0.08);border-radius:2px;}
            QSlider::sub-page:horizontal{background:#1ed760;border-radius:2px;}
            QSlider::handle:horizontal{width:12px;height:12px;margin:-5px 0;background:#fff;border-radius:6px;}
            QSlider::handle:horizontal:hover{background:#1ed760;}
        """
        for attr, label, key, lo, hi, unit in [
            ("_op",  "Opaklık",  "opacity", 20, 100, "%"),
            ("_sc",  "Genişlik", "scale",   70, 160, "%"),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            lbl = QLabel(label); lbl.setStyleSheet("font-size:10px;color:#8899aa;min-width:62px;")
            sl  = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi); sl.setValue(self._s.get(key, 100 if key=="scale" else 90))
            sl.setStyleSheet(sl_style)
            val_lbl = QLabel(f"{sl.value()}{unit}")
            val_lbl.setStyleSheet("font-size:10px;color:#1ed760;min-width:36px;font-family:'Consolas';")
            sl.valueChanged.connect(lambda v, k=key, vl=val_lbl, u=unit:
                                    (self._s.update({k: v}), vl.setText(f"{v}{u}")))
            setattr(self, f"{attr}_sl", sl); setattr(self, f"{attr}_val", val_lbl)
            row.addWidget(lbl); row.addWidget(sl, 1); row.addWidget(val_lbl)
            lay.addLayout(row)

        lay.addStretch()

        # ── KISAYOLLAR ──
        lay.addWidget(self._sec("KLAVYE KISAYOLLARI"))
        if not HAS_PYNPUT:
            lay.addWidget(self._hint(
                "⚠ pynput kurulu değil. Kısayolları etkinleştirmek için:\n"
                "pip install pynput"
            ))
        else:
            lay.addWidget(self._hint(
                "Oyun içinde çalışır. Format: <ctrl>+<shift>+harf"
            ))

        hk_style = """
            QLineEdit{background:#0f1318;border:1px solid #1a1f28;border-radius:5px;
                color:#f0f2f5;font-size:10px;padding:5px 8px;font-family:'Consolas';}
            QLineEdit:focus{border-color:rgba(30,215,96,0.4);}
        """
        hk_fields = [
            ("hk_settings",  "Ayar paneli"),
            ("hk_collapse",  "Küçült/Büyüt"),
            ("hk_playpause", "Oynat/Duraklat"),
            ("hk_next",      "Sonraki şarkı"),
            ("hk_prev",      "Önceki şarkı"),
        ]
        for key, label in hk_fields:
            row = QHBoxLayout(); row.setSpacing(8)
            lbl = QLabel(label); lbl.setFixedWidth(90)
            lbl.setStyleSheet("font-size:9px;color:#8899aa;")
            inp = QLineEdit(self._s.get(key, ""))
            inp.setStyleSheet(hk_style)
            inp.setEnabled(HAS_PYNPUT)
            inp.textChanged.connect(lambda v, k=key: self._s.update({k: v}))
            setattr(self, f"hk_{key}", inp)
            row.addWidget(lbl); row.addWidget(inp, 1)
            lay.addLayout(row)

        lay.addStretch()
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        cancel  = QPushButton("İptal")
        cancel.setStyleSheet("""
            QPushButton{background:transparent;border:1px solid #1a1f28;border-radius:7px;
                color:#8899aa;font-size:11px;padding:9px 0;}
            QPushButton:hover{border-color:rgba(255,255,255,0.2);color:#f0f2f5;}
        """)
        cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel.clicked.connect(self.close)

        apply_btn = QPushButton("Uygula")
        apply_btn.setStyleSheet("""
            QPushButton{background:#1ed760;color:#000;border:none;border-radius:7px;
                font-size:11px;font-weight:700;padding:9px 0;}
            QPushButton:hover{background:#2af074;} QPushButton:pressed{background:#17b84e;}
        """)
        apply_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(cancel); btn_row.addWidget(apply_btn)
        lay.addLayout(btn_row)

    def _sec(self, text):
        l = QLabel(text); l.setStyleSheet("font-size:8px;font-weight:600;color:#1ed760;letter-spacing:2px;"); return l

    def _hint(self, text):
        l = QLabel(text); l.setWordWrap(True)
        l.setStyleSheet("font-size:9.5px;color:rgba(240,242,245,0.35);line-height:1.5;"); return l

    def _snap(self, key: str):
        screen = QApplication.primaryScreen().availableGeometry()
        pw  = int(280 * self._s.get("scale", 100) / 100)
        ph  = 130
        pad = 16
        snaps = {
            "tl": (pad,                              pad),
            "tc": (screen.width()//2 - pw//2,        pad),
            "tr": (screen.right()  - pw - pad,       pad),
            "ml": (pad,                              screen.height()//2 - ph//2),
            "mc": (screen.width()//2 - pw//2,        screen.height()//2 - ph//2),
            "mr": (screen.right()  - pw - pad,       screen.height()//2 - ph//2),
            "bl": (pad,                              screen.bottom() - ph - pad),
            "bc": (screen.width()//2 - pw//2,        screen.bottom() - ph - pad),
            "br": (screen.right()  - pw - pad,       screen.bottom() - ph - pad),
        }
        x, y = snaps[key]
        self._s["x"] = x; self._s["y"] = y
        self.sb_x.setValue(x); self.sb_y.setValue(y)

    def update_pos(self, x: int, y: int):
        """Player sürüklenince çağrılır — spinbox'ları günceller."""
        self._s["x"] = x; self._s["y"] = y
        self.sb_x.setValue(x); self.sb_y.setValue(y)

    def _apply(self):
        save_settings(self._s)
        self.applied.emit(dict(self._s))
        self.close()


# ─────────────────────────────────────────────
#  MAIN PLAYER OVERLAY
# ─────────────────────────────────────────────
BASE_WIDTH = 280

class PlayerOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.collapsed   = False
        self.is_playing  = False
        self.cur_ms      = 0
        self.dur_ms      = 1
        self._drag_pos   = None
        self._art_loader = None
        self._poller     = None
        self._last_art   = None
        self._settings   = load_settings()
        self._panel      = None

        self._setup_window()
        self._build_ui()
        self._apply_settings(self._settings, initial=True)
        self._start_poller()
        self._register_hotkeys()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(1000)

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _apply_settings(self, s: dict, initial=False):
        self._settings = s
        # Genişlik
        scale = s.get("scale", 100) / 100.0
        self._main.setFixedWidth(int(BASE_WIDTH * scale))
        self.adjustSize()
        # Opaklık
        self.setWindowOpacity(s.get("opacity", 90) / 100.0)
        # Konum
        x, y = s.get("x", -1), s.get("y", -1)
        if x < 0 or y < 0 or initial:
            screen = QApplication.primaryScreen().availableGeometry()
            if x < 0: x = screen.right()  - self.width()  - 16
            if y < 0: y = screen.bottom() - self.height() - 16
        self.move(x, y)
        # Kısayolları yeniden kaydet
        if not initial:
            hotkey_mgr.stop()
            self._register_hotkeys()
        else:
            self._update_tooltips()

    # ── BUILD UI ──
    def _build_ui(self):
        self._main = QWidget(self)
        self._main.setObjectName("main")
        self._main.setStyleSheet("""
            QWidget#main{background:rgba(8,11,15,242);
                border:1px solid rgba(255,255,255,18);border-radius:13px;}
        """)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30); sh.setOffset(0, 6); sh.setColor(QColor(0, 0, 0, 180))
        self._main.setGraphicsEffect(sh)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._main)

        self._lay = QVBoxLayout(self._main)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # ── TOP BAR ──
        top = QWidget(); top.setFixedHeight(52)
        tl  = QHBoxLayout(top); tl.setContentsMargins(10, 9, 10, 9); tl.setSpacing(8)

        self._art_lbl = QLabel(); self._art_lbl.setFixedSize(34, 34)
        self._art_lbl.setStyleSheet("border-radius:5px;background:#1c2028;")
        self._set_placeholder_art(); tl.addWidget(self._art_lbl)

        info = QWidget(); il = QVBoxLayout(info); il.setContentsMargins(0,0,0,0); il.setSpacing(1)
        self._name_lbl   = QLabel("Yükleniyor...")
        self._artist_lbl = QLabel("Spotify")
        self._name_lbl.setStyleSheet("font-size:11px;font-weight:600;color:#f0f2f5;")
        self._artist_lbl.setStyleSheet("font-size:9px;color:rgba(240,242,245,0.45);font-family:'Consolas';")
        self._name_lbl.setMaximumWidth(155); self._artist_lbl.setMaximumWidth(155)
        il.addWidget(self._name_lbl); il.addWidget(self._artist_lbl)
        tl.addWidget(info, 1)

        self._eq_w = EQWidget(); self._eq_w.setFixedSize(22, 16)
        tl.addWidget(self._eq_w)

        self._col_btn = QPushButton("▾"); self._col_btn.setFixedSize(22, 22)
        self._col_btn.setStyleSheet("""
            QPushButton{background:#161b22;color:rgba(240,242,245,0.45);
                border:1px solid rgba(255,255,255,0.07);border-radius:11px;font-size:10px;}
            QPushButton:hover{background:rgba(30,215,96,0.15);color:#1ed760;
                border-color:rgba(30,215,96,0.3);}
        """)
        self._col_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._col_btn.clicked.connect(self._toggle_collapse)
        tl.addWidget(self._col_btn)
        self._lay.addWidget(top)

        # ── BODY ──
        self._body = QWidget()
        bl = QVBoxLayout(self._body); bl.setContentsMargins(10, 2, 10, 10); bl.setSpacing(6)

        self._prog = ProgressBar(); self._prog.setFixedHeight(3)
        self._prog.seeked.connect(self._on_seek); bl.addWidget(self._prog)
        tr = QHBoxLayout()
        self._t_cur = QLabel("0:00"); self._t_tot = QLabel("0:00")
        for l in (self._t_cur, self._t_tot):
            l.setStyleSheet("font-size:8px;color:rgba(240,242,245,0.2);font-family:'Consolas';")
        tr.addWidget(self._t_cur); tr.addStretch(); tr.addWidget(self._t_tot)
        bl.addLayout(tr)

        cr = QHBoxLayout(); cr.setSpacing(0)
        self._sh_btn   = self._mk_ctrl("⇄", 28, toggle=True)
        self._prev_btn = self._mk_ctrl("⏮", 28)
        self._play_btn = self._mk_ctrl("▶", 34, is_play=True)
        self._next_btn = self._mk_ctrl("⏭", 28)
        self._rep_btn  = self._mk_ctrl("↻", 28, toggle=True)
        self._sh_btn.setToolTip("Karıştır")
        self._prev_btn.setToolTip("Önceki şarkı")
        self._play_btn.setToolTip("Oynat / Duraklat")
        self._next_btn.setToolTip("Sonraki şarkı")
        self._rep_btn.setToolTip("Tekrar")
        self._sh_btn.clicked.connect(self._do_shuffle)
        self._prev_btn.clicked.connect(lambda: self._do_cmd("previous"))
        self._play_btn.clicked.connect(self._do_play)
        self._next_btn.clicked.connect(lambda: self._do_cmd("next"))
        self._rep_btn.clicked.connect(self._do_repeat)
        cr.addStretch()
        for b in (self._sh_btn, self._prev_btn, self._play_btn, self._next_btn, self._rep_btn):
            cr.addWidget(b)
        cr.addStretch(); bl.addLayout(cr)

        vr = QHBoxLayout(); vr.setSpacing(6)
        vi = QLabel("🔉"); vi.setStyleSheet("font-size:11px;")
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100); self._vol.setValue(70); self._vol.setFixedHeight(14)
        self._vol.setStyleSheet("""
            QSlider::groove:horizontal{height:3px;background:rgba(255,255,255,0.08);border-radius:2px;}
            QSlider::sub-page:horizontal{background:#1ed760;border-radius:2px;}
            QSlider::handle:horizontal{width:10px;height:10px;margin:-4px 0;background:#fff;border-radius:5px;}
            QSlider::handle:horizontal:hover{background:#1ed760;}
        """)
        self._vol.valueChanged.connect(self._do_volume)
        self._vol_pct = QLabel("70%")
        self._vol_pct.setStyleSheet("font-size:8px;color:rgba(240,242,245,0.2);font-family:'Consolas';min-width:24px;")
        vr.addWidget(vi); vr.addWidget(self._vol, 1); vr.addWidget(self._vol_pct)
        bl.addLayout(vr)
        self._lay.addWidget(self._body)

        # ── STRIP ──
        strip = QWidget(); strip.setFixedHeight(22)
        strip.setStyleSheet("border-top:1px solid rgba(255,255,255,0.05);")
        sl = QHBoxLayout(strip); sl.setContentsMargins(10, 0, 10, 0); sl.setSpacing(0)

        sp = QLabel("●"); sp.setStyleSheet("font-size:8px;color:#1ed760;")
        lb = QLabel("spotify mini")
        lb.setStyleSheet("font-size:7px;color:rgba(240,242,245,0.2);letter-spacing:1px;margin-left:3px;")
        sl.addWidget(sp); sl.addWidget(lb); sl.addStretch()

        self._conn_lbl = QLabel("bağlanıyor")
        self._conn_lbl.setStyleSheet("font-size:7px;color:rgba(240,242,245,0.2);font-family:'Consolas';")
        sl.addWidget(self._conn_lbl)

        self._settings_btn = QPushButton(" ⊹")
        self._settings_btn.setStyleSheet("""
            QPushButton{background:transparent;color:rgba(240,242,245,0.25);
                border:none;font-size:11px;padding:0 4px;}
            QPushButton:hover{color:#1ed760;}
        """)
        self._settings_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._settings_btn.clicked.connect(self._open_settings)
        sl.addWidget(self._settings_btn)

        disc = QPushButton("çıkış")
        disc.setStyleSheet("""
            QPushButton{background:transparent;color:rgba(240,242,245,0.2);
                border:none;font-size:7px;padding:0 0 0 6px;}
            QPushButton:hover{color:#e05858;}
        """)
        disc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        disc.clicked.connect(self._do_logout)
        sl.addWidget(disc)
        self._lay.addWidget(strip)
        self.adjustSize()

    def _mk_ctrl(self, icon, size, toggle=False, is_play=False):
        b = QPushButton(icon); b.setFixedSize(size, size)
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setProperty("toggled", False)
        if is_play:
            b.setStyleSheet("""
                QPushButton{background:#1ed760;color:#000;border:none;border-radius:17px;font-size:12px;}
                QPushButton:hover{background:#2af074;} QPushButton:pressed{background:#17b84e;}
            """)
        else:
            b.setStyleSheet("""
                QPushButton{background:transparent;color:rgba(240,242,245,0.4);
                    border:none;border-radius:6px;font-size:12px;padding:4px;}
                QPushButton:hover{background:rgba(255,255,255,0.05);color:#f0f2f5;}
                QPushButton[toggled="true"]{color:#1ed760;}
            """)
        return b

    def _set_placeholder_art(self):
        px = QPixmap(34, 34); px.fill(QColor("#1c2028"))
        self._art_lbl.setPixmap(px)

    def _register_hotkeys(self):
        s = self._settings
        hotkey_mgr.register("settings",  s.get("hk_settings",  "<ctrl>+<shift>+s"), self._open_settings)
        hotkey_mgr.register("collapse",  s.get("hk_collapse",  "<ctrl>+<shift>+m"), self._toggle_collapse)
        hotkey_mgr.register("playpause", s.get("hk_playpause", "<ctrl>+<shift>+p"), self._do_play)
        hotkey_mgr.register("next",      s.get("hk_next",      "<ctrl>+<shift>+n"), lambda: self._do_cmd("next"))
        hotkey_mgr.register("prev",      s.get("hk_prev",      "<ctrl>+<shift>+b"), lambda: self._do_cmd("previous"))
        hotkey_mgr.start()
        self._update_tooltips()

    def _update_tooltips(self):
        s = self._settings
        def fmt(key, default):
            raw = s.get(key, default)
            # "<ctrl>+<shift>+p" → "Ctrl+Shift+P"
            return (raw.replace("<ctrl>", "Ctrl")
                       .replace("<shift>", "Shift")
                       .replace("<alt>", "Alt")
                       .upper()
                       .replace("+", " + "))

        pp  = fmt("hk_playpause", "<ctrl>+<shift>+p")
        nxt = fmt("hk_next",      "<ctrl>+<shift>+n")
        prv = fmt("hk_prev",      "<ctrl>+<shift>+b")
        col = fmt("hk_collapse",  "<ctrl>+<shift>+m")
        stg = fmt("hk_settings",  "<ctrl>+<shift>+s")

        self._play_btn.setToolTip(f"Oynat / Duraklat  [{pp}]")
        self._next_btn.setToolTip(f"Sonraki şarkı  [{nxt}]")
        self._prev_btn.setToolTip(f"Önceki şarkı  [{prv}]")
        self._col_btn.setToolTip(f"Küçült / Büyüt  [{col}]")

        hk_status = "etkin ✓" if HAS_PYNPUT else "pynput kurulu değil"
        self._settings_btn.setToolTip(
            f"Konum & görünüm ayarları  [{stg}]\n"
            f"─────────────────────────\n"
            f"Klavye kısayolları ({hk_status}):\n"
            f"  Oynat/Duraklat   {pp}\n"
            f"  Sonraki          {nxt}\n"
            f"  Önceki           {prv}\n"
            f"  Küçült/Büyüt     {col}\n"
            f"  Bu panel         {stg}"
        )

    # ── SETTINGS ──
    def _open_settings(self):
        if self._panel and self._panel.isVisible():
            self._panel.raise_(); return
        s = dict(self._settings); s["x"] = self.x(); s["y"] = self.y()
        self._panel = SettingsPanel(s)
        self._panel.applied.connect(self._apply_settings)
        screen = QApplication.primaryScreen().availableGeometry()
        px = self.x() - 350 if self.x() > 350 else self.x() + self.width() + 8
        py = max(screen.top(), min(self.y(), screen.bottom() - 480))
        self._panel.move(px, py); self._panel.show()

    # ── POLLER ──
    def _start_poller(self):
        self._poller = SpotifyPoller()
        self._poller.track_updated.connect(self._on_track)
        self._poller.error.connect(lambda _: self._conn_lbl.setText("hata"))
        self._poller.start()

    def _on_track(self, d):
        if d.get("nothing"):
            self._name_lbl.setText("Çalmıyor"); self._artist_lbl.setText("Spotify'ı aç")
            self._conn_lbl.setText("bekliyor"); self.is_playing = False; self._update_play(); return
        self._name_lbl.setText(self._elide(d.get("name",""), 18))
        self._artist_lbl.setText(self._elide(d.get("artist",""), 22))
        self.cur_ms = d["progress_ms"]; self.dur_ms = d["duration_ms"]
        self.is_playing = d["is_playing"]; self._update_play(); self._update_prog()
        self._conn_lbl.setText("bağlı ✓")
        art = d.get("art_url")
        if art and art != self._last_art:
            self._last_art = art
            if self._art_loader: self._art_loader.terminate()
            self._art_loader = ArtLoader(art)
            self._art_loader.loaded.connect(self._art_lbl.setPixmap)
            self._art_loader.start()

    def _on_tick(self):
        if self.is_playing: self.cur_ms += 1000; self._update_prog()

    def _update_prog(self):
        self._prog.set_value(min(self.cur_ms / self.dur_ms, 1.0))
        self._t_cur.setText(self._fmt(self.cur_ms)); self._t_tot.setText(self._fmt(self.dur_ms))

    def _update_play(self):
        self._play_btn.setText("⏸" if self.is_playing else "▶")
        self._eq_w.set_playing(self.is_playing)

    # ── CONTROLS ──
    def _do_play(self):
        ep = "/pause" if self.is_playing else "/play"
        threading.Thread(target=spotify_cmd, args=("PUT", ep), daemon=True).start()
        self.is_playing = not self.is_playing; self._update_play()

    def _do_cmd(self, cmd):
        threading.Thread(target=spotify_cmd, args=("POST", f"/{cmd}"), daemon=True).start()
        QTimer.singleShot(800, self._poller._poll)

    def _do_shuffle(self):
        s = not (self._sh_btn.property("toggled") or False)
        self._sh_btn.setProperty("toggled", s)
        self._sh_btn.style().unpolish(self._sh_btn); self._sh_btn.style().polish(self._sh_btn)
        threading.Thread(target=spotify_cmd, args=("PUT", f"/shuffle?state={str(s).lower()}"), daemon=True).start()

    def _do_repeat(self):
        s = not (self._rep_btn.property("toggled") or False)
        self._rep_btn.setProperty("toggled", s)
        self._rep_btn.style().unpolish(self._rep_btn); self._rep_btn.style().polish(self._rep_btn)
        threading.Thread(target=spotify_cmd, args=("PUT", f"/repeat?state={'context' if s else 'off'}"), daemon=True).start()

    def _do_volume(self, v):
        self._vol_pct.setText(f"{v}%")
        threading.Thread(target=spotify_cmd, args=("PUT", f"/volume?volume_percent={v}"), daemon=True).start()

    def _on_seek(self, pct):
        pos = int(pct * self.dur_ms); self.cur_ms = pos; self._update_prog()
        threading.Thread(target=spotify_cmd, args=("PUT", f"/seek?position_ms={pos}"), daemon=True).start()

    def _do_logout(self):
        if self._poller: self._poller.stop()
        hotkey_mgr.stop()
        token_mgr.revoke(); self.close(); _show_setup()

    # ── COLLAPSE ──
    def _toggle_collapse(self):
        self.collapsed = not self.collapsed
        self._body.setVisible(not self.collapsed)
        self._col_btn.setText("▸" if self.collapsed else "▾")
        self.adjustSize()
        s = dict(self._settings); s["x"] = self.x(); s["y"] = self.y(); save_settings(s)

    # ── DRAG — sürükle & konum otomatik kaydedilir ──
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._drag_pos:
            self._drag_pos = None
            s = dict(self._settings); s["x"] = self.x(); s["y"] = self.y()
            self._settings = s; save_settings(s)
            if self._panel and self._panel.isVisible():
                self._panel.update_pos(self.x(), self.y())

    # ── HELPERS ──
    @staticmethod
    def _fmt(ms):
        s = int(ms / 1000); return f"{s//60}:{s%60:02d}"

    @staticmethod
    def _elide(text, n):
        return text if len(text) <= n else text[:n-1] + "…"


# ─────────────────────────────────────────────
#  APP ENTRY
# ─────────────────────────────────────────────
_app = _setup = _player = None

def _show_setup():
    global _setup
    _setup = SetupWindow()
    _setup.login_success.connect(_on_login)
    _setup.show()

def _on_login():
    global _player
    if _setup: _setup.close()
    _player = PlayerOverlay(); _player.show()

def main():
    global _app
    _app = QApplication(sys.argv)
    _app.setApplicationName("Spotify Mini Player")
    _app.setQuitOnLastWindowClosed(False)
    if token_mgr.has_token:
        global _player
        _player = PlayerOverlay(); _player.show()
    else:
        _show_setup()
    sys.exit(_app.exec())

if __name__ == "__main__":
    main()
