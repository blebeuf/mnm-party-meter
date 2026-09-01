from __future__ import annotations

import ctypes
import json
import os
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "MNMPartyMeter"
APP_VERSION = "1.0.2"
MAX_PARTY = 6

CLASS_CHOICES = [
    "Unknown",
    "Archer",
    "Bard",
    "Beastmaster",
    "Cleric",
    "Druid",
    "Elementalist",
    "Enchanter",
    "Fighter",
    "Inquisitor",
    "Monk",
    "Necromancer",
    "Paladin",
    "Ranger",
    "Rogue",
    "Shadowknight",
    "Shaman",
    "Spellblade",
    "Wizard",
]

CLASS_COLORS = {
    "Unknown": "#64748b",
    "Archer": "#7faa3d",
    "Bard": "#d76ac9",
    "Beastmaster": "#b8793f",
    "Cleric": "#7cb8ff",
    "Druid": "#5dbb63",
    "Elementalist": "#e8793e",
    "Enchanter": "#9b5de5",
    "Fighter": "#d24a43",
    "Inquisitor": "#8f6fd1",
    "Monk": "#4caf73",
    "Necromancer": "#8b5cf6",
    "Paladin": "#e8c47a",
    "Ranger": "#6fa34a",
    "Rogue": "#d4a63a",
    "Shadowknight": "#76507d",
    "Shaman": "#19a79c",
    "Spellblade": "#4f9fbd",
    "Wizard": "#6d83ff",
}

CLASS_ABBREV = {
    "Unknown": "?",
    "Archer": "ARC",
    "Bard": "BRD",
    "Beastmaster": "BST",
    "Cleric": "CLR",
    "Druid": "DRU",
    "Elementalist": "ELE",
    "Enchanter": "ENC",
    "Fighter": "FTR",
    "Inquisitor": "INQ",
    "Monk": "MNK",
    "Necromancer": "NEC",
    "Paladin": "PAL",
    "Ranger": "RNG",
    "Rogue": "ROG",
    "Shadowknight": "SK",
    "Shaman": "SHM",
    "Spellblade": "SPB",
    "Wizard": "WIZ",
}


def app_config_path() -> Path:
    root = Path(os.getenv("APPDATA", Path.home())) / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root / "config.json"


DEFAULT_CONFIG = {
    "party": ["", "", "", "", "", ""],
    "party_classes": ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown"],
    "party_pets": ["", "", "", "", "", ""],
    "self_name": "",
    "combat_ocr_region": None,
    "overlay": {
        "x": 40,
        "y": 140,
        "w": 640,
        "h": 360,
        "opacity": 92,
        "locked": False,
        "compact": False,
        "scale": 100,
    },
    "capture_interval_ms": 300,
    "encounter_timeout_s": 8,
    "continuous_session": True,
    "combat_ocr_region_native": False,
}


def deep_copy_default() -> dict:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def load_config() -> dict:
    path = app_config_path()
    cfg = deep_copy_default()
    if not path.exists():
        return cfg
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        cfg.update(loaded)
        cfg["overlay"].update(loaded.get("overlay", {}))
        party = list(loaded.get("party", cfg["party"]))[:MAX_PARTY]
        cfg["party"] = party + [""] * (MAX_PARTY - len(party))
        classes = list(loaded.get("party_classes", cfg["party_classes"]))[:MAX_PARTY]
        cfg["party_classes"] = classes + ["Unknown"] * (MAX_PARTY - len(classes))
        pets = list(loaded.get("party_pets", cfg["party_pets"]))[:MAX_PARTY]
        cfg["party_pets"] = pets + [""] * (MAX_PARTY - len(pets))
        if loaded.get("ocr_region") and not loaded.get("combat_ocr_region"):
            cfg["combat_ocr_region"] = loaded["ocr_region"]
        if not loaded.get("combat_ocr_region") and loaded.get("self_ocr_region") and loaded.get("party_ocr_region"):
            a = loaded["self_ocr_region"]
            b = loaded["party_ocr_region"]
            left = min(a["left"], b["left"])
            top = min(a["top"], b["top"])
            right = max(a["left"] + a["width"], b["left"] + b["width"])
            bottom = max(a["top"] + a["height"], b["top"] + b["height"])
            cfg["combat_ocr_region"] = {
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            }
        if not normalize_line(cfg.get("self_name", "")) and normalize_line(cfg["party"][0]):
            cfg["self_name"] = normalize_line(cfg["party"][0])
        return cfg
    except Exception:
        return cfg


def save_config(cfg: dict) -> None:
    app_config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


@dataclass
class PlayerStats:
    name: str
    damage: int = 0
    hits: int = 0
    max_hit: int = 0

    def add(self, amount: int) -> None:
        self.damage += amount
        self.hits += 1
        self.max_hit = max(self.max_hit, amount)


