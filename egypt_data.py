"""
Anno 117 Map Template Editor - Aegyptus (DLC03) static data

Loads the tables tools/build_egypt_data.py writes into data/egypt and data/ui/islands:
island/quadrant geometry, active-area bitmaps, images, tile images and the Egyptian fertilities.

Geometry (all in game units, y pointing north):
  • map_size     the island file's square map (the template AABB, anchored at the element's Position)
  • active_rect  the island's playable territory inside that square; gamemapimage.png covers exactly this rect
  • grid / bits  the territory as 8-unit cells, row 0 = south, LSB-first, rows padded to 32 bits
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import base64
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import config

EGYPT_DIR       = os.path.join(config.DATA_DIR, "egypt")
EGYPT_IMG_DIR   = os.path.join(config.DATA_DIR, "ui", "islands")
TILES_DIR       = os.path.join(config.DATA_DIR, "ui", "islands", "tiles")
VANILLA_TEMPLATE = os.path.join(EGYPT_DIR, "egypt_province_default_01.xml")

REGION = "Aegyptus"
SESSION_GUID = 149679
MAP_SIZE = 2560
QUADRANT_SIZE = 960
PREFIX = "egypt_dlc_03_valley_"
LAYER_SUFFIX = "_layer01"

# The islands the vanilla MapTemplate lists in ReduceSizeIslands: the generator swaps these to their
# _layer01 file on medium/small maps (0/2/4 mediums, 2/4/6 larges at random).
AUTO_REDUCED = {
    "medium_01", "medium_02", "medium_03", "medium_04",
    "large_01", "large_02", "large_03", "large_05", "large_06", "large_07", "large_08", "large_10",
}

# Land fill and label for the cutout mode (no island images), as on the Latium/Albion placeholder images.
# Starters use the Large fill whatever their size.
KIND_COLORS = {
    "Large":      "#1d000e",
    "Medium":     "#d4b89b",
    "Small":      "#d4b89b",
    "Decoration": "#6b6258",
    "Village":    "#d4b89b",
    "Trader":     "#d4b89b",
    "Project":    "#d4b89b",
    "Pirate":     "#d4b89b",
}
KIND_LABEL_COLORS = {
    "Large":   "#d6bb9e",
    "Medium":  "#1d000e",
    "Small":   "#5f032e",
    "Village": "#5f032e",
    "Trader":  "#5f032e",
    "Project": "#5f032e",
    "Pirate":  "#5f032e",
}
# Which Latium/Albion island type an Aegyptus island borrows its border colour from (config.ISLAND_COLORS
# without images, config.ISLAND_COLORS_IMG with images). Decorations get no border.
KIND_BORDER_TYPE = {
    "Large": "Normal", "Medium": "Normal", "Small": "Normal",
    "Village": "ThirdParty", "Trader": "ThirdParty", "Project": "ThirdParty",
    "Pirate": "Pirate",
}
KIND_LABELS = {"Large": "L", "Medium": "M", "Small": "S", "Village": "3RD", "Trader": "3RD",
               "Project": "3RD", "Pirate": "RAIDER", "Decoration": ""}


@dataclass
class IslandFile:
    stem: str
    quadrant: str
    kind: str
    map_file: str
    map_size: Tuple[int, int]
    active_rect: Tuple[int, int, int, int]
    grid: Tuple[int, int]
    bits: bytes
    image: Optional[str]
    layer_of: Optional[str]
    has_layer: bool

    @property
    def short(self) -> str:
        return self.stem.replace(PREFIX, "")

    @property
    def cell(self) -> int:
        return self.map_size[0] // self.grid[0]

    @property
    def stride(self) -> int:
        return len(self.bits) // self.grid[1]

    def cell_set(self, cx: int, cy: int) -> bool:
        gw, gh = self.grid
        if not (0 <= cx < gw and 0 <= cy < gh):
            return False
        return bool(self.bits[cy * self.stride + cx // 8] >> (cx % 8) & 1)

    def contains(self, lx: float, ly: float, rot: int = 0) -> bool:
        """Local (island-relative) game coordinates inside the active territory of the island turned by *rot*."""
        lx, ly = unrotate_point(lx, ly, self.map_size[0], rot)
        return self.cell_set(int(lx // self.cell), int(ly // self.cell))

    def rotated_rect(self, rot: int) -> Tuple[int, int, int, int]:
        return rotate_rect(self.active_rect, self.map_size[0], rot)

    def rotated_cells(self, rot: int):
        """Set cells (cx, cy) of the territory after turning the island by *rot* quarter turns CCW."""
        gw, gh = self.grid
        out = []
        for cy in range(gh):
            for cx in range(gw):
                if self.cell_set(cx, cy):
                    x, y = cx, cy
                    for _ in range(rot % 4):
                        x, y = gw - 1 - y, x
                    out.append((x, y))
        return out

    @property
    def image_path(self) -> Optional[str]:
        return os.path.join(EGYPT_IMG_DIR, self.image) if self.image else None


@dataclass
class Fertility:
    guid: int
    name: str
    icon: str

    @property
    def display_name(self) -> str:
        for p in ("Fertility Egyptian ", "Fertility Roman ", "Fertility Celtic ", "Fertility ",
                  "Deposit Egyptian ", "Deposit Roman ", "Deposit Celtic ", "Deposit "):
            if self.name.startswith(p):
                return self.name[len(p):]
        return self.name

    @property
    def icon_path(self) -> str:
        return config.resource_path(self.icon)


@dataclass
class FertilityData:
    fertilities: Dict[int, Fertility] = field(default_factory=dict)
    pools: Dict[int, List[int]] = field(default_factory=dict)
    sets: Dict[int, dict] = field(default_factory=dict)


# ─── Rotation ─────────────────────────────────────────────────────────────────
# Rotation90 turns an island inside its square map about the square's centre, one quarter turn
# counter-clockwise per step (the convention the Latium/Albion canvas uses for fixed islands).

def rotate_point(x: float, y: float, size: float, rot: int) -> Tuple[float, float]:
    for _ in range(rot % 4):
        x, y = size - y, x
    return x, y


def unrotate_point(x: float, y: float, size: float, rot: int) -> Tuple[float, float]:
    for _ in range(rot % 4):
        x, y = y, size - x
    return x, y


def rotate_rect(rect, size: int, rot: int) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = rect
    for _ in range(rot % 4):
        x0, y0, x1, y1 = size - y1, x0, size - y0, x1
    return (x0, y0, x1, y1)


# ─── Loading ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def islands() -> Dict[str, IslandFile]:
    path = os.path.join(EGYPT_DIR, "islands.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {
        stem: IslandFile(
            stem=stem, quadrant=v["quadrant"], kind=v["kind"], map_file=v["map_file"],
            map_size=tuple(v["map_size"]), active_rect=tuple(v["active_rect"]), grid=tuple(v["grid"]),
            bits=base64.b64decode(v["grid_bits"]), image=v.get("image"),
            layer_of=v.get("layer_of"), has_layer=v.get("has_layer", False),
        )
        for stem, v in raw.items()
    }


@lru_cache(maxsize=1)
def fertility_data() -> FertilityData:
    path = os.path.join(EGYPT_DIR, "fertilities.json")
    if not os.path.isfile(path):
        return FertilityData()
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return FertilityData(
        fertilities={int(g): Fertility(int(g), v["name"], v["icon"]) for g, v in raw["fertilities"].items()},
        pools={int(g): v for g, v in raw["pools"].items()},
        sets={int(g): v for g, v in raw["sets"].items()},
    )


@lru_cache(maxsize=1)
def tile_boxes() -> Dict[str, dict]:
    path = os.path.join(TILES_DIR, "boxes.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def available() -> bool:
    return bool(islands()) and os.path.isfile(VANILLA_TEMPLATE)


# ─── Names / paths ────────────────────────────────────────────────────────────

def stem_of(map_file_path: str) -> str:
    return os.path.basename(map_file_path.replace("\\", "/")).rsplit(".", 1)[0]


def base_stem(stem: str) -> str:
    return stem[:-len(LAYER_SUFFIX)] if stem.endswith(LAYER_SUFFIX) else stem


def layer_stem(stem: str) -> str:
    return base_stem(stem) + LAYER_SUFFIX


def quadrant_origin(quadrant: str) -> Tuple[int, int]:
    """Vanilla lower-left corner of a quadrant, from its x?/y? suffix."""
    m = re.search(r"_x(\d)_y(\d)$", quadrant)
    return (int(m.group(1)) * QUADRANT_SIZE, int(m.group(2)) * QUADRANT_SIZE) if m else (0, 0)


def quadrant_label(quadrant: str) -> str:
    m = re.search(r"_x(\d)_y(\d)$", quadrant)
    if not m:
        return quadrant
    return {("0", "0"): "South", ("1", "0"): "East", ("0", "1"): "West", ("1", "1"): "North"}[(m.group(1), m.group(2))]


QUADRANTS = [f"egypt_island_quadrant_01_x{x}_y{y}" for y in (1, 0) for x in (0, 1)]


# ─── Tile images (all regions) ────────────────────────────────────────────────

def tile_image_path(stem: str) -> Optional[str]:
    p = os.path.join(TILES_DIR, stem + ".png")
    return p if os.path.isfile(p) else None


def tile_square_image(stem: str):
    """
    The tile image placed on the island's full square map (north-up), or None.
    Matches the artwork convention the Latium/Albion canvas uses: the image covers the whole .a7m square.
    """
    from PIL import Image
    box = tile_boxes().get(stem)
    path = tile_image_path(stem)
    if not box or not path:
        return None
    mw, mh = box["map_size"]
    x0, y0, x1, y1 = box["box"]
    img = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
    tile = Image.open(path).convert("RGBA")
    img.paste(tile, (x0, mh - y1))
    return img
