"""
Anno 117 Map Template Editor - Data Models
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Optional, Tuple, List
import config

# ─── Global editor-ID counter ───────────────────────────────────────────────

_eid_counter = 0

def _next_eid() -> int:
    global _eid_counter
    _eid_counter += 1
    return _eid_counter


# ─── Island Element ─────────────────────────────────────────────────────────

@dataclass
class IslandElement:
    """
    A single TemplateElement: a random island, fixed island, or ship-spawn.

    Coordinate note:
        position = (x, y) where x is the East axis and y is the North axis.
        (0, 0) is the SW corner (South tip in the rotated view).
        The island square occupies [x, x+size_px] × [y, y+size_px].
    """

    # ── position & geometry ─────────────────────────────────────────────────
    position: Tuple[int, int] = (0, 0)        # (gx, gy) lower-left corner
    size: str = "Medium"                      # Small/Medium/Large/ExtraLarge/Continental

    # ── type / role ─────────────────────────────────────────────────────────
    island_type: str = "Normal"               # Normal/Starter/ThirdParty/Pirate/Vulcan/Decoration

    # ── element metadata ────────────────────────────────────────────────────
    element_type: int = 1                     # 0=fixed, 1=random, 2=ship-spawn
    locked: bool = False                      # True = locked in enlarged template

    # ── fixed-island overrides (element_type == 0) ──────────────────────────
    map_file_path: Optional[str] = None
    island_label: Optional[str] = None
    rotation90: int = 0                       # 0-3  → 0°/90°/180°/270°
    fertility_guids: List[int] = field(default_factory=list)
    randomize_fertilities: bool = True

    # ── internal editor state (not serialised) ───────────────────────────────
    _eid: int = field(default_factory=_next_eid, compare=False, repr=False)

    # ── computed properties ──────────────────────────────────────────────────

    @property
    def size_pixels(self) -> int:
        return config.ISLAND_SIZE_PX.get(self.size, 320)

    @property
    def display_size_pixels(self) -> float:
        """Terrain-footprint approximation: size_pixels / √2.
        Non-continental islands have significant water at AABB corners; the game engine can place adjacent islands with slightly overlapping AABBs because only the inscribed diamond (side ≈ size/√2) contains terrain.
        Use this for collision detection and clamping for all non-continental islands."""
        import math
        return self.size_pixels / math.sqrt(2)

    @property
    def render_size_pixels(self) -> float:
        """Full AABB side length used for rendering the island polygon/image.
        Matches the AnnoMapEditor (Anno 1800) approach: islands are drawn as full AABB squares on a rotated canvas, which in our per-point gts() system is equivalent to transforming all 4 AABB corners - producing a diamond whose tip-to-tip width equals size_pixels × √2 × scale.
        Collision and clamping use display_size_pixels (terrain footprint) separately."""
        return float(self.size_pixels)

    @property
    def is_fixed(self) -> bool:
        return self.map_file_path is not None or self.element_type == 0

    @property
    def is_ship_spawn(self) -> bool:
        return self.element_type == 2

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        """(x1, y1, x2, y2) full AABB footprint in game pixels.
        Used for island-island collision: islands may touch but not overlap."""
        px, py = self.position
        return (px, py, px + self.size_pixels, py + self.size_pixels)

    @property
    def center(self) -> Tuple[float, float]:
        px, py = self.position
        s = self.size_pixels
        return (px + s / 2, py + s / 2)

    @property
    def display_name(self) -> str:
        if self.island_label:
            return self.island_label.split("/")[-1].removesuffix(".a7m")
        type_label = config.ISLAND_TYPE_LABELS.get(self.island_type, self.island_type)
        return f"{self.size} {type_label}"

    @property
    def type_color(self) -> str:
        # Continental is identified by size, not island_type
        if self.size == "Continental":
            return config.ISLAND_COLORS.get("Continental", config.ISLAND_COLORS["Vulcan"])
        return config.ISLAND_COLORS.get(self.island_type, "#4a8fc7")

    def clone(self) -> "IslandElement":
        c = deepcopy(self)
        object.__setattr__(c, "_eid", _next_eid())
        return c

    # ── validation ───────────────────────────────────────────────────────────

    def snap_position(self) -> None:
        """Snap position to grid of 8."""
        gx, gy = self.position
        self.position = (
            round(gx / config.GRID_SNAP) * config.GRID_SNAP,
            round(gy / config.GRID_SNAP) * config.GRID_SNAP,
        )


# ─── Map Template ────────────────────────────────────────────────────────────

@dataclass
class MapTemplate:
    """A complete map template for one region (Latium or Albion)."""

    region: str = "Latium"

    # Total map size (x, y) - must be divisible by 8
    size: Tuple[int, int] = (2048, 2048)

    # Playable area rectangle (x1, y1, x2, y2)
    playable_area: Tuple[int, int, int, int] = (20, 20, 2028, 2028)

    # Initial playable area (for enlarged templates)
    initial_playable_area: Tuple[int, int, int, int] = (20, 20, 2028, 2028)

    is_enlarged: bool = False
    enlargement_offset: Tuple[int, int] = (0, 0)

    elements: List[IslandElement] = field(default_factory=list)

    source_path: Optional[str] = None
    modified: bool = field(default=False, compare=False, repr=False)

    # ── Difficulty (editor-only, not serialised to XML) ──────────────────────
    # "easy" / "medium" / "hard" - only relevant when the template contains
    # fixed islands with randomize_fertilities=True.
    difficulty:        str  = field(default="easy",   compare=False, repr=False)
    difficulty_asked:  bool = field(default=False,    compare=False, repr=False)

    # ── convenience accessors ────────────────────────────────────────────────

    @property
    def map_size(self) -> int:
        """Maximum dimension (assumes square)."""
        return max(self.size)

    @property
    def computed_initial_pa(self) -> Tuple[int, int, int, int]:
        """
        InitialPlayableArea always derived from playable_area - never stored directly - so it is always consistent after any PA change.

        Enlarged Latium: the DLC01 expansion adds ENL_PA_EXPANSION px to x2/y2;
        the pre-DLC area is therefore (x1, y1, x2-exp, y2-exp).
        All other templates: equals playable_area.
        """
        import config as _cfg
        pa = self.playable_area
        if self.is_enlarged and self.region == "Latium":
            exp = _cfg.ENL_PA_EXPANSION
            return (pa[0], pa[1], pa[2] - exp, pa[3] - exp)
        return pa

    @property
    def islands(self) -> List[IslandElement]:
        return [e for e in self.elements if not e.is_ship_spawn]

    @property
    def ship_spawns(self) -> List[IslandElement]:
        return [e for e in self.elements if e.is_ship_spawn]

    # ── limit checking ───────────────────────────────────────────────────────

    def random_count(self, size: str) -> int:
        return sum(1 for e in self.islands if e.size == size and not e.is_fixed)

    def check_limits(self) -> List[str]:
        """Return list of human-readable warning strings for exceeded/met limits."""
        warnings: List[str] = []
        limits = config.ISLAND_LIMITS.get(self.region, {})
        for sz, cap in limits.items():
            if cap == 0:
                continue
            count = self.random_count(sz)
            if count > cap:
                warnings.append(
                    f"⚠  {sz}: {count}/{cap} random islands (EXCEEDED)"
                )
            elif count == cap:
                warnings.append(
                    f"ℹ  {sz}: {count}/{cap} random islands (at limit)"
                )
        return warnings

    # ── island lookup ────────────────────────────────────────────────────────

    def find_by_eid(self, eid: int) -> Optional[IslandElement]:
        for e in self.elements:
            if e._eid == eid:
                return e
        return None

    def remove_by_eid(self, eid: int) -> bool:
        for i, e in enumerate(self.elements):
            if e._eid == eid:
                del self.elements[i]
                self.modified = True
                return True
        return False

    def add_element(self, element: IslandElement) -> None:
        self.elements.append(element)
        self.modified = True

    # ── gap checking ────────────────────────────────────────────────────────

    def island_covers_spawn(
        self, pos: Tuple[int, int], size_px: int,
        exclude_eid: Optional[int] = None,
    ) -> bool:
        """Return True if a hypothetical island at *pos* with *size_px* covers any ship spawn."""
        ax1, ay1 = pos
        ax2, ay2 = ax1 + size_px, ay1 + size_px
        for sp in self.ship_spawns:
            if exclude_eid is not None and sp._eid == exclude_eid:
                continue
            sx, sy = sp.position
            if ax1 <= sx <= ax2 and ay1 <= sy <= ay2:
                return True
        return False

    def spawn_in_island(
        self, pos: Tuple[int, int],
        exclude_eid: Optional[int] = None,
    ) -> bool:
        """Return True if a spawn point at *pos* falls within any island's bounds."""
        sx, sy = pos
        for isl in self.islands:
            if exclude_eid is not None and isl._eid == exclude_eid:
                continue
            bx1, by1, bx2, by2 = isl.bounds
            if bx1 <= sx <= bx2 and by1 <= sy <= by2:
                return True
        return False

    def islands_overlap_or_too_close(
        self, pos: Tuple[int, int], size_px: int,
        size_str: str = "",
        exclude_eid: Optional[int] = None,
        min_gap: int = config.MIN_ISLAND_GAP,
    ) -> bool:
        """
        Return True if a hypothetical island at *pos* / *size_px* / *size_str* overlaps or is too close to any existing island.

        XL_COLLISION_GAP is applied when an ExtraLarge island is checked against a Continental island (and vice versa) - not between regular islands.
        """
        ax1, ay1 = pos
        ax2, ay2 = ax1 + size_px, ay1 + size_px

        for isl in self.islands:
            if exclude_eid is not None and isl._eid == exclude_eid:
                continue
            gap = min_gap
            if ((size_str == "ExtraLarge" and isl.size == "Continental") or
                    (size_str == "Continental" and isl.size == "ExtraLarge")):
                gap += config.XL_COLLISION_GAP
            bx1, by1, bx2, by2 = isl.bounds
            # Symmetric gap test: are the two AABBs within *gap* px of each other?
            if not (ax2 + gap > bx1 and bx2 + gap > ax1 and ay2 + gap > by1 and by2 + gap > ay1):
                continue
            # Continental underlap: a non-continental island may partially overlap the continental AABB, but only up to 10 % of the smaller island's area.
            # Only applies when gap == 0 (actual AABB overlap, not XL clearance range).
            if gap == 0:
                if isl.size == "Continental" and size_str != "Continental":
                    # Placing a smaller island that overlaps the continental
                    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
                    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
                    if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * size_px * size_px:
                        continue
                elif size_str == "Continental" and isl.size != "Continental":
                    # Placing the continental over an existing smaller island
                    isl_px = config.ISLAND_SIZE_PX.get(isl.size, size_px)
                    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
                    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
                    if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * isl_px * isl_px:
                        continue
            return True
        return False

    # ── factory ─────────────────────────────────────────────────────────────

    @staticmethod
    def new_empty(region: str) -> "MapTemplate":
        s = config.DEFAULT_SIZES.get(region, 2048)
        pad = 20
        return MapTemplate(
            region=region,
            size=(s, s),
            playable_area=(pad, pad, s - pad, s - pad),
            initial_playable_area=(pad, pad, s - pad, s - pad),
        )