@dataclass
class Encounter:
    party: list[str]
    started_at: float | None = None
    last_damage_at: float | None = None
    ended_at: float | None = None
    stats: dict[str, PlayerStats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.reset(self.party)

    def reset(self, party: list[str] | None = None) -> None:
        if party is not None:
            self.party = [p for p in party if p]
        self.started_at = None
        self.last_damage_at = None
        self.ended_at = None
        self.stats = {p: PlayerStats(p) for p in self.party}

    @property
    def active(self) -> bool:
        return self.started_at is not None and self.ended_at is None

    def duration(self, now: float | None = None) -> float:
        if self.started_at is None:
            return 0.0
        endpoint = self.ended_at or now or time.time()
        return max(0.1, endpoint - self.started_at)

    def add_damage(self, player: str, amount: int, timestamp: float, timeout_s: int, auto_reset: bool = True) -> None:
        if auto_reset and self.last_damage_at is not None and timestamp - self.last_damage_at > timeout_s:
            self.reset(self.party)
        if self.started_at is None:
            self.started_at = timestamp
        self.ended_at = None
        self.last_damage_at = timestamp
        if player not in self.stats:
            self.stats[player] = PlayerStats(player)
        self.stats[player].add(amount)

    def maybe_end(self, now: float, timeout_s: int, allow_end: bool = True) -> None:
        if allow_end and self.active and self.last_damage_at is not None and now - self.last_damage_at > timeout_s:
            self.ended_at = self.last_damage_at


DAMAGE_AMOUNT_RE = re.compile(
    r"\bfor\s*[-–—:]?\s*([\d,]+)\b",
    re.IGNORECASE,
)
DAMAGE_WORD_RE = re.compile(r"\b(?:damage|point|points)\b", re.IGNORECASE)



def normalize_line(line: str) -> str:
    line = line.replace("|", "I")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def stitch_wrapped_damage_lines(lines: list[str]) -> list[str]:
    src = [normalize_line(x) for x in lines if normalize_line(x)]
    out: list[str] = []
    i = 0
    while i < len(src):
        line = src[i]
        unfinished = bool(
            re.search(r"\bfor\s+[\d,]+\s+(?:point|points)\s+of\b", line, re.IGNORECASE)
            and not re.search(r"\bdamage\b", line, re.IGNORECASE)
        )
        if unfinished:
            combined = line
            j = i + 1
            while j < len(src) and j <= i + 2:
                combined += " " + src[j]
                if re.search(r"\bdamage\b", combined, re.IGNORECASE):
                    break
                j += 1
            out.append(normalize_line(combined))
            i = j + 1
            continue
        if re.match(r"^(?:[A-Za-z]+\s+)?damage[.!]?$", line, re.IGNORECASE) and out:
            out[-1] = normalize_line(out[-1] + " " + line)
        else:
            out.append(line)
        i += 1
    return out


def clean_actor_token(token: str) -> str:
    token = token.strip(" \"'‘’`|:;,.!?[](){}<>")
    token = re.sub(r"(?:'s|’s)$", "", token, flags=re.IGNORECASE)
    return token


def fuzzy_party_actor(line: str, party: list[str]) -> str | None:
    stripped = line.lstrip(" \"'‘’`|:;,.!?[](){}<>")
    if not stripped:
        return None
    first = stripped.split()[0]
    actor = clean_actor_token(first)
    if not actor:
        return None
    best_name = None
    best_score = 0.0
    for name in [p for p in party if p]:
        score = SequenceMatcher(None, actor.lower(), name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_name = name
    if best_name and best_score >= 0.76:
        return best_name
    return None


def is_self_actor(line: str) -> bool:
    stripped = line.lstrip(" \"'‘’`|:;,.!?[](){}<>")
    if not stripped:
        return False
    token = clean_actor_token(stripped.split()[0]).lower()
    token_alpha = re.sub(r"[^a-z0-9]", "", token)
    if token_alpha in {"you", "your", "vou", "vour", "y0u", "yur", "ycur", "youf"}:
        return True
    return max(
        SequenceMatcher(None, token_alpha, "you").ratio(),
        SequenceMatcher(None, token_alpha, "your").ratio(),
    ) >= 0.66


def split_pet_aliases(value: str) -> list[str]:
    """Allow comma/semicolon-separated pet names for one owner."""
    return [
        normalize_line(part)
        for part in re.split(r"[,;]", value or "")
        if normalize_line(part)
    ]


def fuzzy_pet_owner(line: str, pet_owner_map: dict[str, str] | None) -> str | None:
    """Map a named pet at the start of an outgoing combat line to its owner."""
    if not pet_owner_map:
        return None
    stripped = line.lstrip(" \"'‘’`|:;,.!?[](){}<>")
    if not stripped:
        return None

    # Most MnM pet names are one token, but test several leading words so a
    # multi-word pet name also works. Possessives such as "Flamey's" work too.
    words = stripped.split()
    candidates: list[str] = []
    for n in range(1, min(4, len(words)) + 1):
        prefix = " ".join(words[:n])
        prefix = re.sub(r"(?:'s|’s)$", "", prefix, flags=re.IGNORECASE)
        candidates.append(clean_actor_token(prefix))

    best_owner = None
    best_score = 0.0
    for pet_name, owner in pet_owner_map.items():
        pet_norm = normalize_line(pet_name)
        if not pet_norm or not owner:
            continue
        for candidate in candidates:
            score = SequenceMatcher(None, candidate.lower(), pet_norm.lower()).ratio()
            if score > best_score:
                best_score = score
                best_owner = owner

    if best_owner and best_score >= 0.78:
        return best_owner
    return None

def parse_damage_line(line: str, party: list[str], self_name: str, pet_owner_map: dict[str, str] | None = None) -> tuple[str, int] | None:
    """Parse outgoing MnM damage while tolerating common OCR damage."""
    line = normalize_line(line)
    actor_line = line.lstrip(" \"'‘’`|:;,.!?[](){}<>")
    amount_match = DAMAGE_AMOUNT_RE.search(actor_line)
    if not amount_match or not DAMAGE_WORD_RE.search(actor_line):
        return None
    amount = int(amount_match.group(1).replace(",", ""))
    if amount <= 0:
        return None
    if is_self_actor(actor_line):
        # MnM writes the local player as You/Your. Always attribute that to
        # the configured character, and recover gracefully if an older config
        # literally stored "You" in the character-name field.
        mapped_self = normalize_line(self_name)
        if not mapped_self or mapped_self.lower() in {"you", "your", "your pet"}:
            mapped_self = next((p for p in party if normalize_line(p)), "You")
        return mapped_self, amount
    actor = fuzzy_party_actor(actor_line, party)
    if actor:
        return actor, amount

    pet_owner = fuzzy_pet_owner(actor_line, pet_owner_map)
    if pet_owner:
        return pet_owner, amount
    return None


def line_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_line(a).lower(), normalize_line(b).lower()).ratio()


def new_lines_from_frames(previous: list[str], current: list[str]) -> list[str]:
    """Return lines that are genuinely new, even when chat scrolls quickly.

    v0.8.7 uses one-to-one fuzzy matching rather than assuming the old frame
    must be a prefix/suffix of the new frame. This is much more stable for MnM
    chat panes where several lines can scroll between OCR captures. Repeated
    identical attacks are preserved because each prior line can match only once.
    """
    prev = [normalize_line(x) for x in previous if normalize_line(x)]
    curr = [normalize_line(x) for x in current if normalize_line(x)]
    if not curr:
        return []
    if not prev:
        return curr

    unused = set(range(len(prev)))
    fresh: list[str] = []
    for line in curr:
        best_idx = None
        best_score = 0.0
        for idx in unused:
            score = line_similarity(line, prev[idx])
            if score > best_score:
                best_score = score
                best_idx = idx
        # OCR often changes a letter or two between frames. 0.74 is forgiving
        # enough for that drift without collapsing distinct combat lines.
        if best_idx is not None and best_score >= 0.74:
            unused.remove(best_idx)
        else:
            fresh.append(line)
    return fresh


class OCRWorker(QThread):
    # Emit independent OCR frames for the upper (Other) and lower (My) chat panes.
    # Keeping them separate is important: merging several OCR passes caused the
    # frame-diff code to lose live lines, especially You/Your Pet messages.
    text_frame = Signal(object)
    error = Signal(str)

    def __init__(self, region: dict, interval_ms: int = 650):
        super().__init__()
        self.region = dict(region)
        self.interval_ms = interval_ms
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        try:
            import mss
            import pytesseract
            from concurrent.futures import ThreadPoolExecutor
            from PIL import Image, ImageFilter, ImageOps, ImageChops
        except Exception as exc:
            self.error.emit(f"OCR dependencies are missing: {exc}")
            return

        if os.name == "nt":
            candidates: list[Path] = []

            env_tess = os.getenv("MNM_TESSERACT_PATH", "").strip()
            if env_tess:
                candidates.append(Path(env_tess))

            # The streamlined installer records the exact Tesseract executable
            # it selected, whether that is an existing system install or the
            # copy installed with MnM Party Meter.
            local_root = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
            tess_path_file = local_root / "state" / "tesseract_path.txt"
            try:
                if tess_path_file.exists():
                    recorded = tess_path_file.read_text(encoding="utf-8").strip()
                    if recorded:
                        candidates.append(Path(recorded))
            except Exception:
                pass

            # True standalone builds place Tesseract beside the application.
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).resolve().parent
                candidates.extend([
                    exe_dir / "Tesseract-OCR" / "tesseract.exe",
                    exe_dir / "tesseract" / "tesseract.exe",
                ])
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    candidates.extend([
                        Path(meipass) / "Tesseract-OCR" / "tesseract.exe",
                        Path(meipass) / "tesseract" / "tesseract.exe",
                    ])

            script_dir = Path(__file__).resolve().parent
            candidates.extend([
                script_dir.parent / "runtime" / "Tesseract-OCR" / "tesseract.exe",
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ])

            for candidate in candidates:
                try:
                    if candidate.exists():
                        pytesseract.pytesseract.tesseract_cmd = str(candidate)
                        tessdata = candidate.parent / "tessdata"
                        if tessdata.exists():
                            os.environ["TESSDATA_PREFIX"] = str(tessdata)
                        break
                except Exception:
                    continue

        def prep_text(img):
            # MnM mixes white/light-gray player text with orange pet text over a
            # translucent game background. Max-channel luminance preserves the
            # orange text, while a blurred-background difference lifts faint gray
            # strokes that would otherwise disappear against bright scenery.
            r, g, b = img.split()
            bright = ImageChops.lighter(ImageChops.lighter(r, g), b)
            bright = ImageOps.autocontrast(bright, cutoff=1)

            bg = bright.filter(ImageFilter.GaussianBlur(radius=3.0))
            detail = ImageChops.difference(bright, bg)
            detail = ImageOps.autocontrast(detail, cutoff=1)
            # Screen blend equivalent: keep strong colored/white luminance and
            # add local text edges. This avoids a brittle hard threshold.
            proc = ImageChops.lighter(bright, detail)
            proc = ImageOps.autocontrast(proc, cutoff=1)
            proc = ImageOps.invert(proc)
            proc = proc.resize((proc.width * 3, proc.height * 3))
            proc = proc.filter(ImageFilter.UnsharpMask(radius=0.9, percent=150, threshold=1))
            return proc

        def ocr_lines(img):
            proc = prep_text(img)
            txt = pytesseract.image_to_string(
                proc,
                config="--psm 6 -c preserve_interword_spaces=1 -c textord_space_size_is_variable=1",
            )
            return [normalize_line(x) for x in txt.splitlines() if normalize_line(x)]

        with mss.mss() as sct, ThreadPoolExecutor(max_workers=2) as pool:
            while self._running:
                started = time.time()
                try:
                    raw = sct.grab(self.region)
                    image = Image.frombytes("RGB", raw.size, raw.rgb)
                    w, h = image.size

                    # The user's selected box spans Other above My. Read each
                    # pane as its own stable text block instead of mixing OCR
                    # outputs into one unstable frame.
                    split = int(h * 0.50)
                    upper = image.crop((0, 0, w, min(h, split + 16)))
                    lower = image.crop((0, max(0, split - 16), w, h))

                    # OCR the two panes concurrently. Tesseract runs as separate
                    # subprocesses, so this cuts wall-clock scan latency on
                    # multi-core systems and gives fast-scrolling lines a better
                    # chance of being sampled before they disappear.
                    upper_future = pool.submit(ocr_lines, upper)
                    lower_future = pool.submit(ocr_lines, lower)
                    upper_lines = upper_future.result()
                    lower_lines = lower_future.result()
                    scan_ms = int((time.time() - started) * 1000)
                    self.text_frame.emit({
                        "upper": upper_lines,
                        "lower": lower_lines,
                        "scan_ms": scan_ms,
                    })
                except Exception as exc:
                    self.error.emit(str(exc))
                    return
                elapsed_ms = int((time.time() - started) * 1000)
                # Other (upper) is normally the high-traffic pane. If it is
                # already carrying a dense block of text, temporarily shorten
                # the next sampling interval by 20%. The user's configured
                # refresh remains the normal cadence; this is only a burst
                # response to a busy pane.
                busy_upper = len(upper_lines) >= 7
                target_ms = max(180, int(self.interval_ms * 0.80)) if busy_upper else self.interval_ms
                self.msleep(max(30, target_ms - elapsed_ms))


