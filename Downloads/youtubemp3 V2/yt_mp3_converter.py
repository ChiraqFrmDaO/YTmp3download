#!/usr/bin/env python3
"""
YT -> MP3 Converter
GUI: PyQt6  |  Download: yt-dlp  |  Audio: FFmpeg
"""

import sys, os, re, subprocess, platform, shutil, hashlib, logging, traceback
from pathlib import Path
from datetime import datetime
import urllib.request
import json
from packaging import version

# --- Logging naar bestand (voor support/debugging) -----------------------------
LOG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "YT-MP3" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"app_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

def log_exception(exc_type, exc_value, exc_tb):
    """Vangt onverwachte crashes op en logt ze i.p.v. de app stil te laten crashen."""
    logging.critical("Onverwachte fout:\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = log_exception

# Windows subprocess flags om console vensters te voorkomen
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0

# --- Auto-updater configuratie -------------------------------------------------
GITHUB_REPO = "ChiraqFrmDaO/YTmp3download"
CURRENT_VERSION = "1.0.1"

def check_for_updates():
    """Checkt GitHub API voor nieuwe versie"""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "YT-MP3-Converter"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            latest_version = data["tag_name"].lstrip("v")
            
            # Check of assets bestaan
            if not data.get("assets"):
                return {"available": False, "error": "Geen assets gevonden in release"}
            
            # Zoek Windows exe asset + bijbehorende checksum (sha256)
            download_url = None
            checksum_url = None
            for asset in data["assets"]:
                name = asset.get("name", "")
                if name.endswith(".exe"):
                    download_url = asset["browser_download_url"]
                if name.endswith(".sha256") or name.endswith(".sha256.txt"):
                    checksum_url = asset["browser_download_url"]

            if not download_url:
                return {"available": False, "error": "Geen .exe asset gevonden"}

            # Gebruik packaging.version voor correcte semver vergelijking
            if version.parse(latest_version) > version.parse(CURRENT_VERSION):
                return {
                    "available": True,
                    "version": latest_version,
                    "download_url": download_url,
                    "checksum_url": checksum_url,
                    "notes": data.get("body", "")
                }
        return {"available": False}
    except Exception as e:
        print(f"Update check mislukt: {e}")
        return {"available": False, "error": str(e)}

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QProgressBar,
    QTextEdit, QFrame, QFileDialog, QDialog, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QSettings
from PyQt6.QtGui import QColor, QPalette

import yt_dlp

# --- Node.js vinden (voor yt-dlp JS runtime) ----------------------------------
def find_node():
    try:
        r = subprocess.run(["where.exe", "node"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if r.returncode == 0:
            return r.stdout.strip().splitlines()[0]
    except Exception:
        pass
    for p in [
        Path("C:/Program Files/nodejs/node.exe"),
        Path("C:/Program Files (x86)/nodejs/node.exe"),
    ]:
        if p.exists():
            return str(p)
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    try:
        base = local / "Microsoft" / "WinGet" / "Packages"
        if base.exists():
            hits = list(base.rglob("node.exe"))
            if hits:
                return str(hits[0])
    except Exception:
        pass
    return None

# --- FFmpeg vinden ------------------------------------------------------------
def find_ffmpeg():
    # 1. Naast de exe (PyInstaller bundle)
    base = Path(sys.executable).parent
    if (base / "ffmpeg.exe").exists():
        return str(base)

    # 2. where.exe (werkt ook als PATH nog niet ververst is in deze sessie)
    try:
        r = subprocess.run(["where.exe", "ffmpeg"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if r.returncode == 0:
            return str(Path(r.stdout.strip().splitlines()[0]).parent)
    except Exception:
        pass

    # 3. Standaard PATH
    if shutil.which("ffmpeg"):
        return None  # yt-dlp pakt hem zelf

    # 4. Winget pad
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    try:
        base = local / "Microsoft" / "WinGet" / "Packages"
        if base.exists():
            hits = list(base.rglob("ffmpeg.exe"))
            if hits:
                return str(hits[0].parent)
    except Exception:
        pass

    return None

NODE_PATH    = find_node()
FFMPEG_PATH  = find_ffmpeg()

# --- Setup marker -------------------------------------------------------------
SETUP_FLAG = Path(os.environ.get("APPDATA", "")) / "YT-MP3" / ".setup_done"

def setup_already_done():
    return SETUP_FLAG.exists()

def mark_setup_done():
    SETUP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    SETUP_FLAG.touch()

# --- Kleuren ------------------------------------------------------------------
C = {
    "bg":      "#0D0D0F", "surface": "#16161A", "card":    "#1E1E24",
    "border":  "#2A2A35", "accent":  "#FF3B5C", "accent2": "#FF6B35",
    "text":    "#F0F0F5", "muted":   "#6B6B80", "ok":      "#2ECC71",
    "warn":    "#F39C12", "err":     "#E74C3C", "inp":     "#121216",
}

QSS = f"""
QMainWindow, QWidget#root {{ background: {C['bg']}; }}
QWidget {{ background: transparent; color: {C['text']};
           font-family: 'Inter','Segoe UI','SF Pro Display',sans-serif; }}
QFrame#card {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 12px; }}
QLineEdit {{
    background: {C['inp']}; border: 1.5px solid {C['border']}; border-radius: 8px;
    color: {C['text']}; padding: 0px 14px; font-size: 14px;
}}
QLineEdit:focus {{ border-color: {C['accent']}; }}
QComboBox {{
    background: {C['inp']}; border: 1.5px solid {C['border']}; border-radius: 8px;
    color: {C['text']}; padding: 0px 14px; font-size: 13px; min-width: 180px;
}}
QComboBox:focus {{ border-color: {C['border']}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {C['muted']}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {C['card']}; border: 1px solid {C['border']}; border-radius: 8px;
    color: {C['text']}; selection-background-color: {C['accent']}; padding: 4px;
}}
QPushButton#dlBtn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {C['accent']},stop:1 {C['accent2']});
    border: none; border-radius: 8px; color: white;
    font-size: 14px; font-weight: 700; padding: 0px 28px;
}}
QPushButton#dlBtn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff5570,stop:1 #ff8555);
}}
QPushButton#dlBtn:disabled {{ background: {C['border']}; color: {C['muted']}; }}
QPushButton#secBtn {{
    background: {C['surface']}; border: 1.5px solid {C['border']}; border-radius: 8px;
    color: {C['muted']}; font-size: 13px; padding: 0px 16px;
}}
QPushButton#secBtn:hover {{ border-color: {C['accent']}; color: {C['text']}; }}
QProgressBar {{
    background: {C['inp']}; border: none; border-radius: 5px;
    height: 10px; color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {C['accent']},stop:1 {C['accent2']});
    border-radius: 5px;
}}
QTextEdit {{
    background: {C['inp']}; border: 1px solid {C['border']}; border-radius: 8px;
    color: {C['muted']}; font-family: 'JetBrains Mono','Fira Code','Consolas',monospace;
    font-size: 11px; padding: 10px;
}}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

# --- Zoek worker thread -------------------------------------------------------
class SearchWorker(QThread):
    sig_results = pyqtSignal(list)   # list of dicts: {title, channel, duration, url}
    sig_error   = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "no_color": True,
                "extract_flat": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch8:{self.query}", download=False)
            results = []
            for entry in (info.get("entries") or []):
                dur = entry.get("duration") or 0
                m, s = divmod(int(dur), 60)
                results.append({
                    "title":    entry.get("title", "Onbekend"),
                    "channel":  entry.get("uploader") or entry.get("channel", ""),
                    "duration": f"{m}:{s:02d}",
                    "url":      entry.get("url") or entry.get("webpage_url", ""),
                })
            self.sig_results.emit(results)
        except Exception as e:
            self.sig_error.emit(str(e))



# --- Update worker thread ------------------------------------------------------
class UpdateWorker(QThread):
    sig_progress = pyqtSignal(int, str)
    sig_done     = pyqtSignal(bool, str)

    def __init__(self, download_url, checksum_url=None):
        super().__init__()
        self.download_url = download_url
        self.checksum_url = checksum_url

    def run(self):
        try:
            # Download nieuwe versie
            self.sig_progress.emit(10, "Update downloaden...")
            temp_dir = Path(os.environ.get("TEMP", "/tmp"))
            # Unieke tijdelijke naam i.p.v. vaste naam (voorkomt conflicten/permission-issues
            # als een vorige update-poging is mislukt en het bestand nog "in gebruik" is)
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            temp_file = temp_dir / f"yt_mp3_converter_update_{stamp}.exe"
            backup_file = temp_dir / f"yt_mp3_converter_backup_{stamp}.exe"

            req = urllib.request.Request(self.download_url, headers={"User-Agent": "YT-MP3-Converter"})
            with urllib.request.urlopen(req, timeout=30) as response:
                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                chunk_size = 8192
                sha256 = hashlib.sha256()

                with open(temp_file, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = 10 + (downloaded / total) * 70
                            self.sig_progress.emit(int(pct), f"Downloaden... {downloaded/1024/1024:.1f}MB")

            # Controleer dat het volledige bestand is binnengekomen
            if total and downloaded != total:
                temp_file.unlink(missing_ok=True)
                raise RuntimeError(f"Download incompleet ({downloaded}/{total} bytes)")

            # Checksum-verificatie: als de release een .sha256 bestand publiceert,
            # MOET de hash kloppen voordat we de lopende exe overschrijven.
            self.sig_progress.emit(82, "Integriteit controleren...")
            if self.checksum_url:
                try:
                    creq = urllib.request.Request(self.checksum_url, headers={"User-Agent": "YT-MP3-Converter"})
                    with urllib.request.urlopen(creq, timeout=15) as cresp:
                        expected = cresp.read().decode("utf-8", "ignore").strip().split()[0].lower()
                    actual = sha256.hexdigest().lower()
                    if expected != actual:
                        temp_file.unlink(missing_ok=True)
                        raise RuntimeError("Checksum komt niet overeen - update geweigerd (mogelijk corrupt of onveilig bestand)")
                    logging.info(f"Update checksum geverifieerd: {actual}")
                except (IndexError, UnicodeDecodeError) as e:
                    temp_file.unlink(missing_ok=True)
                    raise RuntimeError(f"Checksum-bestand kon niet worden gelezen: {e}")
            else:
                logging.warning("Geen checksum-bestand gevonden bij release - update wordt ongeverifieerd geinstalleerd.")

            self.sig_progress.emit(90, "Installeren...")

            # Maak update script met robuustere methode
            script_path = temp_dir / "update_script.bat"
            current_exe = Path(sys.executable)
            update_script = f"""@echo off
timeout /t 3 /nobreak >nul
:: Stop het huidige proces als het nog draait
taskkill /F /IM "{current_exe.name}" 2>nul
timeout /t 2 /nobreak >nul
:: Maak backup
if exist "{current_exe}" copy /Y "{current_exe}" "{backup_file}" >nul
:: Vervang met nieuwe versie
copy /Y "{temp_file}" "{current_exe}" >nul
:: Start nieuwe versie
start "" "{current_exe}"
:: Cleanup
del "{script_path}" >nul 2>&1
del "{temp_file}" >nul 2>&1
"""
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(update_script)

            # Start update script en sluit huidige app
            subprocess.Popen([str(script_path)], shell=True, creationflags=CREATE_NO_WINDOW)
            self.sig_progress.emit(100, "Update voltooid!")
            self.sig_done.emit(True, "")

        except Exception as e:
            self.sig_done.emit(False, str(e))


# --- Setup / installer worker -------------------------------------------------
class SetupWorker(QThread):
    sig_log    = pyqtSignal(str, str)   # message, level
    sig_done   = pyqtSignal(bool)       # success

    def run(self):
        ok = True
        ok &= self._ensure("FFmpeg",  "Gyan.FFmpeg",   self._find_ffmpeg_after)
        ok &= self._ensure("Node.js", "OpenJS.NodeJS", self._find_node_after)
        if ok:
            mark_setup_done()
        self.sig_done.emit(ok)

    def _ensure(self, name, winget_id, verify_fn):
        if verify_fn():
            self.sig_log.emit(f"{name} al geïnstalleerd — overgeslagen.", "ok")
            return True
        self.sig_log.emit(f"{name} niet gevonden — installeren via winget...", "info")
        try:
            r = subprocess.run(
                ["winget", "install", "--id", winget_id,
                 "-e", "--accept-source-agreements", "--accept-package-agreements",
                 "--silent"],
                capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW
            )
            if r.returncode == 0 or "already installed" in r.stdout.lower():
                self.sig_log.emit(f"{name} succesvol geïnstalleerd.", "ok")
                return True
            else:
                self.sig_log.emit(f"{name} installatie mislukt: {r.stderr.strip()[:200]}", "err")
                return False
        except FileNotFoundError:
            self.sig_log.emit("winget niet gevonden — installeer handmatig via winget.ms", "err")
            return False
        except subprocess.TimeoutExpired:
            self.sig_log.emit(f"{name} installatie duurde te lang (timeout).", "err")
            return False
        except Exception as e:
            self.sig_log.emit(f"{name} fout: {e}", "err")
            return False

    def _find_ffmpeg_after(self):
        return bool(find_ffmpeg()) or bool(shutil.which("ffmpeg"))

    def _find_node_after(self):
        return bool(find_node())


# --- Update dialoog -----------------------------------------------------------
class UpdateDialog(QDialog):
    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setWindowTitle("Update Beschikbaar")
        self.setFixedSize(450, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        title = QLabel(f"Nieuwe versie beschikbaar: v{update_info['version']}")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#FF3B5C;")
        lay.addWidget(title)

        sub = QLabel(f"Huidige versie: v{CURRENT_VERSION}")
        sub.setStyleSheet("font-size:12px;color:#6B6B80;")
        lay.addWidget(sub)

        notes = QLabel(update_info.get('notes', 'Geen release notes beschikbaar.'))
        notes.setWordWrap(True)
        notes.setStyleSheet("font-size:12px;color:#F0F0F5;background:#1E1E24;padding:12px;border-radius:8px;")
        lay.addWidget(notes)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(8)
        self.pbar.setVisible(False)
        lay.addWidget(self.pbar)

        self.status = QLabel("")
        self.status.setStyleSheet("font-size:11px;color:#6B6B80;")
        lay.addWidget(self.status)

        btn_row = QHBoxLayout()
        self.later_btn = QPushButton("Later")
        self.later_btn.setFixedHeight(38)
        self.later_btn.setStyleSheet("background:#2A2A35;color:#F0F0F5;border-radius:6px;font-size:13px;")
        self.later_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.later_btn)

        self.update_btn = QPushButton("Nu updaten")
        self.update_btn.setFixedHeight(38)
        self.update_btn.setStyleSheet("background:#FF3B5C;color:white;border-radius:6px;font-weight:600;font-size:13px;")
        self.update_btn.clicked.connect(self._start_update)
        btn_row.addWidget(self.update_btn)
        lay.addLayout(btn_row)

        self._worker = None

    def _start_update(self):
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.pbar.setVisible(True)
        self.status.setText("Update downloaden...")

        self._worker = UpdateWorker(self.update_info['download_url'], self.update_info.get('checksum_url'))
        self._worker.sig_progress.connect(self._on_progress)
        self._worker.sig_done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, pct, msg):
        self.pbar.setValue(pct)
        self.status.setText(msg)

    def _on_done(self, ok, error):
        if ok:
            self.status.setText("Update voltooid! App wordt herstart...")
            QTimer.singleShot(2000, QApplication.quit)
        else:
            self.status.setText(f"Fout: {error}")
            self.update_btn.setEnabled(True)
            self.later_btn.setEnabled(True)
            # Log error naar parent window als beschikbaar
            if self.parent():
                try:
                    self.parent()._log(f"Update mislukt: {error}", "err")
                except:
                    pass


# --- Setup venster ------------------------------------------------------------
class SetupWindow(QDialog):
    sig_setup_done = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YT → MP3  —  Eerste installatie")
        self.setFixedSize(520, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(16)

        title = QLabel("Eerste installatie")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        lay.addWidget(title)

        sub = QLabel("FFmpeg en Node.js worden automatisch geïnstalleerd via winget.\nDit hoeft maar één keer.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size:12px;color:#6B6B80;")
        lay.addWidget(sub)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.log.setStyleSheet("background:#121216;border:1px solid #2A2A35;border-radius:8px;font-size:11px;color:#F0F0F5;padding:8px;")
        lay.addWidget(self.log)

        self.btn = QPushButton("Installeren")
        self.btn.setFixedHeight(42)
        self.btn.setStyleSheet("background:#FF3B5C;color:white;border-radius:8px;font-weight:600;font-size:13px;")
        self.btn.clicked.connect(self._start)
        lay.addWidget(self.btn)

    def _start(self):
        self.btn.setEnabled(False)
        self.btn.setText("Bezig met installeren...")
        self._worker = SetupWorker()
        self._worker.sig_log.connect(self._on_log)
        self._worker.sig_done.connect(self._on_done)
        self._worker.start()

    def _on_log(self, msg, level):
        colors = {"ok": "#2ECC71", "err": "#E74C3C", "warn": "#F39C12", "info": "#F0F0F5"}
        col = colors.get(level, "#F0F0F5")
        self.log.append(f'<span style="color:{col};">{msg}</span>')

    def _on_done(self, ok):
        if ok:
            self.btn.setText("✓ Klaar — doorgaan")
            self.btn.setEnabled(True)
            self.btn.clicked.disconnect()
            self.btn.clicked.connect(self._finish)
        else:
            self.btn.setText("Opnieuw proberen")
            self.btn.setEnabled(True)
            self.btn.clicked.disconnect()
            self.btn.clicked.connect(self._start)

    def _finish(self):
        # Herlaad paden na installatie
        global NODE_PATH, FFMPEG_PATH
        NODE_PATH   = find_node()
        FFMPEG_PATH = find_ffmpeg()
        self.sig_setup_done.emit()
        self.accept()



class SearchWindow(QWidget):
    sig_url_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("YouTube Zoeken")
        self.setMinimumSize(620, 500)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        search_row = QHBoxLayout(); search_row.setSpacing(10)
        self.search_in = QLineEdit()
        self.search_in.setPlaceholderText("Zoek op artiest, titel...")
        self.search_in.setFixedHeight(44)
        self.search_in.returnPressed.connect(self._search)
        search_row.addWidget(self.search_in)
        self.search_btn = QPushButton("Zoeken")
        self.search_btn.setObjectName("dlBtn")
        self.search_btn.setFixedHeight(44)
        self.search_btn.setFixedWidth(110)
        self.search_btn.clicked.connect(self._search)
        search_row.addWidget(self.search_btn)
        root.addLayout(search_row)

        self.status_lbl = QLabel("Typ een zoekopdracht en druk op Zoeken.")
        self.status_lbl.setStyleSheet(f"color:{C['muted']};font-size:12px;")
        root.addWidget(self.status_lbl)

        self.list = QListWidget()
        self.list.setStyleSheet(f"""
            QListWidget {{
                background: {C['inp']}; border: 1px solid {C['border']};
                border-radius: 10px; color: {C['text']}; font-size: 13px; padding: 6px;
            }}
            QListWidget::item {{ padding: 12px 14px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: {C['accent']}; color: white; }}
            QListWidget::item:hover:!selected {{ background: {C['border']}; }}
        """)
        self.list.itemDoubleClicked.connect(self._pick_and_close)
        root.addWidget(self.list)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.pick_btn = QPushButton("Kies en download")
        self.pick_btn.setObjectName("dlBtn")
        self.pick_btn.setFixedHeight(42)
        self.pick_btn.setMinimumWidth(140)
        self.pick_btn.setEnabled(False)
        self.pick_btn.clicked.connect(self._pick_and_close)
        btn_row.addWidget(self.pick_btn)
        root.addLayout(btn_row)

        self.search_in.setFocus()

    def _search(self):
        query = self.search_in.text().strip()
        if not query:
            return
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Bezig...")
        self.pick_btn.setEnabled(False)
        self.list.clear()
        self.status_lbl.setText("Zoeken...")
        self._worker = SearchWorker(query)
        self._worker.sig_results.connect(self._on_results)
        self._worker.sig_error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, results):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Zoeken")
        if not results:
            self.status_lbl.setText("Geen resultaten gevonden.")
            return
        self.status_lbl.setText(f"{len(results)} resultaten — dubbelklik of selecteer en klik 'Kies & download'.")
        for r in results:
            item = QListWidgetItem(f"  {r['title']}\n  {r['channel']}  •  {r['duration']}")
            item.setData(Qt.ItemDataRole.UserRole, r["url"])
            self.list.addItem(item)
        self.pick_btn.setEnabled(True)

    def _on_error(self, err):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Zoeken")
        self.status_lbl.setText(f"Fout: {err}")

    def _pick_and_close(self, *_):
        item = self.list.currentItem()
        if item:
            self.sig_url_chosen.emit(item.data(Qt.ItemDataRole.UserRole))
            self.close()


# --- Worker thread ------------------------------------------------------------
class Worker(QThread):
    sig_progress = pyqtSignal(float, str)
    sig_log      = pyqtSignal(str, str)
    sig_done     = pyqtSignal(bool, str)
    sig_meta     = pyqtSignal(str, str)

    def __init__(self, url, quality, out_dir):
        super().__init__()
        self.url     = url
        self.quality = quality
        self.out_dir = out_dir
        self._cancel = False
        self._last   = -1

    def cancel(self): self._cancel = True

    def _base_opts(self):
        opts = {
            "quiet": False,
            "no_warnings": False,
            "no_color": True,
            "socket_timeout": 30,
            "logger": self._YTLogger(self),
        }
        if FFMPEG_PATH:
            opts["ffmpeg_location"] = FFMPEG_PATH
        return opts

    class _YTLogger:
        """Stuurt alleen nette yt-dlp berichten naar de GUI log."""
        # Prefixes die we volledig negeren
        _SKIP = (
            "[download]", "[youtube]", "[YoutubeYtBe]", "[youtube:tab]",
            "[info]", "[ExtractAudio]", "[ffmpeg]", "[Merger]",
        )
        _SKIP_CONTAINS = (
            "Downloading webpage", "Downloading API JSON", "Downloading android",
            "Downloading playlist", "Downloading item", "JavaScript runtime",
            "js-runtimes", "EJS", "deprecated",
        )

        def __init__(self, worker):
            self._w = worker

        def _should_skip(self, msg):
            m = msg.strip()
            for p in self._SKIP:
                if m.startswith(p):
                    return True
            for s in self._SKIP_CONTAINS:
                if s in m:
                    return True
            return False

        def debug(self, msg):
            pass  # volledig negeren

        def info(self, msg):
            if not self._should_skip(msg):
                self._w.sig_log.emit(msg.strip(), "info")

        def warning(self, msg):
            # Negeer JS runtime waarschuwing
            if "JavaScript runtime" in msg or "js-runtimes" in msg:
                return
            self._w.sig_log.emit(msg.strip(), "warn")

        def error(self, msg):
            self._w.sig_log.emit(msg.strip(), "err")

    def run(self):
        self.sig_log.emit("Verbinding checken...", "info")
        self._rate_check()

        # Playlist uit URL verwijderen — alleen het enkele video-ID gebruiken
        url = self.url
        import re as _re
        match = _re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
        if match:
            url = f"https://www.youtube.com/watch?v={match.group(1)}"
            if url != self.url:
                self.sig_log.emit(f"Playlist genegeerd, enkel video: {url}", "info")
        self._url_clean = url

        # --- Metadata ophalen -------------------------------------------------
        self.sig_log.emit("Video info ophalen...", "info")
        try:
            opts_info = self._base_opts()
            opts_info["skip_download"] = True
            opts_info["ignore_no_formats_error"] = True
            with yt_dlp.YoutubeDL(opts_info) as ydl:
                info = ydl.extract_info(self._url_clean, download=False)
        except Exception as e:
            self.sig_log.emit(f"Info ophalen mislukt: {e}", "err")
            self.sig_done.emit(False, "")
            return

        title   = info.get("title", "Onbekend")
        channel = info.get("uploader") or info.get("channel", "Onbekend")
        dur     = info.get("duration", 0)
        m, s    = divmod(int(dur), 60)

        self.sig_meta.emit(title, channel)
        self.sig_log.emit(f"Nummer: {title}", "info")
        self.sig_log.emit(f"Artiest: {channel}  ({m}:{s:02d})", "info")
        self.sig_log.emit(f"Kwaliteit: {self.quality} kbps", "info")

        if self._cancel:
            self.sig_log.emit("Geannuleerd", "warn")
            self.sig_done.emit(False, "")
            return

        # --- Output map -------------------------------------------------------
        safe_title   = re.sub(r'[\\/*?:"<>|]', "", title)[:80].strip()
        safe_channel = re.sub(r'[\\/*?:"<>|]', "", channel)[:40].strip()
        folder_name  = f"{safe_channel} - {safe_title}" if safe_channel else safe_title
        folder       = Path(self.out_dir) / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        self.sig_log.emit(f"Map: {folder}", "info")

        # --- Download + convert -----------------------------------------------
        opts = self._base_opts()
        opts.update({
            "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(folder / "%(title)s.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": self.quality}],
            "progress_hooks": [self._hook],
            "retries": 3,
            "fragment_retries": 3,
            "noplaylist": True,
        })
        if NODE_PATH:
            opts["extractor_args"] = {"youtube": {"js_runtimes": [f"node:{NODE_PATH}"]}}

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self._url_clean])

            mp3s = list(folder.glob("*.mp3"))
            if mp3s:
                size = os.path.getsize(mp3s[0]) / 1024 / 1024
                self.sig_log.emit(f"Klaar: {mp3s[0].name}  ({size:.1f} MB)", "ok")
                self.sig_progress.emit(100, "")
                self.sig_done.emit(True, str(mp3s[0]))
            else:
                self.sig_log.emit("MP3 niet gevonden na conversie", "err")
                self.sig_done.emit(False, "")

        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "429" in err or "Too Many Requests" in err:
                self.sig_log.emit("Rate limit (429) - probeer later opnieuw", "err")
            elif "private" in err.lower() or "unavailable" in err.lower():
                self.sig_log.emit("Video is prive of niet beschikbaar", "err")
            elif "ffmpeg" in err.lower() or "ffprobe" in err.lower():
                self.sig_log.emit("FFmpeg niet gevonden!", "err")
            else:
                self.sig_log.emit(f"Download fout: {err[:300]}", "err")
            self.sig_done.emit(False, "")

        except Exception as e:
            self.sig_log.emit(f"Onverwacht: {e}", "err")
            self.sig_done.emit(False, "")

    def _rate_check(self):
        import urllib.request, urllib.error
        try:
            req = urllib.request.Request("https://www.youtube.com",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                self.sig_log.emit("YouTube bereikbaar", "info")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.sig_log.emit("Rate limit actief (429)!", "warn")
            else:
                self.sig_log.emit(f"HTTP fout {e.code} bij verbinden", "warn")
        except Exception:
            self.sig_log.emit("Verbinding kon niet worden geverifieerd", "warn")

    def _hook(self, d):
        if self._cancel:
            raise yt_dlp.utils.DownloadCancelled("Geannuleerd door gebruiker")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            dl    = d.get("downloaded_bytes", 0)
            spd   = d.get("speed", 0) or 0
            eta   = d.get("eta", 0) or 0
            pct   = (dl / total * 100) if total else 0
            spd_s = f"{spd/1024:.0f} KB/s" if spd < 1e6 else f"{spd/1024/1024:.1f} MB/s"
            eta_s = f"  ETA {eta}s" if eta else ""
            if abs(pct - self._last) >= 0.5:
                self._last = pct
                self.sig_progress.emit(pct, f"{spd_s}{eta_s}")
                self.sig_log.emit(f"Download: {pct:.1f}%  {spd_s}{eta_s}", "info")
        elif d["status"] == "finished":
            self.sig_log.emit("Converteren naar MP3...", "info")
            self.sig_progress.emit(99, "Converteren...")
        elif d["status"] == "error":
            self.sig_log.emit("Fout tijdens download", "err")

# --- Hoofd venster ------------------------------------------------------------
class App(QMainWindow):
    QUALITIES = [
        ("320 kbps  -  Studio",    "320"),
        ("192 kbps  -  Hoog",      "192"),
        ("128 kbps  -  Standaard", "128"),
        ("96 kbps   -  Klein",     "96"),
    ]

    def __init__(self):
        super().__init__()
        self.worker    = None
        self._workers  = []  # houdt referenties vast zodat Python threads niet vroegtijdig opruimt
        self.settings  = QSettings("YT-MP3-Converter", "YT-MP3")
        default_dir    = str(Path.home() / "Downloads" / "YT-MP3")
        self.out_dir   = self.settings.value("out_dir", default_dir, type=str)
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)
        self._build()

        # Herstel laatst gebruikte kwaliteit en venstergrootte
        saved_quality = self.settings.value("quality", "192", type=str)
        idx = self.quality.findData(saved_quality)
        if idx >= 0:
            self.quality.setCurrentIndex(idx)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        # Check voor updates bij opstarten (na 2 seconden)
        QTimer.singleShot(2000, self._check_updates)

    def closeEvent(self, event):
        """Sla instellingen op en stop netjes lopende downloads voordat de app afsluit."""
        self.settings.setValue("out_dir", self.out_dir)
        self.settings.setValue("quality", self.quality.currentData())
        self.settings.setValue("geometry", self.saveGeometry())
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)  # max 3s wachten op nette afsluiting
        event.accept()

    def _build(self):
        self.setWindowTitle("YT -> MP3")
        self.setMinimumSize(640, 680)
        self.resize(680, 720)
        self.setStyleSheet(QSS)

        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(20)

        # Header
        hl = QVBoxLayout(); hl.setSpacing(4)
        header_row = QHBoxLayout()
        t = QLabel(f'<span style="color:{C["accent"]}">o</span>  YT -> MP3')
        t.setStyleSheet("font-size:24px;font-weight:800;letter-spacing:-0.5px;")
        header_row.addWidget(t)
        header_row.addStretch()

        self.update_btn = QPushButton("↻")
        self.update_btn.setFixedSize(32, 32)
        self.update_btn.setToolTip("Check voor updates")
        self.update_btn.setStyleSheet("background:#2A2A35;color:#6B6B80;border-radius:6px;font-size:16px;")
        self.update_btn.clicked.connect(self._check_updates)
        header_row.addWidget(self.update_btn)
        hl.addLayout(header_row)

        s = QLabel("Download YouTube audio in hoge kwaliteit")
        s.setStyleSheet(f"font-size:12px;color:{C['muted']};letter-spacing:0.5px;")
        hl.addWidget(s)

        ffmpeg_ok = bool(FFMPEG_PATH or shutil.which("ffmpeg"))
        node_ok   = bool(NODE_PATH)
        status_line = []
        status_line.append(("FFmpeg OK" if ffmpeg_ok else "FFmpeg NIET gevonden - installeer via: winget install ffmpeg", ffmpeg_ok))
        status_line.append(("Node.js OK" if node_ok else "Node.js NIET gevonden - installeer via: winget install OpenJS.NodeJS", node_ok))
        for msg, ok in status_line:
            lbl = QLabel(("OK  " if ok else "WAARSCHUWING  ") + msg)
            lbl.setStyleSheet(f"font-size:11px;color:{C['ok'] if ok else C['warn']};")
            hl.addWidget(lbl)
        lay.addLayout(hl)

        # Input kaart
        card = QFrame(); card.setObjectName("card")
        card.setMinimumHeight(160)
        cl = QVBoxLayout(card); cl.setContentsMargins(20, 20, 20, 20); cl.setSpacing(12)

        lbl_url = QLabel("URL")
        lbl_url.setStyleSheet(f"font-size:11px;color:{C['muted']};font-weight:600;letter-spacing:1px;")
        cl.addWidget(lbl_url)

        url_row = QHBoxLayout(); url_row.setSpacing(10)
        self.url_in = QLineEdit()
        self.url_in.setPlaceholderText("https://youtube.com/watch?v=...")
        self.url_in.setFixedHeight(44)
        self.url_in.returnPressed.connect(self._toggle)
        url_row.addWidget(self.url_in)

        self.search_btn = QPushButton("Zoeken")
        self.search_btn.setObjectName("secBtn")
        self.search_btn.setFixedHeight(44)
        self.search_btn.setFixedWidth(100)
        self.search_btn.setToolTip("Zoek een nummer op YouTube")
        self.search_btn.clicked.connect(self._open_search)
        url_row.addWidget(self.search_btn)
        cl.addLayout(url_row)

        row = QHBoxLayout(); row.setSpacing(10)
        self.quality = QComboBox()
        self.quality.setFixedHeight(44)
        for lbl, val in self.QUALITIES:
            self.quality.addItem(lbl, val)
        row.addWidget(self.quality)
        row.addStretch()

        self.folder_btn = QPushButton("Map")
        self.folder_btn.setObjectName("secBtn")
        self.folder_btn.setFixedHeight(44)
        self.folder_btn.setToolTip("Uitvoermap kiezen")
        self.folder_btn.clicked.connect(self._pick_folder)
        row.addWidget(self.folder_btn)

        self.dl_btn = QPushButton("Downloaden")
        self.dl_btn.setObjectName("dlBtn")
        self.dl_btn.setFixedHeight(44)
        self.dl_btn.clicked.connect(self._toggle)
        row.addWidget(self.dl_btn)
        cl.addLayout(row)
        lay.addWidget(card)

        self.folder_lbl = QLabel(f"Uitvoer:  {self.out_dir}")
        self.folder_lbl.setStyleSheet(f"color:{C['muted']};font-size:11px;padding-left:4px;")
        self.folder_lbl.setWordWrap(True)
        lay.addWidget(self.folder_lbl)

        # Progress kaart
        pc = QFrame(); pc.setObjectName("card")
        pl = QVBoxLayout(pc); pl.setContentsMargins(20,16,20,16); pl.setSpacing(10)

        top = QHBoxLayout()
        self.track_lbl = QLabel("Klaar om te downloaden")
        self.track_lbl.setStyleSheet(f"font-size:13px;font-weight:600;color:{C['text']};")
        top.addWidget(self.track_lbl)
        top.addStretch()
        self.speed_lbl = QLabel("")
        self.speed_lbl.setStyleSheet(f"font-size:11px;color:{C['muted']};")
        top.addWidget(self.speed_lbl)
        pl.addLayout(top)

        self.pbar = QProgressBar(); self.pbar.setValue(0); self.pbar.setFixedHeight(10)
        pl.addWidget(self.pbar)

        bot = QHBoxLayout()
        self.status_lbl = QLabel("Wachten...")
        self.status_lbl.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        bot.addWidget(self.status_lbl)
        bot.addStretch()
        self.pct_lbl = QLabel("0%")
        self.pct_lbl.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        bot.addWidget(self.pct_lbl)
        pl.addLayout(bot)
        lay.addWidget(pc)

        # Log
        log_lbl = QLabel("ACTIVITEITENLOG")
        log_lbl.setStyleSheet(f"font-size:11px;color:{C['muted']};font-weight:600;letter-spacing:1px;")
        lay.addWidget(log_lbl)

        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(160)
        lay.addWidget(self.log)

        br = QHBoxLayout()
        clr = QPushButton("Log wissen"); clr.setObjectName("secBtn")
        clr.clicked.connect(self.log.clear)
        br.addWidget(clr)
        br.addStretch()
        opn = QPushButton("Map openen"); opn.setObjectName("secBtn")
        opn.clicked.connect(self._open_folder)
        br.addWidget(opn)
        lay.addLayout(br)

    def _open_search(self):
        dlg = SearchWindow(self)
        dlg.sig_url_chosen.connect(lambda url: self.url_in.setText(url))
        dlg.show()

    def _toggle(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.dl_btn.setText("Downloaden")
            self._status("Geannuleerd", C["warn"])
        else:
            self._start()

    def _start(self):
        url = self.url_in.text().strip()
        if not url:
            self._log("Voer een URL in", "warn"); return
        # Striktere YouTube URL validatie
        yt_pattern = re.compile(r'^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_-]{11}')
        if not yt_pattern.match(url):
            self._log("Geen geldige YouTube URL", "warn"); return

        self.pbar.setValue(0); self.pct_lbl.setText("0%")
        self.speed_lbl.setText(""); self.track_lbl.setText("Bezig...")
        self._status("Downloaden...", C["accent"])
        self.dl_btn.setText("Stoppen")
        self.log.clear()
        self._log(f"Start: {url[:70]}", "info")
        self._log(f"FFmpeg: {FFMPEG_PATH or 'via PATH'}", "info")
        self._log(f"Node.js: {NODE_PATH or 'niet gevonden'}", "info")

        self.worker = Worker(url, self.quality.currentData().strip(), self.out_dir)
        self.worker.sig_progress.connect(self._on_progress)
        self.worker.sig_log.connect(self._log)
        self.worker.sig_done.connect(self._on_done)
        self.worker.sig_meta.connect(self._on_meta)
        self.worker.finished.connect(lambda: self._cleanup_worker(self.worker))
        self._workers.append(self.worker)
        self.worker.start()

    def _cleanup_worker(self, w):
        """Ruimt een afgeronde worker-thread netjes op (voorkomt memory leaks)."""
        if w in self._workers:
            self._workers.remove(w)
        w.deleteLater()

    def _on_progress(self, pct, spd):
        self.pbar.setValue(int(pct)); self.pct_lbl.setText(f"{pct:.0f}%")
        if spd: self.speed_lbl.setText(spd)

    def _on_meta(self, title, channel):
        self.track_lbl.setText(title[:45] + "..." if len(title) > 45 else title)

    def _on_done(self, ok, path):
        self.dl_btn.setText("Downloaden")
        if ok:
            self._status("Voltooid!", C["ok"])
            self.pbar.setValue(100); self.pct_lbl.setText("100%")
        else:
            self._status("Mislukt", C["err"])
        self.worker = None

    def _log(self, msg, level="info"):
        col = {"info": C["muted"], "warn": C["warn"], "err": C["err"], "ok": C["ok"]}.get(level, C["muted"])
        ts  = datetime.now().strftime("%H:%M:%S")
        self.log.append(f'<span style="color:{C["muted"]}">[{ts}]</span> <span style="color:{col}">{msg}</span>')
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _status(self, txt, col):
        self.status_lbl.setText(txt)
        self.status_lbl.setStyleSheet(f"color:{col};font-size:11px;font-weight:600;")

    def _pick_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Uitvoermap", self.out_dir)
        if f:
            self.out_dir = f
            self.folder_lbl.setText(f"Uitvoer: {f}")
            self._log(f"Map gewijzigd: {f}", "info")

    def _open_folder(self):
        if platform.system() == "Windows":   os.startfile(self.out_dir)
        elif platform.system() == "Darwin":  subprocess.Popen(["open", self.out_dir])

    def _check_updates(self):
        """Checkt voor updates en toont dialoog indien beschikbaar"""
        self._log("Controleren op updates...", "info")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("...")
        update_info = check_for_updates()
        self.update_btn.setEnabled(True)
        self.update_btn.setText("↻")

        if update_info.get("available"):
            self._log(f"Nieuwe versie beschikbaar: v{update_info['version']}", "ok")
            dlg = UpdateDialog(update_info, self)
            dlg.exec()
        elif update_info.get("error"):
            self._log(f"Update check mislukt: {update_info['error']}", "warn")
        else:
            self._log("Geen nieuwe versie beschikbaar", "info")

# --- Entry point --------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,     QColor(C["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Base,       QColor(C["inp"]))
    pal.setColor(QPalette.ColorRole.Text,       QColor(C["text"]))
    app.setPalette(pal)

    needs_setup = not setup_already_done() or not FFMPEG_PATH or not find_node()

    if needs_setup:
        setup = SetupWindow()
        setup.setStyleSheet(f"background:{C['bg']};color:{C['text']};font-family:'Segoe UI',sans-serif;")
        result = setup.exec()
        # Doorgaan ook als setup gedeeltelijk mislukt — gebruiker kan handmatig installeren
    win = App(); win.show()
    sys.exit(app.exec())