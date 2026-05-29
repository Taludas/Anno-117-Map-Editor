"""
Anno 117 Map Template Editor - Configuration & Constants
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))


import os
import sys
import platform
import settings as _settings

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# ─── Paths ──────────────────────────────────────────────────────────────────

def resource_path(rel):
    """Absolute path to a bundled read-only resource (works for dev and PyInstaller bundles)."""
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    return os.path.join(base, rel)

def _app_data_dir() -> str:
    """Platform-appropriate user config directory for persistent app data."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "Anno117MapEditor")

DATA_DIR         = resource_path("data")
FONTS_DIR        = os.path.join(DATA_DIR, "fonts")
ISLANDS_DIR      = os.path.join(DATA_DIR, "ui", "islands")
PLACEHOLDERS_DIR = os.path.join(ISLANDS_DIR, "placeholders")
UI_MAP_DIR       = os.path.join(DATA_DIR, "ui", "map")
INTERPRETER_PATH = os.path.join(DATA_DIR, "interpreter", "a7tinfo.xml")

_FDB_EXE = "FileDBReader.exe" if IS_WINDOWS else "FileDBReader"
TOOLS_INSTALL_DIR = r"C:\tools" if IS_WINDOWS else os.path.expanduser("~/.local/bin")

FILEDB_CANDIDATES = [
    os.path.join(TOOLS_INSTALL_DIR, _FDB_EXE),
    resource_path(_FDB_EXE),
    resource_path(os.path.join("tools", _FDB_EXE)),
    os.path.join(".", _FDB_EXE),
    os.path.join(".", "tools", _FDB_EXE),
    resource_path(_settings.get("fdb_path"))
]

EXTRACTED_DIR = os.path.join(_app_data_dir(), "extracted")

_GENERIC_ICONS_DIR   = os.path.join(DATA_DIR, "ui", "fhd", "base", "icon_content", "generic")
RAND_FERT_ICON_PATH  = os.path.join(_GENERIC_ICONS_DIR, "icon_2d_fertility.png")
RAND_QUEST_ICON_PATH = os.path.join(_GENERIC_ICONS_DIR, "icon_2d_mark_question.png")
MAP_BG_MAIN      = os.path.join(UI_MAP_DIR, "bg_main.jpg")
MAP_BG_MAP       = os.path.join(UI_MAP_DIR, "bg_map.jpg")
UI_ISLANDS_DIR   = ISLANDS_DIR
ASSETS_XML       = os.path.join(EXTRACTED_DIR, "data", "base", "config", "export", "assets.xml")

RDACONSOLE_CANDIDATES = [
    resource_path(os.path.join("tools", "RdaConsole.exe" if IS_WINDOWS else "RdaConsole")),
    os.path.join(".", "tools", "RdaConsole.exe" if IS_WINDOWS else "RdaConsole"),
    resource_path(_settings.get("rda_path"))
]

ANNO_INSTALL_CANDIDATES: list = []
if IS_WINDOWS:
    ANNO_INSTALL_CANDIDATES = [
        r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games\Anno 117",
        r"C:\Program Files\Ubisoft\Ubisoft Game Launcher\games\Anno 117",
        r"C:\Program Files (x86)\Steam\steamapps\common\Anno 117",
        r"C:\Program Files\Steam\steamapps\common\Anno 117",
        r"C:\Program Files (x86)\Epic Games\Anno117",
    ]
else:
    _h = os.path.expanduser("~")
    ANNO_INSTALL_CANDIDATES = [
        os.path.join(_h, ".steam", "steam", "steamapps", "common", "Anno 117"),
        os.path.join(_h, ".local", "share", "Steam", "steamapps", "common", "Anno 117"),
        os.path.join(_h, ".var", "app", "com.valvesoftware.Steam", ".steam", "steam", "steamapps", "common", "Anno 117"),
    ]

# ─── Colours ────────────────────────────────────────────────────────────────

BG_MAIN      = "#0b192c"
BG_SECTION   = "#162a45"
BG_HOVER     = "#253b59"
FG_MAIN      = "#ffffff"
FG_DIM       = "#aaaaaa"
FG_GOLD      = "#f1c40f"
FG_SEPARATOR = "#aaaaaa"

CANVAS_BG          = "#080f1a"
MAP_BORDER_FILL    = "#0d1f35"
MAP_BORDER_OUTLINE = "#1a3050"
MAP_PLAY_FILL      = "#152640"
MAP_PLAY_OUTLINE   = "#2a4870"
MAP_INIT_FILL      = "#1a2d50"   # Initial playable area (enlarged maps)

SELECTION_COLOR = "#ffffff"
HOVER_TINT      = "#aaccff"
GHOST_VALID     = "#00ff88"
GHOST_INVALID   = "#ff4444"
SHIP_SPAWN_COLOR= "#00bcd4"
GRID_COLOR      = "#1a2e4a"

# Island type border colours - used when island images are hidden (polygon fill mode)
ISLAND_COLORS = {
    "Normal":      "#08ac89",
    "Starter":     "#82ac08",
    "ThirdParty":  "#bd49e4",
    "Pirate":      "#ba0024",
    "Vulcan":      "#ff812d",
    "Continental": "#ff812d"
}