class RegionSelector(QWidget):
    region_selected = Signal(dict)

    def __init__(self, prompt: str):
        super().__init__(None)
        self.prompt = prompt
        self.start = QPoint()
        self.end = QPoint()
        self.dragging = False
        virtual = QRect()
        for screen in QGuiApplication.screens():
            virtual = virtual.united(screen.geometry())
        self.setGeometry(virtual)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            rect = QRect(self.start, self.end).normalized()
            if rect.width() > 120 and rect.height() > 60:
                global_top_left = self.mapToGlobal(rect.topLeft())
                # Qt selection coordinates are device-independent pixels, while
                # MSS captures native desktop pixels. On Windows display scaling
                # (125/150/175/200%), using Qt coordinates directly captures the
                # wrong part of the game. Convert the selected rectangle to the
                # screen's native pixel space before saving it.
                screen = QGuiApplication.screenAt(global_top_left)
                dpr = float(screen.devicePixelRatio()) if screen else 1.0
                self.region_selected.emit(
                    {
                        "left": round(global_top_left.x() * dpr),
                        "top": round(global_top_left.y() * dpr),
                        "width": round(rect.width() * dpr),
                        "height": round(rect.height() * dpr),
                    }
                )
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self.start != self.end:
            rect = QRect(self.start, self.end).normalized()
            painter.fillRect(rect, QColor(255, 255, 255, 28))
            painter.setPen(QPen(QColor(132, 211, 255), 2))
            painter.drawRect(rect)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 14, 600))
        painter.drawText(30, 45, self.prompt)


class DamageRow(QFrame):
    def __init__(self, index: int):
        super().__init__()
        self.index = index
        self._fraction = 0.0
        self._color = "#64748b"
        self._compact = False
        self._scale = 100

        self.setObjectName("rowFrame")
        self.setMinimumHeight(48)

        self.accent = QFrame()
        self.accent.setFixedWidth(5)
        self.accent.setStyleSheet("background:#64748b; border-radius:2px;")

        self.rank = QLabel(str(index + 1))
        self.rank.setAlignment(Qt.AlignCenter)
        self.rank.setFixedWidth(28)

        self.badge = QLabel("?")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedWidth(42)
        self.badge.setObjectName("classBadge")

        self.name = QLabel("—")
        self.name.setObjectName("nameLabel")

        self.damage = QLabel("0")
        self.damage.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.damage.setObjectName("damageLabel")

        self.bar_track = QFrame()
        self.bar_track.setObjectName("barTrack")
        self.bar_track.setMinimumHeight(10)
        self.bar_track.setMaximumHeight(10)
        self.bar_track.setStyleSheet(
            "QFrame#barTrack {background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.08); border-radius: 5px;}"
        )
        self.bar_fill = QFrame(self.bar_track)
        self.bar_fill.setObjectName("barFill")
        self.bar_fill.setGeometry(0, 0, 0, 8)
        self.bar_fill.setStyleSheet("background:#64748b; border-radius:4px;")

        self.meta = QLabel("0.0 DPS • 0.0%")
        self.meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.meta.setObjectName("metaLabel")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self.rank)
        header.addWidget(self.badge)
        header.addWidget(self.name, 1)
        header.addWidget(self.damage)

        lower = QHBoxLayout()
        lower.setContentsMargins(0, 0, 0, 0)
        lower.setSpacing(10)
        lower.addWidget(self.bar_track, 1)
        lower.addWidget(self.meta)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        right.addLayout(header)
        right.addLayout(lower)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)
        outer.addWidget(self.accent)
        outer.addLayout(right, 1)

        self.apply_style()
        self.apply_display_settings(compact=False, scale=100)

    def refresh_bar_geometry(self) -> None:
        track = self.bar_track.contentsRect()
        fill_width = int(max(0, track.width() * self._fraction))
        self.bar_fill.setGeometry(track.x(), track.y(), fill_width, track.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_bar_geometry()

    def apply_style(self) -> None:
        rgba = hex_to_rgba(self._color, 0.22)
        border = hex_to_rgba(self._color, 0.60)
        text_soft = "#b7c1cc"
        self.setStyleSheet(
            f"""
            QFrame#rowFrame {{
                background: rgba(9, 13, 18, 185);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }}
            QLabel {{
                color: #edf2f7;
                background: transparent;
            }}
            QLabel#nameLabel {{
                font-weight: 650;
            }}
            QLabel#damageLabel {{
                color: #ffffff;
                font-weight: 700;
            }}
            QLabel#metaLabel {{
                color: {text_soft};
            }}
            QLabel#classBadge {{
                color: #ffffff;
                background: {rgba};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 2px 4px;
                font-weight: 700;
            }}
            """
        )
        self.accent.setStyleSheet(f"background:{self._color}; border-radius:2px;")
        self.bar_fill.setStyleSheet(f"background:{self._color}; border-radius:4px;")

    def apply_display_settings(self, compact: bool, scale: int) -> None:
        self._compact = compact
        self._scale = scale
        base = max(80, scale)
        name_pt = 10 if compact else 11
        meta_pt = 8 if compact else 9
        damage_pt = 11 if compact else 12
        badge_pt = 7 if compact else 8
        row_h = int((42 if compact else 58) * base / 100)
        outer_margin = int((6 if compact else 8) * base / 100)
        spacing = int((8 if compact else 10) * base / 100)

        self.setMinimumHeight(row_h)
        self.rank.setFixedWidth(int(26 * base / 100))
        self.badge.setFixedWidth(int(40 * base / 100))
        self.bar_track.setMinimumHeight(int((8 if compact else 10) * base / 100))
        self.bar_track.setMaximumHeight(int((8 if compact else 10) * base / 100))
        layout = self.layout()
        if isinstance(layout, QHBoxLayout):
            layout.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
            layout.setSpacing(spacing)

        self.rank.setFont(QFont("Segoe UI", name_pt, 600))
        self.badge.setFont(QFont("Segoe UI", badge_pt, 700))
        self.name.setFont(QFont("Segoe UI", name_pt, 600))
        self.damage.setFont(QFont("Segoe UI", damage_pt, 700))
        self.meta.setFont(QFont("Segoe UI", meta_pt, 500))
        self.updateGeometry()
        self.update()

    def update_stats(
        self,
        rank: int,
        name: str,
        damage: int,
        dps: float,
        share: float,
        leader_damage: int,
        player_class: str,
        compact: bool,
        scale: int,
    ) -> None:
        self.rank.setText(str(rank))
        self.name.setText(name)
        self.damage.setText(f"{damage:,}")
        if compact:
            self.meta.setText(f"{share:.1f}%")
        else:
            self.meta.setText(f"{dps:.1f} DPS • {share:.1f}%")
        self._fraction = (damage / leader_damage) if leader_damage else 0.0
        self._color = CLASS_COLORS.get(player_class or "Unknown", CLASS_COLORS["Unknown"])
        self.badge.setText(CLASS_ABBREV.get(player_class or "Unknown", "?"))
        self.apply_style()
        self.apply_display_settings(compact, scale)
        self.refresh_bar_geometry()


class Overlay(QWidget):
    moved_or_resized = Signal()

    def __init__(self, cfg: dict):
        super().__init__(None)
        self.cfg = cfg
        self._locked = bool(cfg["overlay"].get("locked", False))
        self._compact = bool(cfg["overlay"].get("compact", False))
        self._scale = int(cfg["overlay"].get("scale", 100))
        self._drag_start: Optional[QPoint] = None
        self._window_start: Optional[QPoint] = None
        self._resize_start: Optional[QPoint] = None
        self._start_geom: Optional[QRect] = None
        self._mode: Optional[str] = None
        self._grip_size = 18
        self.party_classes: dict[str, str] = {}

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("MnM Party Meter")
        self.setMinimumSize(360, 210)

        self.root = QFrame(self)
        self.root.setObjectName("panel")

        self.title = QLabel("Damage Done")
        self.title.setObjectName("title")
        self.timer_chip = QLabel("00:00")
        self.timer_chip.setObjectName("chip")
        self.status_chip = QLabel("WAITING")
        self.status_chip.setObjectName("chipMuted")
        self.players_chip = QLabel("0 PLAYERS")
        self.players_chip.setObjectName("chipMuted")
        self.hint = QLabel("LOCKED" if self._locked else "DRAG TO MOVE • DRAG CORNER TO RESIZE")
        self.hint.setObjectName("subtle")

        header_left = QVBoxLayout()
        header_left.setContentsMargins(0, 0, 0, 0)
        header_left.setSpacing(1)
        header_left.addWidget(self.title)
        header_left.addWidget(self.hint)

        header_right = QHBoxLayout()
        header_right.setContentsMargins(0, 0, 0, 0)
        header_right.setSpacing(6)
        header_right.addWidget(self.players_chip)
        header_right.addWidget(self.status_chip)
        header_right.addWidget(self.timer_chip)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addLayout(header_left, 1)
        header.addLayout(header_right)

        self.rows = [DamageRow(i) for i in range(MAX_PARTY)]

        self.footer_left = QLabel("Party-only • OCR overlay")
        self.footer_left.setObjectName("subtle")
        self.footer_right = QLabel(f"v{APP_VERSION}")
        self.footer_right.setObjectName("subtle")
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.footer_left)
        footer.addStretch(1)
        footer.addWidget(self.footer_right)

        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)
        root_layout.addLayout(header)
        for row in self.rows:
            root_layout.addWidget(row)
        root_layout.addLayout(footer)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.root)

        o = cfg["overlay"]
        self.setGeometry(o["x"], o["y"], o["w"], o["h"])
        self.setWindowOpacity(o.get("opacity", 92) / 100.0)
        self.refresh_panel_style()
        self.apply_scale_and_mode(self._scale, self._compact)

    def set_party_classes(self, mapping: dict[str, str]) -> None:
        self.party_classes = dict(mapping)

    def refresh_panel_style(self) -> None:
        self.root.setStyleSheet(
            """
            QFrame#panel {
                background-color: rgba(8, 12, 18, 212);
                border: 1px solid rgba(160, 190, 220, 90);
                border-radius: 14px;
            }
            QLabel { color: #e8eef7; font-family: 'Segoe UI'; background: transparent; }
            QLabel#title { font-size: 24px; font-weight: 760; color: #f8fbff; }
            QLabel#subtle { color: #aeb8c4; font-size: 11px; }
            QLabel#chip {
                background: rgba(31, 41, 55, 185);
                border: 1px solid rgba(120, 159, 198, 95);
                border-radius: 10px;
                padding: 4px 8px;
                color: #f8fbff;
                font-weight: 700;
            }
            QLabel#chipMuted {
                background: rgba(31, 41, 55, 150);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 4px 8px;
                color: #d2dae3;
                font-weight: 600;
            }
            """
        )

    def apply_scale_and_mode(self, scale: int, compact: bool) -> None:
        self._scale = int(max(80, min(160, scale)))
        self._compact = compact
        base = self._scale
        margin = int(12 * base / 100)
        spacing = int((6 if compact else 8) * base / 100)
        title_pt = max(13, int((16 if compact else 18) * base / 100))
        subtle_pt = max(8, int((8 if compact else 9) * base / 100))
        chip_pt = max(8, int((9 if compact else 10) * base / 100))

        root_layout = self.root.layout()
        if isinstance(root_layout, QVBoxLayout):
            root_layout.setContentsMargins(margin, margin, margin, margin)
            root_layout.setSpacing(spacing)

        self.title.setFont(QFont("Segoe UI", title_pt, 750))
        self.hint.setFont(QFont("Segoe UI", subtle_pt, 500))
        self.footer_left.setFont(QFont("Segoe UI", subtle_pt, 500))
        self.footer_right.setFont(QFont("Segoe UI", subtle_pt, 500))
        self.timer_chip.setFont(QFont("Segoe UI", chip_pt, 700))
        self.status_chip.setFont(QFont("Segoe UI", chip_pt, 650))
        self.players_chip.setFont(QFont("Segoe UI", chip_pt, 650))

        self.footer_left.setVisible(not compact)
        self.footer_right.setVisible(not compact)
        self.hint.setText("LOCKED" if self._locked else "DRAG TO MOVE • DRAG CORNER TO RESIZE")

        for row in self.rows:
            row.apply_display_settings(compact, self._scale)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.apply_click_through)

    def apply_click_through(self) -> None:
        if os.name != "nt":
            return
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if self._locked:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style &= ~WS_EX_TRANSPARENT
            style |= WS_EX_LAYERED
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.hint.setText("LOCKED" if self._locked else "DRAG TO MOVE • DRAG CORNER TO RESIZE")
        self.apply_click_through()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.apply_scale_and_mode(self._scale, self._compact)

    def set_scale(self, scale: int) -> None:
        self._scale = scale
        self.apply_scale_and_mode(self._scale, self._compact)

    def _resize_zone(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - self._grip_size and pos.y() >= self.height() - self._grip_size

    def mousePressEvent(self, event: QMouseEvent):
        if self._locked or event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        self._start_geom = self.geometry()
        if self._resize_zone(pos):
            self._mode = "resize"
            self._resize_start = event.globalPosition().toPoint()
        else:
            self._mode = "move"
            self._drag_start = event.globalPosition().toPoint()
            self._window_start = self.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._locked:
            return
        pos = event.position().toPoint()
        if self._mode == "resize" and self._resize_start and self._start_geom:
            delta = event.globalPosition().toPoint() - self._resize_start
            new_w = max(self.minimumWidth(), self._start_geom.width() + delta.x())
            new_h = max(self.minimumHeight(), self._start_geom.height() + delta.y())
            self.setGeometry(self._start_geom.x(), self._start_geom.y(), new_w, new_h)
            return
        if self._mode == "move" and self._drag_start and self._window_start:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._window_start + delta)
            return
        self.setCursor(Qt.SizeFDiagCursor if self._resize_zone(pos) else Qt.SizeAllCursor)

    def mouseReleaseEvent(self, event):
        if self._mode is not None:
            self._mode = None
            self._drag_start = None
            self._window_start = None
            self._resize_start = None
            self._start_geom = None
            self.setCursor(Qt.ArrowCursor)
            self.moved_or_resized.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._locked:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(160, 190, 220, 130), 2))
        x2 = self.width() - 6
        y2 = self.height() - 6
        for i in range(3):
            painter.drawLine(x2 - i * 5, y2, x2, y2 - i * 5)

    def update_encounter(self, encounter: Encounter) -> None:
        duration = encounter.duration()
        mins = int(duration) // 60
        secs = int(duration) % 60
        self.timer_chip.setText(f"{mins:02d}:{secs:02d}")
        self.status_chip.setText("LIVE" if encounter.active else ("ENDED" if encounter.started_at else "WAITING"))

        players = list(encounter.stats.values())
        players.sort(key=lambda s: s.damage, reverse=True)
        total = sum(p.damage for p in players)
        leader = players[0].damage if players else 0
        visible_players = [p for p in players if p.name]
        self.players_chip.setText(f"{len(visible_players)} PLAYERS")

        for i, row in enumerate(self.rows):
            if i < len(visible_players):
                p = visible_players[i]
                share = (p.damage / total * 100.0) if total else 0.0
                dps = p.damage / duration if encounter.started_at else 0.0
                row.show()
                row.update_stats(
                    i + 1,
                    p.name,
                    p.damage,
                    dps,
                    share,
                    leader,
                    self.party_classes.get(p.name, "Unknown"),
                    self._compact,
                    self._scale,
                )
            else:
                row.hide()