# Island type border colours - used when island images are shown (higher contrast on photos)
ISLAND_COLORS_IMG = {
    "Normal":      "#e0d8c0",
    "Starter":     "#f1c40f",
    "ThirdParty":  "#e07b39",
    "Pirate":      "#c0392b",
    "Vulcan":      "#8e44ad",
    "Continental": "#8e44ad"
}

# Fill colours (semi-transparent - handled by stipple or alpha image)
ISLAND_FILL = {
    "Normal":      "#1a3050",
    "Starter":     "#3a2e00",
    "ThirdParty":  "#3a2000",
    "Pirate":      "#2a0a00",
    "Vulcan":      "#200a30",
    "Continental": "#200a30"
}

# Human-readable type labels
ISLAND_TYPE_LABELS = {
    "Normal":      "Standard",
    "Starter":     "Starter",
    "ThirdParty":  "3rd Party",
    "Pirate":      "Pirate",
    "Vulcan":      "Vulcan",
    "Continental": "Continental",
}

# ─── Fonts ──────────────────────────────────────────────────────────────────

FONT_FILES = [
    os.path.join(FONTS_DIR, "PlayfairDisplaySC-Regular.ttf"),
    os.path.join(FONTS_DIR, "Marcellus-Regular.ttf"),
]

FONT_TITLE      = ("Playfair Display SC", 16, "bold")
FONT_DESC       = ("Marcellus", 11, "italic")
FONT_HEADER     = ("Playfair Display SC", 13, "bold")
FONT_BODY       = ("Marcellus", 13)
FONT_UI_BOLD    = ("Marcellus", 14, "bold")
FONT_TAB_BOLD   = ("Marcellus", 13, "bold")
FONT_BOLD_SMALL = ("Marcellus", 11, "bold")
FONT_SMALL      = ("Marcellus", 11)
FONT_XSMALL     = ("Marcellus", 10)

# Always-available fallbacks
FONT_FB       = ("TkDefaultFont", 14, "bold")
FONT_FB_BOLD  = ("TkDefaultFont", 13, "bold")
FONT_FB_SMALL  = ("TkDefaultFont", 12, "bold")
FONT_SPAWN_ICON = ("TkDefaultFont", 9, "bold")
FONT_FB_TITLE = ("TkDefaultFont", 16, "bold")

def load_custom_fonts():
    if IS_WINDOWS:
        try:
            import ctypes
            FR_PRIVATE = 0x10
            for fp in FONT_FILES:
                if os.path.exists(fp):
                    ctypes.windll.gdi32.AddFontResourceExW(fp, FR_PRIVATE, 0)
        except Exception as exc:
            print(f"[fonts] Could not load custom fonts: {exc}")

# ─── Island Data ────────────────────────────────────────────────────────────

# Size in game-coordinate pixels
ISLAND_SIZE_PX = {
    "Small":       256,
    "Medium":      320,
    "Large":       435,
    "ExtraLarge":  435,
    "Continental": 768,
}

ISLAND_SIZES = ["Small", "Medium", "Large", "ExtraLarge", "Continental"]
ISLAND_TYPES = ["Normal", "Starter", "ThirdParty", "Pirate", "Vulcan"]

# Max RANDOM (non-fixed) islands per region
ISLAND_LIMITS = {
    "Latium": {
        "Normal":     {"ExtraLarge": 4, "Large": 8, "Medium": 8, "Small": 7},
        "Starter":    {},
        "ThirdParty": {"any": 2},
        "Pirate":     {"any": 1},
        "Vulcan":     {"Medium": 3, "Small": 2},
    },
    "Albion": {
        "Normal":     {"Large": 8, "Medium": 7, "Small": 7},
        "Starter":    {},
        "ThirdParty": {"any": 2},
        "Pirate":     {"any": 1},
        "Vulcan":     {"any": 0},
    },
}

# Rotation labels for UI
ROTATION_LABELS = ["0°", "90°", "180°", "270°"]

# Difficulty - internal key → UI label (order matters for dropdowns)
DIFFICULTY_LABELS = {
    "easy":   "Easy",
    "medium": "Regular",
    "hard":   "Hard",
}
DIFFICULTY_KEYS = ["easy", "medium", "hard"]

MIN_ISLAND_GAP    = 0  # min game pixels between islands (baseline)
XL_COLLISION_GAP  = 64  # extra clearance between ExtraLarge islands and the PA border (not applied to island-vs-island collision)
GRID_SNAP         = 8   # positions must be divisible by this

# ─── Enlarged-map constants ──────────────────────────────────────────────────
ENL_PA_EXPANSION     = 420  # px added to PA x2/y2 when DLC01 expands the map
CONTINENTAL_MIN_BORDER = 248  # min PA border (px) for safe continental placement

# ─── Default map sizes ──────────────────────────────────────────────────────

DEFAULT_SIZES = {
    "Latium": 2048,
    "Albion": 2048,
}