class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.encounter = Encounter([p for p in self.cfg["party"] if p])
        self.previous_ocr_frames: dict[str, list[str]] = {"upper": [], "lower": []}
        self.last_raw_ocr_frames: dict[str, list[str]] = {"upper": [], "lower": []}
        self.ocr_baseline_pending = True
        self.recent_damage_events: list[tuple[float, str, int, str, str]] = []
        self.worker: OCRWorker | None = None
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self.demo_tick)

        self.overlay = Overlay(self.cfg)
        self.overlay.moved_or_resized.connect(self.persist_overlay_geometry)
        self.overlay.show()

        self.setWindowTitle(f"MnM Party Meter — Setup v{APP_VERSION}")
        self.resize(700, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        intro = QLabel(
            "v1.0.2: Keep TWO MnM combat windows (Other above My) inside ONE OCR selection. "
            "The meter reads the panes independently and can sample faster when Other becomes busy. "
            "For charm pets, choose a creature you are not also fighting and enter that creature name in Pet name(s)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        party_box = QFrame()
        party_layout = QGridLayout(party_box)
        party_layout.addWidget(QLabel("#"), 0, 0)
        party_layout.addWidget(QLabel("Name"), 0, 1)
        party_layout.addWidget(QLabel("Class"), 0, 2)
        party_layout.addWidget(QLabel("Pet name(s)"), 0, 3)
        self.party_edits: list[QLineEdit] = []
        self.class_edits: list[QComboBox] = []
        self.pet_edits: list[QLineEdit] = []
        for i in range(MAX_PARTY):
            edit = QLineEdit(self.cfg["party"][i])
            edit.setPlaceholderText(f"Party member {i+1}")
            cls = QComboBox()
            cls.addItems(CLASS_CHOICES)
            current_cls = self.cfg["party_classes"][i] if i < len(self.cfg["party_classes"]) else "Unknown"
            idx = max(0, cls.findText(current_cls))
            cls.setCurrentIndex(idx)
            pet_edit = QLineEdit(self.cfg["party_pets"][i] if i < len(self.cfg["party_pets"]) else "")
            pet_edit.setPlaceholderText("Optional; comma-separated")
            pet_edit.setToolTip("Enter the pet's combat-log name. Use commas if this character may have multiple named pets.")
            self.party_edits.append(edit)
            self.class_edits.append(cls)
            self.pet_edits.append(pet_edit)
            party_layout.addWidget(QLabel(str(i + 1)), i + 1, 0)
            party_layout.addWidget(edit, i + 1, 1)
            party_layout.addWidget(cls, i + 1, 2)
            party_layout.addWidget(pet_edit, i + 1, 3)
        layout.addWidget(party_box)

        self.self_edit = QLineEdit(self.cfg.get("self_name", ""))
        form = QFormLayout()
        form.addRow("Your character name (e.g. Prussy)", self.self_edit)
        self.interval = QSpinBox()
        self.interval.setRange(200, 2500)
        self.interval.setSingleStep(25)
        self.interval.setValue(self.cfg["capture_interval_ms"])
        self.interval.setSuffix(" ms")
        self.interval.setToolTip("Recommended: 300 ms. Use 250 ms for maximum catch rate; 400–450 ms if CPU usage is high.")
        form.addRow("OCR refresh", self.interval)
        self.timeout = QSpinBox()
        self.timeout.setRange(3, 30)
        self.timeout.setValue(self.cfg["encounter_timeout_s"])
        self.timeout.setSuffix(" sec")
        form.addRow("Encounter timeout", self.timeout)
        self.continuous_check = QCheckBox("Keep one running session across mobs")
        self.continuous_check.setChecked(bool(self.cfg.get("continuous_session", True)))
        self.continuous_check.setToolTip("When checked, the meter keeps accumulating damage until you press Reset encounter.")
        form.addRow("Session mode", self.continuous_check)
        layout.addLayout(form)

        self.combat_region_label = QLabel(self.region_text("combat_ocr_region"))
        self.combat_region_button = QPushButton("Select BOTH combat windows")
        self.combat_region_button.clicked.connect(self.select_combat_region)
        region_grid = QGridLayout()
        region_grid.addWidget(self.combat_region_button, 0, 0)
        region_grid.addWidget(self.combat_region_label, 0, 1)
        layout.addLayout(region_grid)

        overlay_controls = QGridLayout()
        self.lock_check = QCheckBox("Lock/click-through")
        self.lock_check.setChecked(self.cfg["overlay"].get("locked", False))
        self.lock_check.toggled.connect(self.toggle_lock)
        overlay_controls.addWidget(self.lock_check, 0, 0)

        self.compact_check = QCheckBox("Compact mode")
        self.compact_check.setChecked(self.cfg["overlay"].get("compact", False))
        self.compact_check.toggled.connect(self.toggle_compact)
        overlay_controls.addWidget(self.compact_check, 0, 1)

        overlay_controls.addWidget(QLabel("Opacity"), 1, 0)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(45, 100)
        self.opacity.setValue(self.cfg["overlay"].get("opacity", 92))
        self.opacity.valueChanged.connect(self.set_opacity)
        overlay_controls.addWidget(self.opacity, 1, 1)

        overlay_controls.addWidget(QLabel("UI scale"), 2, 0)
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(80, 160)
        self.scale_slider.setValue(int(self.cfg["overlay"].get("scale", 100)))
        self.scale_slider.valueChanged.connect(self.set_overlay_scale)
        overlay_controls.addWidget(self.scale_slider, 2, 1)
        self.scale_label = QLabel(f"{self.scale_slider.value()}%")
        overlay_controls.addWidget(self.scale_label, 2, 2)

        layout.addLayout(overlay_controls)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start OCR")
        self.start_button.clicked.connect(self.toggle_ocr)
        self.demo_button = QPushButton("Start demo")
        self.demo_button.clicked.connect(self.toggle_demo)
        self.reset_button = QPushButton("Reset encounter")
        self.reset_button.clicked.connect(self.reset_encounter)
        self.diag_button = QPushButton("Show OCR diagnostics")
        self.diag_button.clicked.connect(self.show_diagnostics)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.demo_button)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.diag_button)
        layout.addLayout(buttons)

        self.log_label = QLabel("Ready.")
        self.log_label.setWordWrap(True)
        self.log_label.setStyleSheet("color:#666;")
        layout.addWidget(self.log_label)
        layout.addStretch(1)

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start(250)
        self.apply_party_to_overlay()

    def region_text(self, key: str) -> str:
        r = self.cfg.get(key)
        if not r:
            return "No region selected"
        return f"{r['width']}×{r['height']} at {r['left']},{r['top']}"

    def current_party(self) -> list[str]:
        values = [normalize_line(e.text()) for e in self.party_edits]
        return [v for v in values if v]

    def current_party_class_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for edit, cls in zip(self.party_edits, self.class_edits):
            name = normalize_line(edit.text())
            if name:
                mapping[name] = cls.currentText() or "Unknown"
        return mapping

    def current_pet_owner_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for owner_edit, pet_edit in zip(self.party_edits, self.pet_edits):
            owner = normalize_line(owner_edit.text())
            if not owner:
                continue
            for pet_name in split_pet_aliases(pet_edit.text()):
                mapping[pet_name] = owner
        return mapping

    def save_current_settings(self) -> None:
        party_raw = [normalize_line(e.text()) for e in self.party_edits]
        self.cfg["party"] = party_raw
        self.cfg["party_classes"] = [c.currentText() or "Unknown" for c in self.class_edits]
        self.cfg["party_pets"] = [normalize_line(e.text()) for e in self.pet_edits]
        self.cfg["self_name"] = normalize_line(self.self_edit.text()) or normalize_line(self.party_edits[0].text()) or "You"
        self.cfg["capture_interval_ms"] = self.interval.value()
        self.cfg["encounter_timeout_s"] = self.timeout.value()
        self.cfg["continuous_session"] = self.continuous_check.isChecked()
        self.persist_overlay_geometry()
        save_config(self.cfg)

    def persist_overlay_geometry(self) -> None:
        g = self.overlay.geometry()
        self.cfg["overlay"].update({"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()})
        save_config(self.cfg)

    def set_opacity(self, value: int) -> None:
        self.cfg["overlay"]["opacity"] = value
        self.overlay.setWindowOpacity(value / 100.0)
        save_config(self.cfg)

    def set_overlay_scale(self, value: int) -> None:
        self.cfg["overlay"]["scale"] = int(value)
        self.scale_label.setText(f"{int(value)}%")
        self.overlay.set_scale(int(value))
        save_config(self.cfg)

    def toggle_lock(self, locked: bool) -> None:
        self.cfg["overlay"]["locked"] = locked
        self.overlay.set_locked(locked)
        save_config(self.cfg)

    def toggle_compact(self, compact: bool) -> None:
        self.cfg["overlay"]["compact"] = compact
        self.overlay.set_compact(compact)
        save_config(self.cfg)

    def select_combat_region(self) -> None:
        self.hide()
        self.overlay.hide()
        selector = RegionSelector(
            "Drag ONE rectangle around BOTH combat windows (OTHER + MY), including the text areas. Esc cancels."
        )
        self._selector = selector

        def selected(region: dict):
            self.cfg["combat_ocr_region"] = region
            self.cfg["combat_ocr_region_native"] = True
            save_config(self.cfg)
            self.combat_region_label.setText(self.region_text("combat_ocr_region"))
            self.show()
            self.overlay.show()

        def finished():
            if not self.isVisible():
                self.show()
                self.overlay.show()

        selector.region_selected.connect(selected)
        selector.destroyed.connect(finished)
        selector.show()
        selector.activateWindow()

    def apply_party_to_overlay(self) -> None:
        self.overlay.set_party_classes(self.current_party_class_map())

    def apply_party(self) -> None:
        party = self.current_party()
        self.encounter.reset(party)
        self.apply_party_to_overlay()
        self.save_current_settings()

    def toggle_ocr(self) -> None:
        if self.worker and self.worker.isRunning():
            self.stop_ocr()
            return
        if not self.cfg.get("combat_ocr_region"):
            QMessageBox.information(self, "Select combat area", "Select one rectangle containing BOTH MnM combat windows first.")
            return
        if not self.cfg.get("combat_ocr_region_native", False):
            QMessageBox.information(
                self,
                "Re-select combat area",
                "This saved region predates the Windows display-scaling fix. Please click 'Select BOTH combat windows' once more, then Start OCR."
            )
            return
        self.apply_party()
        if not self.current_party():
            QMessageBox.information(self, "Party names", "Enter at least your character name in the party list.")
            return
        self.previous_ocr_frames = {"upper": [], "lower": []}
        self.last_raw_ocr_frames = {"upper": [], "lower": []}
        self.ocr_baseline_pending = True
        self.last_scan_ms = 0
        self.recent_damage_events = []
        self.worker = OCRWorker(self.cfg["combat_ocr_region"], self.interval.value())
        self.worker.text_frame.connect(self.process_ocr_frame)
        self.worker.error.connect(self.ocr_error)
        self.worker.start()
        self.start_button.setText("Stop OCR")
        self.log_label.setText("OCR running on the combined combat area.")

    def stop_ocr(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker.wait(1500)
            self.worker = None
        self.start_button.setText("Start OCR")
        self.log_label.setText("OCR stopped.")

    def ocr_error(self, message: str) -> None:
        self.stop_ocr()
        QMessageBox.warning(
            self,
            "OCR error",
            f"OCR failed while reading the combined combat area:\n\n{message}\n\nIf this mentions Tesseract, install Tesseract OCR for Windows and restart the app. See README.md.",
        )

    def is_duplicate_damage(self, player: str, amount: int, line: str, now: float, source: str) -> bool:
        """Suppress cross-pane OCR duplicates without deleting real repeated hits.

        Persistence inside a single pane is already handled by frame-to-frame
        one-to-one matching. The short-lived fingerprint below is therefore
        intentionally cross-pane only. This matters for fast classes/pets: two
        genuine identical hits in Other should both count, while one event seen
        in the overlap between Other and My should count once.
        """
        canonical = normalize_line(line).lower()
        self.recent_damage_events = [e for e in self.recent_damage_events if now - e[0] <= 0.90]
        for ts, old_player, old_amount, old_line, old_source in self.recent_damage_events:
            if old_source == source:
                continue
            if old_player == player and old_amount == amount and now - ts <= 0.55:
                if SequenceMatcher(None, canonical, old_line).ratio() >= 0.78:
                    return True
        self.recent_damage_events.append((now, player, amount, canonical, source))
        return False

    def process_ocr_frame(self, frames: object) -> None:
        if not isinstance(frames, dict):
            # Compatibility guard for an unexpected/older worker payload.
            frames = {"upper": list(frames or []), "lower": []}

        self.last_scan_ms = int(frames.get("scan_ms", 0) or 0)
        self_name = normalize_line(self.self_edit.text()) or "You"
        party = self.current_party()
        pet_owner_map = self.current_pet_owner_map()
        parsed = []
        saw_fresh = []

        # After Start/Reset, the first complete OCR frame is a baseline only.
        # Everything already visible in both MnM combat panes is considered
        # pre-encounter text and must not be counted as new damage.
        if self.ocr_baseline_pending:
            for source in ("upper", "lower"):
                raw_lines = list(frames.get(source, []) or [])
                self.last_raw_ocr_frames[source] = raw_lines
                self.previous_ocr_frames[source] = stitch_wrapped_damage_lines(raw_lines)
            self.ocr_baseline_pending = False
            self.log_label.setText("READY — existing combat text ignored; waiting for new damage.")
            return

        for source in ("upper", "lower"):
            raw_lines = list(frames.get(source, []) or [])
            self.last_raw_ocr_frames[source] = raw_lines
            logical_lines = stitch_wrapped_damage_lines(raw_lines)
            previous = self.previous_ocr_frames.get(source, [])
            fresh = new_lines_from_frames(previous, logical_lines)
            self.previous_ocr_frames[source] = logical_lines
            saw_fresh.extend(fresh)

            for line in fresh:
                event = parse_damage_line(line, party, self_name, pet_owner_map)
                if not event:
                    continue
                player, amount = event
                now = time.time()
                if self.is_duplicate_damage(player, amount, line, now, source):
                    continue
                self.encounter.add_damage(
                    player, amount, now, self.timeout.value(),
                    auto_reset=not self.continuous_check.isChecked(),
                )
                parsed.append(f"{player} +{amount}")

        if parsed:
            self.log_label.setText("LIVE parsed: " + ", ".join(parsed[-8:]))
        elif saw_fresh:
            preview = " | ".join(saw_fresh[-4:])
            if len(preview) > 260:
                preview = preview[-260:]
            self.log_label.setText(f"OCR live: {preview} — no outgoing party damage matched.")

    def show_diagnostics(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"MnM Party Meter v{APP_VERSION} — OCR diagnostics")
        dialog.resize(900, 660)
        layout = QVBoxLayout(dialog)
        explainer = QLabel(
            f"v{APP_VERSION} maps named pet combat lines back to their owners. Enter each pet name in the Pet name(s) column; recognized outgoing damage is marked with ✓."
        )
        explainer.setWordWrap(True)
        layout.addWidget(explainer)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        party = self.current_party()
        pet_owner_map = self.current_pet_owner_map()
        self_name = normalize_line(self.self_edit.text()) or "You"
        mapped_self = self_name
        if not mapped_self or mapped_self.lower() in {"you", "your", "your pet"}:
            mapped_self = next((p for p in party if normalize_line(p)), "You")
        r = self.cfg.get("combat_ocr_region") or {}
        pet_map_text = ", ".join(f"{pet} -> {owner}" for pet, owner in pet_owner_map.items()) or "(none)"
        sections = [f"CAPTURE: {r.get('width','?')}x{r.get('height','?')} at {r.get('left','?')},{r.get('top','?')} native pixels\nSELF MAP: You / Your / Your pet -> {mapped_self}\nNAMED PET MAP: {pet_map_text}\nLAST OCR SCAN: {self.last_scan_ms} ms (target refresh {self.interval.value()} ms)"]
        for source, label in (("upper", "UPPER / OTHER"), ("lower", "LOWER / MY")):
            logical = stitch_wrapped_damage_lines(self.last_raw_ocr_frames.get(source, []))
            rendered = []
            for line in logical:
                event = parse_damage_line(line, party, self_name, pet_owner_map)
                if event:
                    rendered.append(f"✓ {event[0]} +{event[1]}    |    {line}")
                else:
                    rendered.append(f"  {line}")
            sections.append(label + "\n" + ("\n".join(rendered) if rendered else "(no OCR text)"))
        box.setPlainText("\n\n".join(sections))
        layout.addWidget(box)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def toggle_demo(self) -> None:
        if self.demo_timer.isActive():
            self.demo_timer.stop()
            self.demo_button.setText("Start demo")
            self.log_label.setText("Demo stopped.")
        else:
            if not self.current_party():
                demo_names = ["Prussy", "Redbali", "Sneaki", "Mattyhcf", "Xoren", "Samqanch"]
                demo_classes = ["Enchanter", "Shaman", "Rogue", "Monk", "Warrior", "Cleric"]
                for i, name in enumerate(demo_names):
                    self.party_edits[i].setText(name)
                    self.class_edits[i].setCurrentText(demo_classes[i])
                if not normalize_line(self.self_edit.text()):
                    self.self_edit.setText("Prussy")
            self.apply_party()
            self.demo_timer.start(420)
            self.demo_button.setText("Stop demo")
            self.log_label.setText("Demo running. This uses fake damage only to test the overlay.")

    def demo_tick(self) -> None:
        party = self.current_party()
        if not party:
            return
        weights = [1.25, 1.15, 0.95, 1.0, 0.85, 0.82][: len(party)]
        idx = random.randrange(len(party))
        amount = int(random.randint(18, 115) * weights[idx])
        self.encounter.add_damage(party[idx], amount, time.time(), self.timeout.value(), auto_reset=not self.continuous_check.isChecked())

    def reset_encounter(self) -> None:
        self.encounter.reset(self.current_party())
        self.previous_ocr_frames = {"upper": [], "lower": []}
        self.recent_damage_events = []
        self.ocr_baseline_pending = True
        if self.worker is not None:
            self.log_label.setText("Encounter reset — baselining visible combat text…")
        else:
            self.log_label.setText("Encounter reset — existing text will be ignored when OCR starts.")

    def refresh_ui(self) -> None:
        self.encounter.maybe_end(time.time(), self.timeout.value(), allow_end=not self.continuous_check.isChecked())
        self.apply_party_to_overlay()
        self.overlay.update_encounter(self.encounter)

    def closeEvent(self, event):
        self.save_current_settings()
        self.stop_ocr()
        self.demo_timer.stop()
        self.overlay.close()
        super().closeEvent(event)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"rgba(255,255,255,{alpha})"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"



def set_windows_dpi_awareness() -> None:
    """Make the process DPI-aware before Qt creates any windows."""
    if os.name != "nt":
        return
    try:
        # PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main() -> None:
    set_windows_dpi_awareness()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec())


def startup_log_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "startup_error.log"


if __name__ == "__main__":
    try:
        main()
    except Exception:
        details = traceback.format_exc()
        try:
            log_path = startup_log_path()
            log_path.write_text(details, encoding="utf-8")
        except Exception:
            log_path = None

        # pythonw.exe normally hides tracebacks. Show a real Windows error box
        # so a failed launch is visible instead of looking like "nothing happened".
        if os.name == "nt":
            try:
                message = (
                    "MnM Party Meter could not start.\\n\\n"
                    + (f"A diagnostic log was saved to:\\n{log_path}\\n\\n" if log_path else "")
                    + "Please send that log with your bug report."
                )
                ctypes.windll.user32.MessageBoxW(None, message, "MnM Party Meter — Startup Error", 0x10)
            except Exception:
                pass
        raise
