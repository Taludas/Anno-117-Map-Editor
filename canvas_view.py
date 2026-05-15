"""
Anno 117 Map Template Editor - Map Canvas

Renders the map as a 45°-rotated diamond, handles island placement,
drag/drop, selection, and image display.

Coordinate conventions
──────────────────────
Game coords (gx, gy):
  • x → East  (right in unrotated view)
  • y → North (up in unrotated view)
  • (0, 0) is the SW corner = the South tip of the diamond

Screen coords (sx, sy): standard Tk canvas, y increases downward.

Rotation (45° CCW applied to game coords, then y-flipped for screen):
  sx = cx + scale · (gx − S/2 − (gy − S/2)) / √2
  sy = cy − scale · (gx − S/2 + (gy − S/2)) / √2
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))


import math
import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Tuple, Dict, List

import config
from models import IslandElement, MapTemplate
from island_registry import IslandRegistry, PoolImageAssigner, _placeholder_for, _resolve_image

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

SQRT2 = math.sqrt(2)
BORDER_PX = 3       # island border width on screen (pixels)
GHOST_ALPHA = 128   # alpha for ghost island fill


# ─── Coordinate helpers ──────────────────────────────────────────────────────

def _gts(gx: float, gy: float,
         cx: float, cy: float,
         scale: float, S: float) -> Tuple[float, float]:
    """Game → screen."""
    dx, dy = gx - S / 2, gy - S / 2
    sx = cx + scale * (dx - dy) / SQRT2
    sy = cy - scale * (dx + dy) / SQRT2
    return sx, sy


def _stg(sx: float, sy: float,
         cx: float, cy: float,
         scale: float, S: float) -> Tuple[float, float]:
    """Screen → game."""
    rx = (sx - cx) / scale
    ry = (cy - sy) / scale
    dx = (rx + ry) / SQRT2
    dy = (ry - rx) / SQRT2
    return dx + S / 2, dy + S / 2


def _snap(v: float, grid: int = config.GRID_SNAP) -> int:
    return round(v / grid) * grid


# ─── Placeholder image generator ─────────────────────────────────────────────

def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _warn_continental_border_zone(isl: "IslandElement", pa: Tuple[int, int, int, int], parent_widget) -> None:
    """Show a warning if a continental island is placed >50 % into the border zone.

    The border zone is the area between the PlayableArea edge and the map Size boundary. If more than half the island's side length sits outside the PA, the game may produce bugs on the playable area or NPC interactions.
    """
    x, y = isl.position
    cs = isl.size_pixels # raw game-coord side length (768)
    half = cs / 2

    in_zone = (
        x < pa[0] - half or          # >50 % beyond left PA edge
        y < pa[1] - half or          # >50 % beyond bottom PA edge
        x + cs > pa[2] + half or     # >50 % beyond right PA edge
        y + cs > pa[3] + half        # >50 % beyond top PA edge
    )
    if in_zone:
        messagebox.showwarning(
            "Continental Island - Border Zone Warning",
            "This Continental island is placed more than 50 % of its side length\n"
            "into the border zone (area between the Playable Area and the map edge).\n\n"
            "This position may cause visual bugs on the playable area borders\n"
            "and/or affect NPC interaction areas.",
            parent=parent_widget,
        )


def _clamp_island_to_pa(isl: "IslandElement", pa: Tuple[int, int, int, int], x: int, y: int, map_size: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
    """
    Clamp island position so it stays within valid bounds.

    Regular islands: clamp to playable area.
    Continental islands: clamp to map bounds (0 to map_size - island_size).
      They may be positioned anywhere within the map regardless of PA.
      If map_size is unknown, fall back to playable area bounds.
    Boundaries are snapped to GRID_SNAP so the clamped position is always a multiple of 8.
    """
    G = config.GRID_SNAP
    if isl.size == "Continental":
        # Use the raw game-coord side length (768), not the rotated display size.
        # Constraint: position + size_pixels <= map_size on every axis.
        cs = isl.size_pixels
        if map_size is not None:
            lo_x, hi_x = 0, map_size[0] - cs
            lo_y, hi_y = 0, map_size[1] - cs
        else:
            lo_x, hi_x = 0, pa[2] - cs
            lo_y, hi_y = 0, pa[3] - cs
        lo_x = math.ceil(lo_x / G) * G
        hi_x = math.floor(hi_x / G) * G
        lo_y = math.ceil(lo_y / G) * G
        hi_y = math.floor(hi_y / G) * G
    else:
        ds = isl.size_pixels
        # ExtraLarge islands keep an additional gap from the PA border.
        border_gap = config.XL_COLLISION_GAP if isl.size == "ExtraLarge" else 0
        # Snap bounds inward to the nearest GRID_SNAP multiple so the clamped position is always on the 8 px grid (mirrors Continental handling above).
        lo_x = math.ceil((pa[0] + border_gap) / G) * G
        hi_x = math.floor((pa[2] - ds - border_gap) / G) * G
        lo_y = math.ceil((pa[1] + border_gap) / G) * G
        hi_y = math.floor((pa[3] - ds - border_gap) / G) * G
    return (max(lo_x, min(x, hi_x)), max(lo_y, min(y, hi_y)))


def _make_placeholder_no_text(island: IslandElement, px_size: int) -> "Image.Image":
    """Generated placeholder with no text - used only as last resort."""
    if not PIL_AVAILABLE:
        return None
    color = config.ISLAND_COLORS.get(island.island_type, "#4a8fc7")
    r, g, b = _hex_to_rgb(color)
    img = Image.new("RGBA", (px_size, px_size), (r // 4, g // 4, b // 4, 255))
    draw = ImageDraw.Draw(img)
    step = max(16, px_size // 8)
    for i in range(0, px_size, step):
        draw.line([(i, 0), (i, px_size)], fill=(r, g, b, 40), width=1)
        draw.line([(0, i), (px_size, i)], fill=(r, g, b, 40), width=1)
    cx2, cy2 = px_size // 2, px_size // 2
    rad = px_size // 4
    draw.ellipse([cx2-rad, cy2-rad, cx2+rad, cy2+rad], fill=(r, g, b, 60), outline=(r, g, b, 160), width=max(1, rad//6))
    return img


def _island_image(island: IslandElement, img_size_px: int, show_real: bool) -> Optional["Image.Image"]:
    """Load a real island image or fall back to a generated placeholder."""
    if not PIL_AVAILABLE:
        return None

    reg = IslandRegistry.instance()
    image_path: Optional[str] = None

    if show_real and reg.is_loaded:
        if island.is_fixed and island.map_file_path:
            # Fixed island - look up the .a7m name in the registry
            asset = reg.find_by_name(island.map_file_path)
            if asset and asset.image_path:
                image_path = asset.image_path
            else:
                # Not in registry (campaign/special islands) - resolve image directly
                a7m_name = os.path.basename(island.map_file_path).replace(".a7m", "")
                fp_lower = island.map_file_path.replace("\\", "/").lower()
                region = "Albion" if "/celtic/" in fp_lower else "Latium"
                image_path = _resolve_image(a7m_name, region)
        else:
            # Random island - use pool assigner (set on island before each redraw)
            assigner: Optional[PoolImageAssigner] = getattr(island, '_pool_assigner', None)
            if assigner:
                image_path = assigner.get_image(
                    getattr(island, '_region', 'Latium'),
                    island.size, island.island_type,
                )

    # Fall back to placeholder image files
    if not image_path:
        image_path = _placeholder_for(island.size, island.island_type)

    if image_path and os.path.isfile(image_path):
        try:
            return Image.open(image_path).resize((img_size_px, img_size_px), Image.LANCZOS)
        except Exception:
            pass

    return _make_placeholder_no_text(island, img_size_px)


# ─── MapCanvas ───────────────────────────────────────────────────────────────

class MapCanvas(tk.Canvas):
    """
    A Canvas widget that displays one Anno 117 map template as a
    45°-rotated diamond and handles interactive island editing.
    """

    def __init__(self, parent: tk.Widget, region: str, **kwargs):
        bg = kwargs.pop("bg", config.CANVAS_BG)
        super().__init__(parent, bg=bg, highlightthickness=0, **kwargs)

        self.region = region
        self.template: Optional[MapTemplate] = None

        # View state
        self._cx = 400.0
        self._cy = 400.0
        self._scale = 0.15
        self._S = 2048.0
        self.on_zoom_change: Optional[Callable[[float], None]] = None

        # Interaction state
        self.selected_eid: Optional[int] = None
        self._drag_start_s: Optional[Tuple[float, float]] = None
        self._drag_orig_pos: Optional[Tuple[int, int]] = None
        self._hover_eid: Optional[int] = None

        # Placement mode
        self._placing: Optional[IslandElement] = None  # ghost island
        self._ghost_valid = True

        # Select-all mode: all non-locked islands move together
        self._all_selected = False
        self._all_drag_start_s: Optional[Tuple[float, float]] = None
        self._all_drag_orig_positions: Dict[int, Tuple[int, int]] = {}

        # Pan (middle-mouse drag)
        self._pan_start_s: Optional[Tuple[float, float]] = None

        # Image toggle
        self.show_images = True
        self._bg_cache: Dict = {}
        self._pool_assigner: Optional[PoolImageAssigner] = None

        # Image cache: eid → (img_size_px, PhotoImage)  [or ghost key]
        self._img_cache: Dict = {}

        # Keep PIL RGBA label-background images alive during the current draw cycle
        self._label_bg_refs: List = []

        # Selection overlay (top-right of canvas)
        self._sel_overlay_lines: List[str] = []

        # Fertility icon cache: guid → PhotoImage (16×16)
        self._fert_icon_cache: Dict[int, object] = {}

        # Zoom settle: during rapid scroll, skip PIL image regeneration for speed
        self._zoom_active = False
        self._zoom_settle_id: Optional[str] = None

        # eid → IslandElement quick lookup (rebuilt on redraw)
        self._eid_map: Dict[int, IslandElement] = {}

        # Undo / redo
        _UNDO_LIMIT = 50
        self._undo_limit   = _UNDO_LIMIT
        self._undo_stack:  List = []
        self._redo_stack:  List = []
        self._drag_pre_snapshot:     Optional[List] = None   # single-island drag
        self._all_drag_pre_snapshot: Optional[List] = None   # select-all drag

        # Multi-select state
        self._multi_select: set = set()                              # set of selected eids
        self._rect_sel_start: Optional[Tuple[float, float]] = None   # screen anchor of drag-rect
        self._rect_sel_cur:   Optional[Tuple[float, float]] = None   # current drag endpoint

        # Multi-select group drag (mirrors select-all drag but for _multi_select only)
        self._multi_drag_start_s:      Optional[Tuple[float, float]] = None
        self._multi_drag_orig_positions: Dict[int, Tuple[int, int]]  = {}
        self._multi_drag_pre_snapshot:   Optional[List]              = None

        # Paste-ghost state: secondary ghosts shown alongside _placing during multi-paste
        self._paste_ghosts:  List[IslandElement]         = []  # secondary ghost islands
        self._paste_ghost_offsets: List[Tuple[int, int]] = []  # (dx, dy) from _placing.position

        # Clipboard (persists across template loads so copy ↔ paste between regions works)
        self._clipboard: List[IslandElement] = []

        # Callbacks
        self.on_select: Optional[Callable[[Optional[IslandElement]], None]] = None
        self.on_modify:  Optional[Callable[[], None]] = None

        # Bindings
        self.bind("<Configure>",       self._on_configure)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)
        self.bind("<ButtonPress-3>",   self._on_right_click)
        self.bind("<Escape>",          self._cancel_place)
        self.bind("<Delete>",          lambda _: self.delete_selected())
        self.bind("<BackSpace>",       lambda _: self.delete_selected())
        self.bind("<Control-c>",       self._on_copy)
        self.bind("<Control-v>",       self._on_paste)
        self.bind("<Up>",              lambda e: self._on_arrow_key(0, 1))
        self.bind("<Down>",            lambda e: self._on_arrow_key(0, -1))
        self.bind("<Right>",           lambda e: self._on_arrow_key(1, 0))
        self.bind("<Left>",            lambda e: self._on_arrow_key(-1, 0))
        self.bind("<Enter>",           lambda e: self.focus_set())
        self.bind_all("<MouseWheel>",  self._on_scroll_all)
        self.bind("<Button-4>",        self._on_scroll)
        self.bind("<Button-5>",        self._on_scroll)
        self.bind("<Shift-Button-4>",  self._on_scroll)
        self.bind("<Shift-Button-5>",  self._on_scroll)
        self.bind("<ButtonPress-2>",   self._on_pan_start)
        self.bind("<B2-Motion>",       self._on_pan_drag)
        self.bind("<ButtonRelease-2>", self._on_pan_end)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind(",",                 self._on_rotate_ccw)
        self.bind(".",                 self._on_rotate_cw)

        self.after(50, self.redraw)

    # ── Redraw scheduling (debounce) ─────────────────────────────────────────

    def _request_redraw(self) -> None:
        """Queue one redraw via after_idle; collapses multiple rapid calls."""
        if not getattr(self, '_redraw_scheduled', False):
            self._redraw_scheduled = True
            self.after_idle(self._do_scheduled_redraw)

    def _do_scheduled_redraw(self) -> None:
        self._redraw_scheduled = False
        self.redraw()

    # ── Public API ───────────────────────────────────────────────────────────

    def load_template(self, template: MapTemplate) -> None:
        self.template = template
        self.selected_eid = None
        self._placing = None
        self._sel_overlay_lines = []
        self._img_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._multi_select.clear()
        self._rect_sel_start = None
        self._rect_sel_cur = None
        self._multi_drag_start_s = None
        self._multi_drag_orig_positions.clear()
        self._multi_drag_pre_snapshot = None
        self._paste_ghosts = []
        self._paste_ghost_offsets = []
        self._update_transform()
        self._default_scale = self._scale
        self._default_cx = self._cx
        self._default_cy = self._cy
        self.redraw()

    # ── Undo / Redo ──────────────────────────────────────────────────────────

    def push_undo(self) -> None:
        """Snapshot the current template elements onto the undo stack."""
        if self.template is None:
            return
        from copy import deepcopy
        self._undo_stack.append(deepcopy(self.template.elements))
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Restore the previous state. Returns True if a step was undone."""
        if not self._undo_stack or self.template is None:
            return False
        from copy import deepcopy
        self._redo_stack.append(deepcopy(self.template.elements))
        self.template.elements = self._undo_stack.pop()
        self.template.modified = True
        self.selected_eid = None
        self._multi_select.clear()
        self._img_cache.clear()
        if self.on_select:
            self.on_select(None)
        if self.on_modify:
            self.on_modify()
        self.redraw()
        return True

    def redo(self) -> bool:
        """Reapply the last undone state. Returns True if a step was redone."""
        if not self._redo_stack or self.template is None:
            return False
        from copy import deepcopy
        self._undo_stack.append(deepcopy(self.template.elements))
        self.template.elements = self._redo_stack.pop()
        self.template.modified = True
        self.selected_eid = None
        self._multi_select.clear()
        self._img_cache.clear()
        if self.on_select:
            self.on_select(None)
        if self.on_modify:
            self.on_modify()
        self.redraw()
        return True

    def start_placing(self, island: IslandElement) -> None:
        """Enter placement mode: the island ghost follows the mouse."""
        self._placing = island.clone()
        self._placing.position = (0, 0)
        self.config(cursor="crosshair")

    def cancel_placing(self) -> None:
        self._placing = None
        self._paste_ghosts = []
        self._paste_ghost_offsets = []
        self.config(cursor="")
        self.redraw()

    def select_all(self) -> None:
        """Enter select-all mode: all non-locked islands highlighted and moved as one."""
        if self.template is None:
            return
        self._placing = None
        self._all_selected = True
        self.selected_eid = None
        self.config(cursor="fleur")
        self.redraw()

    def deselect_all(self) -> None:
        """Exit select-all mode."""
        self._all_selected = False
        self._all_drag_start_s = None
        self._all_drag_orig_positions.clear()
        self._multi_select.clear()
        self.config(cursor="")
        self.redraw()

    def delete_selected(self) -> None:
        if self.template is None:
            return
        eids_to_delete = set(self._multi_select)
        if self.selected_eid is not None:
            eids_to_delete.add(self.selected_eid)
        if not eids_to_delete:
            return
        self.push_undo()
        for eid in eids_to_delete:
            self.template.remove_by_eid(eid)
        self.selected_eid = None
        self._multi_select.clear()
        self._img_cache.clear()
        if self.on_select:
            self.on_select(None)
        if self.on_modify:
            self.on_modify()
        self.redraw()

    def get_selected(self) -> Optional[IslandElement]:
        if self.template is None or self.selected_eid is None:
            return None
        return self.template.find_by_eid(self.selected_eid)

    def invalidate_image(self, eid: int) -> None:
        """Remove cached image for one island (call after type/size changes)."""
        self._img_cache.pop(eid, None)

    def clear_image_cache(self) -> None:
        self._img_cache.clear()

    def set_selection_overlay(self, lines: List[str]) -> None:
        """Set the selected-island info displayed in the canvas top-right overlay."""
        self._sel_overlay_lines = lines
        self._request_redraw()

    # ── Transform ────────────────────────────────────────────────────────────

    def _update_transform(self) -> None:
        w = max(self.winfo_width(), 100)
        h = max(self.winfo_height(), 100)
        self._cx = w / 2
        self._cy = h / 2
        if self.template:
            self._S = float(max(self.template.size))
        pad = 40
        avail = min(w, h) - 2 * pad
        self._scale = avail / (self._S * SQRT2)

    def gts(self, gx: float, gy: float) -> Tuple[float, float]:
        return _gts(gx, gy, self._cx, self._cy, self._scale, self._S)

    def stg(self, sx: float, sy: float) -> Tuple[float, float]:
        return _stg(sx, sy, self._cx, self._cy, self._scale, self._S)

    def _island_diag(self, island: IslandElement) -> float:
        """Diagonal of the island's screen diamond in pixels."""
        # size_pixels is the game-coord side; on the rotated canvas the visible side length = size_px / sqrt(2)
        return island.size_pixels * self._scale

    # ── Redraw ───────────────────────────────────────────────────────────────

    def redraw(self) -> None:
        self.delete("all")
        self._eid_map.clear()
        self._label_bg_refs.clear()
        self._pool_assigner = PoolImageAssigner()
        if self.template:
            for isl in self.template.islands:
                isl._pool_assigner = self._pool_assigner
                isl._region = self.region

        self._draw_outer_bg()

        if self.template is None:
            self._draw_empty_hint()
            return

        self._draw_map_diamond()
        self._draw_restricted_overlay()
        self._draw_playable_area()
        self._draw_init_area()
        self._draw_compass()
        self._draw_islands()
        self._draw_ship_spawns()
        self._draw_ghost()
        self._draw_rect_selection()
        self._draw_legend()

    # ── Background & map layers ──────────────────────────────────────────────

    def _draw_outer_bg(self) -> None:
        w = self.winfo_width() or 800
        h = self.winfo_height() or 600
        if PIL_AVAILABLE and os.path.isfile(config.MAP_BG_MAIN):
            key = ("bg_main", w, h)
            if key not in self._bg_cache:
                img = Image.open(config.MAP_BG_MAIN)
                iw, ih = img.size
                # Cover-scale: fill the canvas while preserving aspect ratio
                sc = max(w / iw, h / ih)
                nw2, nh2 = int(iw * sc), int(ih * sc)
                img = img.resize((nw2, nh2), Image.LANCZOS)
                left = (nw2 - w) // 2
                top  = (nh2 - h) // 2
                img = img.crop((left, top, left + w, top + h))
                self._bg_cache[key] = ImageTk.PhotoImage(img)
            self.create_image(0, 0, image=self._bg_cache[key], anchor="nw", tags="bg")
        else:
            self.create_rectangle(0, 0, w, h, fill=config.CANVAS_BG, outline="")

    def _draw_empty_hint(self) -> None:
        w = self.winfo_width() or 800
        h = self.winfo_height() or 800
        tid = self.create_text(
            w / 2, h / 2,
            text="No map loaded.\nUse File › Import or File › New.",
            fill=config.FG_GOLD,
            font=config.FONT_FB,
            justify=tk.CENTER,
        )
        bb = self.bbox(tid)
        if bb:
            pad_x, pad_y = 18, 12
            rid = self.create_rectangle(
                bb[0] - pad_x, bb[1] - pad_y, bb[2] + pad_x, bb[3] + pad_y,
                fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1,
            )
            self.tag_lower(rid, tid)

    def _diamond_pts(self, x1: int, y1: int, x2: int, y2: int) -> list:
        """4 screen-space corner points (South, East, North, West) for a game rectangle."""
        s = self.gts(x1, y1)  # SW → South tip
        e = self.gts(x2, y1)  # SE → East tip
        n = self.gts(x2, y2)  # NE → North tip
        w = self.gts(x1, y2)  # NW → West tip
        return [*s, *e, *n, *w]

    def _draw_map_diamond(self) -> None:
        sx, sy = self.template.size
        pts = self._diamond_pts(0, 0, sx, sy)

        # Skip PIL image processing during active zoom - polygon fallback is instant
        if PIL_AVAILABLE and os.path.isfile(config.MAP_BG_MAP) and not self._zoom_active:
            # Compute bounding box of diamond on screen
            xs = pts[0::2]; ys = pts[1::2]
            x1, y1 = int(min(xs)), int(min(ys))
            x2, y2 = int(max(xs)), int(max(ys))
            diam_w, diam_h = x2 - x1, y2 - y1
            key = ("bg_map", diam_w, diam_h)
            if key not in self._bg_cache:
                # Load, rotate 45°, resize to diamond bounding box
                img = Image.open(config.MAP_BG_MAP).convert("RGBA")
                img = img.rotate(45, expand=True, resample=Image.BICUBIC,
                                 fillcolor=(0, 0, 0, 0))
                img = img.resize((diam_w, diam_h), Image.LANCZOS)
                self._bg_cache[key] = ImageTk.PhotoImage(img)
            cx2 = (x1 + x2) / 2
            cy2 = (y1 + y2) / 2
            self.create_image(cx2, cy2, image=self._bg_cache[key], anchor="center", tags="map_bg")
            # Draw diamond outline on top
            self.create_polygon(pts, fill="", outline=config.MAP_BORDER_OUTLINE, width=2, tags="map_bg")
        else:
            self.create_polygon(pts, fill=config.MAP_BORDER_FILL, outline=config.MAP_BORDER_OUTLINE, width=2, tags="map_bg")

    def _draw_restricted_overlay(self) -> None:
        """Stippled overlay over the non-playable area (between map border and playable area border).  Uses the same colour as the playable area outline at 25 % density so the map background shows through."""
        pa = self.template.playable_area # (x1, y1, x2, y2)
        sx, sy = self.template.size

        # Screen-space corners of the full map diamond
        s_map = self.gts(0,   0)
        e_map = self.gts(sx,  0)
        n_map = self.gts(sx,  sy)
        w_map = self.gts(0,   sy)

        # Screen-space corners of the playable area diamond
        s_pa  = self.gts(pa[0], pa[1])
        e_pa  = self.gts(pa[2], pa[1])
        n_pa  = self.gts(pa[2], pa[3])
        w_pa  = self.gts(pa[0], pa[3])

        # Four quadrilateral sections of the frame (SE, NE, NW, SW)
        for quad in (
            (*s_map, *e_map, *e_pa, *s_pa),
            (*e_map, *n_map, *n_pa, *e_pa),
            (*n_map, *w_map, *w_pa, *n_pa),
            (*w_map, *s_map, *s_pa, *w_pa),
        ):
            self.create_polygon(
                quad,
                fill=config.MAP_PLAY_OUTLINE,
                outline="",
                stipple="gray50",
                tags="map_restricted",
            )

    def _draw_playable_area(self) -> None:
        pa = self.template.playable_area
        pts = self._diamond_pts(pa[0], pa[1], pa[2], pa[3])
        self.create_polygon(
            pts,
            fill="",
            outline=config.MAP_PLAY_OUTLINE,
            width=3,
            tags="map_play",
        )

    def _draw_init_area(self) -> None:
        if not self.template.is_enlarged:
            return
        ipa = self.template.computed_initial_pa
        pa  = self.template.playable_area
        if ipa == pa:
            return
        pts = self._diamond_pts(ipa[0], ipa[1], ipa[2], ipa[3])
        self.create_polygon(
            pts,
            fill="",
            outline=config.FG_GOLD,
            width=1,
            dash=(6, 4),
            tags="map_init",
        )

    def _draw_compass(self) -> None:
        """Label cardinal directions on the diamond tips."""
        sx, sy = self.template.size
        offset = 18
        for label, gx, gy, anc in (
            ("S", 0,     0,     "n"),
            ("N", sx,    sy,    "s"),
            ("E", sx,    0,     "w"),
            ("W", 0,     sy,    "e"),
        ):
            px, py = self.gts(gx, gy)
            if anc == "n":  py += offset
            elif anc == "s":py -= offset
            elif anc == "w":px += offset
            elif anc == "e":px -= offset
            self.create_text(px, py, text=label, fill=config.FG_GOLD, font=config.FONT_FB_SMALL)

    # ── PNG export ───────────────────────────────────────────────────────────

    def export_png(self, filepath: str, img_size: int = 1024) -> None:
        """
        Render the current map to a PNG of the full map template diamond:
        playable area + border zone with all islands included.
        • Full map background = bg_map.jpg inside the map diamond.
        • Outside the map diamond = bg_main.jpg (ocean corners).
        • Playable area boundary drawn as a thin reference outline.
        • Island images or filled polygons depending on show_images mode.
        • Island labels (size/type abbreviation + fertility icons) always included.
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for PNG export.")
        if self.template is None:
            raise RuntimeError("No map template loaded.")

        from PIL import Image, ImageDraw as _ImageDraw, ImageFont as _ImageFont

        tmpl = self.template
        pa   = tmpl.playable_area                       # (x1, y1, x2, y2)
        S    = float(max(tmpl.size))                    # map side (assumed square)

        # Scale so the full map diamond exactly fills img_size × img_size.
        # A square of side S rotated 45° has E-W screen span = S × √2.
        exp_scale = img_size / (S * SQRT2)
        half      = img_size / 2.0

        def _gts(gx: float, gy: float) -> Tuple[float, float]:
            sx = half + exp_scale * (gx - S / 2 - (gy - S / 2)) / SQRT2
            sy = half - exp_scale * (gx - S / 2 + (gy - S / 2)) / SQRT2
            return sx, sy

        # ── Full map diamond mask ─────────────────────────────────────────────
        map_corners = [_gts(0, 0), _gts(S, 0), _gts(S, S), _gts(0, S)]
        flat_map    = [v for pt in map_corners for v in pt]
        map_mask    = Image.new("L", (img_size, img_size), 0)
        _ImageDraw.Draw(map_mask).polygon(flat_map, fill=255)

        bg_rgb = _hex_to_rgb(config.CANVAS_BG)

        # ── Outer background: bg_main.jpg (fills the four outer triangles) ────
        if os.path.isfile(config.MAP_BG_MAIN):
            bg_main = Image.open(config.MAP_BG_MAIN).convert("RGBA")
            bg_main = bg_main.resize((img_size, img_size), Image.LANCZOS)
        else:
            bg_main = Image.new("RGBA", (img_size, img_size), (*bg_rgb, 255))

        # Base starts as bg_main; map content is pasted on top inside the diamond.
        base = bg_main.copy()

        # ── Map background: bg_map.jpg covers the whole map diamond ──────────
        # With exp_scale = img_size / (S × √2):  S × √2 × exp_scale = img_size, so the bg_map resized to img_size × img_size and pasted at (0,0) fills the diamond exactly (the 45°-rotated square inscribes in the square canvas).
        if os.path.isfile(config.MAP_BG_MAP):
            bg_img = Image.open(config.MAP_BG_MAP).convert("RGBA")
            bg_img = bg_img.rotate(45, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
            bg_img = bg_img.resize((img_size, img_size), Image.LANCZOS)
            map_layer = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
            map_layer.paste(bg_img, (0, 0))
            base.paste(map_layer, (0, 0), map_mask)

        # ── Label font ───────────────────────────────────────────────────────
        font_sz = max(10, int(14 * img_size / 1024))
        label_font = None
        for _fpath in ("arial.ttf", r"C:\Windows\Fonts\arial.ttf",
                       r"C:\Windows\Fonts\segoeui.ttf"):
            try:
                label_font = _ImageFont.truetype(_fpath, font_sz)
                break
            except Exception:
                continue
        if label_font is None:
            try:
                label_font = _ImageFont.load_default(size=font_sz)
            except TypeError:
                label_font = _ImageFont.load_default()

        # ── Helper: dashed polyline (PIL has no native dash support) ─────────
        def _dashed_line(draw_ctx, pts, fill, width=1, dash_on=8, dash_off=5):
            for i in range(len(pts) - 1):
                x0, y0 = pts[i]
                x1, y1 = pts[i + 1]
                seg_len = math.hypot(x1 - x0, y1 - y0)
                if seg_len == 0:
                    continue
                ddx, ddy = (x1 - x0) / seg_len, (y1 - y0) / seg_len
                pos, on = 0.0, True
                while pos < seg_len:
                    step = dash_on if on else dash_off
                    end = min(pos + step, seg_len)
                    if on:
                        draw_ctx.line(
                            [(x0 + ddx * pos, y0 + ddy * pos),
                             (x0 + ddx * end, y0 + ddy * end)],
                            fill=fill, width=width,
                        )
                    pos, on = end, not on

        # ── Playable area boundary outline (drawn before islands so islands sit on top) ──
        draw = _ImageDraw.Draw(base)
        pa_pts = [_gts(pa[0], pa[1]), _gts(pa[2], pa[1]),
                  _gts(pa[2], pa[3]), _gts(pa[0], pa[3])]
        pa_outline_clr = (*_hex_to_rgb(config.MAP_PLAY_OUTLINE), 200)
        _dashed_line(draw, pa_pts + [pa_pts[0]], fill=pa_outline_clr, width=max(2, BORDER_PX), dash_on=999999)  # solid line for PA

        # ── Initial playable area boundary (enlarged templates only) ──────────
        if tmpl.is_enlarged:
            ipa = tmpl.computed_initial_pa
            if ipa != tmpl.playable_area:
                ipa_pts = [_gts(ipa[0], ipa[1]), _gts(ipa[2], ipa[1]),
                           _gts(ipa[2], ipa[3]), _gts(ipa[0], ipa[3])]
                gold = (*_hex_to_rgb(config.FG_GOLD), 220)
                # width=1 avoids PIL's diagonal thick-line aliasing artefact; dash lengths are scaled so they look the same across export sizes.
                dash_on  = max(10, int(20 * img_size / 1024))
                dash_off = max(5,  int(10 * img_size / 1024))
                _dashed_line(draw, ipa_pts + [ipa_pts[0]], fill=gold, width=1, dash_on=dash_on, dash_off=dash_off)

        # ── Islands ──────────────────────────────────────────────────────────
        draw = _ImageDraw.Draw(base)

        for isl in tmpl.islands:
            s      = isl.render_size_pixels
            img_px = max(4, int(s * exp_scale))
            px_i, py_i = isl.position
            half_s = s / 2.0

            poly = [_gts(px_i,     py_i    ), _gts(px_i + s, py_i    ),
                    _gts(px_i + s, py_i + s), _gts(px_i,     py_i + s)]

            color_dict = config.ISLAND_COLORS_IMG if self.show_images else config.ISLAND_COLORS
            clr = color_dict.get(
                "Continental" if isl.size == "Continental" else isl.island_type,
                color_dict.get("Normal", "#e0d8c0"),
            )

            # Always render as image (real photo or placeholder depending on mode)
            pil_img = _island_image(isl, img_px, show_real=self.show_images)
            if pil_img is not None:
                if pil_img.mode != "RGBA":
                    pil_img = pil_img.convert("RGBA")
                if isl.rotation90:
                    pil_img = pil_img.rotate(isl.rotation90 * 90, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
                pil_img = pil_img.rotate(45, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
                cx_s, cy_s = _gts(px_i + half_s, py_i + half_s)
                base.paste(pil_img,
                           (int(cx_s - pil_img.width / 2),
                            int(cy_s - pil_img.height / 2)),
                           pil_img)
                draw = _ImageDraw.Draw(base)
            # Draw border as a closed polyline: cleaner joins on diagonal edges than draw.polygon(outline=) which fragments at corners.
            closed = poly + [poly[0]]
            flat_closed = [v for pt in closed for v in pt]
            draw.line(flat_closed, fill=clr, width=max(2, BORDER_PX + 1))

            # ── Label (only in image mode) ───────────────────────────────────
            if not self.show_images:
                continue
            cx_l = (poly[0][0] + poly[1][0] + poly[2][0] + poly[3][0]) / 4
            cy_l = (poly[0][1] + poly[1][1] + poly[2][1] + poly[3][1]) / 4

            size_abbr = "XL" if isl.size == "ExtraLarge" else isl.size[:1]
            lbl_parts = [size_abbr]
            if isl.island_type != "Normal":
                lbl_parts.append(isl.island_type[0])
            lbl = "".join(lbl_parts)

            try:
                tbbox = draw.textbbox((0, 0), lbl, font=label_font)
                txt_w, txt_h = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
            except AttributeError:
                txt_w, txt_h = font_sz, font_sz

            # Fertility icons for the label box
            ICON_SZ  = max(8, int(14 * img_size / 1024))
            ICON_PAD = 2
            cols     = 4
            fert_pil: List[Optional[Image.Image]] = []
            if isl.is_fixed and isl.fertility_guids:
                from fertility_registry import FertilityRegistry
                freg = FertilityRegistry.instance()
                if freg.is_loaded:
                    for guid in isl.fertility_guids:
                        asset = freg.find_by_guid(guid)
                        if asset and os.path.isfile(asset.icon_path):
                            try:
                                fert_pil.append(
                                    Image.open(asset.icon_path).convert("RGBA")
                                    .resize((ICON_SZ, ICON_SZ), Image.LANCZOS)
                                )
                            except Exception:
                                fert_pil.append(None)
                        else:
                            fert_pil.append(None)

            num_rows    = math.ceil(len(fert_pil) / cols) if fert_pil else 0
            max_cols_r  = min(len(fert_pil), cols) if fert_pil else 0
            icon_row_w  = max_cols_r * ICON_SZ + max(0, max_cols_r - 1) * ICON_PAD
            icon_blk_h  = (num_rows * ICON_SZ + max(0, num_rows - 1) * ICON_PAD if fert_pil else 0)

            bg_w = max(1, max(txt_w, icon_row_w) + 8)
            bg_h = max(1, txt_h + 6 + (icon_blk_h + 4 if fert_pil else 0))
            box_x = int(cx_l - bg_w / 2)
            box_y = int(cy_l - txt_h / 2 - 3)

            r_b, g_b, b_b = _hex_to_rgb(config.BG_SECTION)
            bg_box = Image.new("RGBA", (bg_w, bg_h), (r_b, g_b, b_b, 128))
            base.paste(bg_box, (box_x, box_y), bg_box)
            draw = _ImageDraw.Draw(base)

            draw.text(
                (cx_l - txt_w / 2, box_y + 3),
                lbl, fill="#ffffff", font=label_font,
            )

            if fert_pil:
                icons_x0 = int(cx_l - icon_row_w / 2)
                icons_y0 = box_y + txt_h + 6
                for i, fi in enumerate(fert_pil):
                    row_i, col_i = divmod(i, cols)
                    ix = icons_x0 + col_i * (ICON_SZ + ICON_PAD)
                    iy = icons_y0 + row_i * (ICON_SZ + ICON_PAD)
                    if fi is not None:
                        base.paste(fi, (ix, iy), fi)
                draw = _ImageDraw.Draw(base)

        # ── Ship spawns (drawn last so they sit above all islands) ───────────
        draw = _ImageDraw.Draw(base)
        spawn_clr = _hex_to_rgb(config.SHIP_SPAWN_COLOR)
        r = max(6, int(9 * img_size / 1024))
        arm = max(2, r // 2)           # half-length of the cross arms
        lw  = max(1, r // 4)           # line width for outline and cross
        for sp in tmpl.ship_spawns:
            sx_s, sy_s = _gts(*sp.position)
            draw.ellipse(
                [sx_s - r, sy_s - r, sx_s + r, sy_s + r],
                fill=(*spawn_clr, 255),
                outline=(255, 255, 255, 255),
                width=lw,
            )
            # Small white cross in the centre
            draw.line([(sx_s - arm, sy_s), (sx_s + arm, sy_s)], fill=(255, 255, 255, 255), width=lw)
            draw.line([(sx_s, sy_s - arm), (sx_s, sy_s + arm)], fill=(255, 255, 255, 255), width=lw)

        # ── Clip: outside map diamond → bg_main.jpg (ocean corners) ──────────
        result = Image.composite(base, bg_main, map_mask)
        result.convert("RGB").save(filepath, "PNG")

    # ── Ship spawns ──────────────────────────────────────────────────────────

    def _draw_ship_spawns(self) -> None:
        for sp in self.template.ship_spawns:
            self._eid_map[sp._eid] = sp
            sx2, sy2 = self.gts(*sp.position)
            r = 9  # fixed screen-pixel radius, independent of zoom
            tag = f"iid_{sp._eid}"
            tags = (tag, "ship_spawn")
            sel = self.selected_eid == sp._eid
            outline = config.SELECTION_COLOR if sel else "#ffffff"
            self.create_oval(
                sx2 - r, sy2 - r, sx2 + r, sy2 + r,
                fill=config.SHIP_SPAWN_COLOR,
                outline=outline,
                width=2 if sel else 1,
                tags=tags,
            )
            self.create_text(
                sx2, sy2, text="⚓",
                fill="#ffffff", font=config.FONT_SPAWN_ICON,
                tags=tags,
            )

    # ── Islands ──────────────────────────────────────────────────────────────

    def _draw_islands(self) -> None:
        for isl in self.template.islands:
            self._eid_map[isl._eid] = isl
            self._draw_one_island(isl, ghost=False)

    def _draw_island_image(self, isl: IslandElement, tags: tuple) -> None:
        """Draw a rotated PIL image centred on the island's screen position."""
        if not PIL_AVAILABLE:
            return
        s = isl.render_size_pixels
        img_px = max(4, int(s * self._scale))
        cache_key = (isl._eid, img_px, isl.island_type, isl.size, self.show_images, isl.rotation90)

        if cache_key not in self._img_cache:
            pil_img = _island_image(isl, img_px, self.show_images)
            if pil_img is None:
                return
            # Convert to RGBA so rotation corners are transparent, not black
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            # Apply island rotation (fixed islands can be rotated in 90° steps)
            if isl.rotation90:
                pil_img = pil_img.rotate(isl.rotation90 * 90, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
            # Rotate 45° CCW so the image aligns with the diamond
            rotated = pil_img.rotate(45, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
            tk_img = ImageTk.PhotoImage(rotated)
            self._img_cache[cache_key] = tk_img
        else:
            tk_img = self._img_cache[cache_key]

        px, py = isl.position
        half_s = isl.render_size_pixels / 2
        cx2, cy2 = self.gts(px + half_s, py + half_s)
        # Strip the eid tag so only the diamond polygon acts as the click target.
        # The image's rectangular bounding box would otherwise create false hit areas in the four corner triangles outside the diamond.
        img_tags = tuple(t for t in tags if not t.startswith("iid_"))
        self.create_image(cx2, cy2, image=tk_img, anchor=tk.CENTER, tags=img_tags)

    def _draw_one_island(
        self,
        isl: IslandElement,
        ghost: bool = False,
        valid: bool = True,
    ) -> None:
        px, py = isl.position
        # render_size_pixels: size_pixels for Continental (terrain fills full AABB), display_size_pixels for all other sizes (game engine places islands with overlapping AABBs; only the inscribed diamond area contains terrain).
        s = isl.render_size_pixels

        # Four screen corners: SW, SE, NE, NW
        sw = self.gts(px,     py    )
        se = self.gts(px + s, py    )
        ne = self.gts(px + s, py + s)
        nw = self.gts(px,     py + s)
        pts = [*sw, *se, *ne, *nw]

        tag = f"iid_{isl._eid}"
        tags = (tag, "island")

        color_dict = config.ISLAND_COLORS_IMG if self.show_images else config.ISLAND_COLORS
        color = color_dict.get(
            "Continental" if isl.size == "Continental" else isl.island_type,
            color_dict.get("Normal", "#4a8fc7"),
        )
        fill_c = config.ISLAND_FILL.get(
            "Continental" if isl.size == "Continental" else isl.island_type, "#1a2030"
        )
        sel       = self.selected_eid == isl._eid
        multi_sel = isl._eid in self._multi_select
        all_sel   = self._all_selected and not isl.locked

        if ghost:
            outline = config.GHOST_VALID if valid else config.GHOST_INVALID
            fill_c  = outline
        elif sel or multi_sel or all_sel:
            outline = config.SELECTION_COLOR
        elif self._hover_eid == isl._eid:
            outline = config.HOVER_TINT
        else:
            outline = color

        bw = BORDER_PX + (2 if (sel or multi_sel or all_sel) else 0)

        # ── Draw island image if PIL available ───────────────────────────────
        if PIL_AVAILABLE and not ghost and not self._zoom_active:
            # show_images=True  → real photo; False → fallback/placeholder image
            self._draw_island_image(isl, tags)
            # Draw border polygon (outline only)
            self.create_polygon(
                pts, fill="", outline=outline, width=bw, tags=tags,
            )
        else:
            # Ghost, active zoom, or no PIL → polygon fill (fast path)
            stipple = "gray50" if ghost else ("gray25" if self._zoom_active else "")
            self.create_polygon(
                pts, fill=fill_c, outline=outline, width=bw,
                stipple=stipple,
                tags=tags,
            )

        # ── Fixed island inner gold border ───────────────────────────────────
        # A thin gold diamond drawn inset from the outer edge acts as an immediate "fixed island" marker in both image and polygon mode.
        if isl.is_fixed and not ghost:
            cx_f = (sw[0] + se[0] + ne[0] + nw[0]) / 4
            cy_f = (sw[1] + se[1] + ne[1] + nw[1]) / 4
            inset = 5
            inner_pts: list = []
            for sx_c, sy_c in (sw, se, ne, nw):
                dx, dy = sx_c - cx_f, sy_c - cy_f
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > inset:
                    f = (dist - inset) / dist
                    inner_pts.extend([cx_f + dx * f, cy_f + dy * f])
                else:
                    inner_pts.extend([cx_f, cy_f])
            self.create_polygon(inner_pts, fill="", outline=config.FG_GOLD, width=1, tags=tags)

        # ── Label ────────────────────────────────────────────────────────────
        # Only show when real images are visible (show_images=True).
        # Placeholder images have size/type labels baked in, so no text needed.
        if not ghost and PIL_AVAILABLE and self.show_images and not self._zoom_active:
            cx2 = (sw[0] + se[0] + ne[0] + nw[0]) / 4
            cy2 = (sw[1] + se[1] + ne[1] + nw[1]) / 4
            _SIZE_ABBR = {"Small": "S", "Medium": "M", "Large": "L", "ExtraLarge": "XL", "Continental": "C"}
            _TYPE_ABBR = {"Normal": "N", "Starter": "S", "ThirdParty": "T", "Pirate": "P", "Vulcan": "V", "Continental": "C"}
            size_abbr = _SIZE_ABBR.get(isl.size, isl.size[:1])
            type_abbr = _TYPE_ABBR.get(isl.island_type, isl.island_type[:1])
            lbl = ("📌" if isl.is_fixed else "") + f"{size_abbr}-{type_abbr}"
            tid = self.create_text(cx2, cy2, text=lbl, fill="#ffffff" if not sel else config.FG_GOLD, font=config.FONT_FB_BOLD, tags=tags)
            bb = self.bbox(tid)
            if bb:
                # Icons-per-row and size: smaller + wrapped at default zoom or more zoomed out
                default_scale = getattr(self, '_default_scale', self._scale)
                zoomed_out = self._scale <= default_scale
                ICON_SZ = 14 if zoomed_out else 21
                ICON_PAD = 2
                cols = 4 if zoomed_out else len(isl.fertility_guids) or 1

                # Collect fertility icon images to draw inside the label box.
                # If the island uses randomized fertility (resolved at export), show a small indicator instead of icons.
                fert_icons = []  # list of (PhotoImage | None)
                show_rand_indicator = (
                    not isl.is_ship_spawn
                    and (
                        not isl.is_fixed                                          # random pool island
                        or (isl.is_fixed and isl.randomize_fertilities            # fixed, unresolved
                            and not isl.fertility_guids)
                    )
                )
                if isl.is_fixed and isl.fertility_guids:
                    from fertility_registry import FertilityRegistry
                    freg = FertilityRegistry.instance()
                    if freg.is_loaded:
                        for guid in isl.fertility_guids:
                            cache_key = (guid, ICON_SZ)
                            if cache_key not in self._fert_icon_cache:
                                asset = freg.find_by_guid(guid)
                                if asset and os.path.isfile(asset.icon_path):
                                    try:
                                        fi = Image.open(asset.icon_path).convert("RGBA").resize(
                                            (ICON_SZ, ICON_SZ), Image.LANCZOS
                                        )
                                        self._fert_icon_cache[cache_key] = ImageTk.PhotoImage(fi)
                                    except Exception:
                                        self._fert_icon_cache[cache_key] = None
                                else:
                                    self._fert_icon_cache[cache_key] = None
                            fert_icons.append(self._fert_icon_cache[cache_key])
                num_rows = math.ceil(len(fert_icons) / cols) if fert_icons else 0
                max_cols_in_row = min(len(fert_icons), cols)
                icon_row_w = max_cols_in_row * ICON_SZ + max(0, max_cols_in_row - 1) * ICON_PAD
                icon_block_h = (num_rows * ICON_SZ + max(0, num_rows - 1) * ICON_PAD if fert_icons else 0)

                RAND_ICON_H = ICON_SZ if show_rand_indicator else 0
                RAND_ICON_W = 2 * ICON_SZ + ICON_PAD if show_rand_indicator else 0
                text_w = bb[2] - bb[0]
                text_h = bb[3] - bb[1]
                bg_w = max(1, max(text_w, icon_row_w, RAND_ICON_W) + 8)
                bg_h = max(1, text_h + 6
                           + (icon_block_h + 4 if fert_icons else 0)
                           + (RAND_ICON_H + 4 if show_rand_indicator else 0))
                r, g, b = _hex_to_rgb(config.BG_SECTION)
                bg_img = Image.new("RGBA", (bg_w, bg_h), (r, g, b, 128))
                tk_bg = ImageTk.PhotoImage(bg_img)
                self._label_bg_refs.append(tk_bg)
                # Centre the background box on cx2, aligned to top of text bbox
                bg_x = cx2 - bg_w / 2
                bg_y = bb[1] - 3
                rid = self.create_image(bg_x, bg_y, image=tk_bg, anchor="nw", tags=tags)
                self.tag_lower(rid, tid)

                # Draw fertility icons below the text, inside the background box
                if fert_icons:
                    icons_top_y = bb[3] + 3
                    icons_start_x = cx2 - icon_row_w / 2 + ICON_SZ / 2
                    for i, tk_icon in enumerate(fert_icons):
                        row_i, col_i = divmod(i, cols)
                        ix = icons_start_x + col_i * (ICON_SZ + ICON_PAD)
                        iy = icons_top_y + row_i * (ICON_SZ + ICON_PAD) + ICON_SZ / 2
                        if tk_icon is not None:
                            self.create_image(ix, iy, image=tk_icon, anchor=tk.CENTER, tags=tags)
                        else:
                            r2 = ICON_SZ // 2 - 1
                            self.create_oval(ix - r2, iy - r2, ix + r2, iy + r2, fill=config.FG_DIM, outline="", tags=tags)

                # Two-icon indicator for fixed islands with randomized fertility:
                # icon_2d_fertility  +  icon_2d_mark_question
                if show_rand_indicator:
                    icons_top_y = bb[3] + 4
                    start_x = cx2 - RAND_ICON_W / 2 + ICON_SZ / 2
                    for i, icon_path in enumerate((
                        config.RAND_FERT_ICON_PATH,
                        config.RAND_QUEST_ICON_PATH,
                    )):
                        cache_key = (icon_path, ICON_SZ)
                        if cache_key not in self._fert_icon_cache:
                            if PIL_AVAILABLE and os.path.isfile(icon_path):
                                try:
                                    fi = Image.open(icon_path).convert("RGBA").resize((ICON_SZ, ICON_SZ), Image.LANCZOS)
                                    self._fert_icon_cache[cache_key] = ImageTk.PhotoImage(fi)
                                except Exception:
                                    self._fert_icon_cache[cache_key] = None
                            else:
                                self._fert_icon_cache[cache_key] = None
                        tk_icon = self._fert_icon_cache[cache_key]
                        ix = start_x + i * (ICON_SZ + ICON_PAD)
                        iy = icons_top_y + ICON_SZ / 2
                        if tk_icon is not None:
                            self.create_image(ix, iy, image=tk_icon, anchor=tk.CENTER, tags=tags)
                        else:
                            r2 = ICON_SZ // 2 - 1
                            self.create_oval(ix - r2, iy - r2, ix + r2, iy + r2, fill=config.FG_DIM, outline="", tags=tags)

            # Locked badge
            if isl.locked:
                self.create_text(cx2, cy2 + 10, text="🔒", fill=config.FG_DIM, font=config.FONT_FB_SMALL, tags=tags)

        # ── Rotation indicator (fixed islands only) ──────────────────────────
        if isl.is_fixed:
            # White dot on the corner matching the current rotation
            # 0=South(sw), 1=East(se), 2=North(ne), 3=West(nw)
            dot_corner = (sw, se, ne, nw)[isl.rotation90 % 4]
            dr = 4
            self.create_oval(dot_corner[0] - dr, dot_corner[1] - dr, dot_corner[0] + dr, dot_corner[1] + dr, fill="#ffffff", outline="", tags=tags)
            if ghost:
                # Degree label further off-centre to clear cursor crosshair
                cx_r = (sw[0] + se[0] + ne[0] + nw[0]) / 4 + 22
                cy_r = (sw[1] + se[1] + ne[1] + nw[1]) / 4 + 22
                self.create_text(cx_r, cy_r, text=f"{isl.rotation90 * 90}°", fill="#ffffff", font=config.FONT_FB_BOLD, tags=tags)

    # ── Ghost (placement mode) ────────────────────────────────────────────────

    def _draw_ghost(self) -> None:
        if self._placing is None:
            return
        if self._placing.is_ship_spawn:
            sx, sy = self.gts(*self._placing.position)
            color = config.GHOST_VALID if self._ghost_valid else config.GHOST_INVALID
            r = 14
            self.create_oval(sx - r, sy - r, sx + r, sy + r, fill=color, outline="#ffffff", width=1, tags="ghost")
            self.create_text(sx, sy, text="⚓", fill="#ffffff", font=config.FONT_SPAWN_ICON, tags="ghost")
        else:
            self._draw_one_island(self._placing, ghost=True, valid=self._ghost_valid)
        # Secondary paste ghosts (multi-paste mode) - share the anchor's validity colour
        for pg in self._paste_ghosts:
            self._draw_one_island(pg, ghost=True, valid=self._ghost_valid)

    def _update_ghost(self, sx: float, sy: float) -> None:
        if self._placing is None:
            return
        gx, gy = self.stg(sx, sy)

        if self._placing.is_ship_spawn:
            # Spawn point: cursor = exact game position
            new_x = _snap(gx)
            new_y = _snap(gy)
        else:
            # Island: cursor lands on the visual centre of the rendered diamond
            ds = self._placing.render_size_pixels
            new_x = _snap(gx - ds / 2)
            new_y = _snap(gy - ds / 2)

        # Clamp to playable area
        if self.template is not None:
            pa = self.template.playable_area  # (x1, y1, x2, y2)
            ms = self.template.size
            if self._placing.is_ship_spawn:
                new_x = max(pa[0], min(new_x, pa[2]))
                new_y = max(pa[1], min(new_y, pa[3]))
            else:
                new_x, new_y = _clamp_island_to_pa(self._placing, pa, new_x, new_y, ms)

        self._placing.position = (new_x, new_y)

        # Reposition secondary paste ghosts relative to the anchor
        if self.template is not None and self._paste_ghosts:
            pa = self.template.playable_area
            ms = self.template.size
            for pg, (dx, dy) in zip(self._paste_ghosts, self._paste_ghost_offsets):
                pg.position = _clamp_island_to_pa(pg, pa, _snap(new_x + dx), _snap(new_y + dy), ms)

        sp = self._placing.size_pixels
        self._ghost_valid = True
        if self.template is not None:
            if self._placing.is_ship_spawn:
                self._ghost_valid = not self.template.spawn_in_island((new_x, new_y))
            else:
                self._ghost_valid = not (
                    self.template.islands_overlap_or_too_close((new_x, new_y), sp, size_str=self._placing.size)
                    or self.template.island_covers_spawn((new_x, new_y), sp)
                )
            # Validate paste ghosts against all existing template islands
            if self._ghost_valid and self._paste_ghosts:
                for pg in self._paste_ghosts:
                    pg_sz = pg.size_pixels
                    pgx, pgy = pg.position
                    if (self.template.islands_overlap_or_too_close((pgx, pgy), pg_sz, size_str=pg.size)
                            or self.template.island_covers_spawn((pgx, pgy), pg_sz)):
                        self._ghost_valid = False
                        break
        self._request_redraw()

    # ── Ghost rotation ───────────────────────────────────────────────────────

    def _rotate_ghost_cw(self) -> None:
        """Rotate the ghost island 90° clockwise (fixed islands only)."""
        if self._placing is None or self._placing.is_ship_spawn or not self._placing.is_fixed:
            return
        self._placing.rotation90 = (self._placing.rotation90 + 1) % 4
        eid = self._placing._eid
        self._img_cache = {k: v for k, v in self._img_cache.items() if not (isinstance(k, tuple) and k[0] == eid)}
        self._request_redraw()

    def _on_rotate_cw(self, _: tk.Event) -> None:
        self._rotate_ghost_cw()

    def _on_rotate_ccw(self, _: tk.Event) -> None:
        if self._placing is None or self._placing.is_ship_spawn or not self._placing.is_fixed:
            return
        self._placing.rotation90 = (self._placing.rotation90 - 1) % 4
        eid = self._placing._eid
        self._img_cache = {k: v for k, v in self._img_cache.items() if not (isinstance(k, tuple) and k[0] == eid)}
        self._request_redraw()

    def _on_double_click(self, event: tk.Event) -> None:
        """Double-click an island or spawn point to clone it into placement mode."""
        if self._placing is not None:
            return  # already in placement mode
        eid = self._island_at(event.x, event.y)
        if eid is None:
            return
        isl = self._eid_map.get(eid)
        if isl is None:
            return
        self.start_placing(isl)
        self._update_ghost(float(event.x), float(event.y))

    # ── Hit testing ──────────────────────────────────────────────────────────

    def _island_at(self, sx: float, sy: float) -> Optional[int]:
        """Return the _eid of the topmost island under (sx, sy), or None."""
        items = self.find_overlapping(sx - 4, sy - 4, sx + 4, sy + 4)
        for item in reversed(items):
            for tag in self.gettags(item):
                if tag.startswith("iid_"):
                    try:
                        return int(tag[4:])
                    except ValueError:
                        pass
        return None

    # ── Mouse events ─────────────────────────────────────────────────────────

    def _on_configure(self, _event: tk.Event) -> None:
        self.after_idle(self.redraw)
        self._update_transform()

    def _on_press(self, event: tk.Event) -> None:
        self.focus_set()

        if self._placing is not None:
            # Place the island
            if self._ghost_valid and self.template is not None:
                self.push_undo()
                pa = self.template.playable_area
                ms = self.template.size

                # Anchor island
                isl = self._placing.clone()
                isl.snap_position()
                x, y = isl.position
                if isl.is_ship_spawn:
                    isl.position = (max(pa[0], min(x, pa[2])), max(pa[1], min(y, pa[3])))
                else:
                    isl.position = _clamp_island_to_pa(isl, pa, x, y, ms)

                # Warn if continental island is deep into the border zone
                if isl.size == "Continental":
                    _warn_continental_border_zone(isl, pa, self)

                self.template.add_element(isl)

                # Secondary paste ghosts (multi-paste mode)
                new_multi: set = set()
                for pg in self._paste_ghosts:
                    pg_clone = pg.clone()
                    pg_clone.snap_position()
                    pgx, pgy = pg_clone.position
                    pg_clone.position = _clamp_island_to_pa(pg_clone, pa, pgx, pgy, ms)
                    self.template.add_element(pg_clone)
                    new_multi.add(pg_clone._eid)

                self.selected_eid = isl._eid
                self._multi_select = new_multi
                if self.on_select:
                    self.on_select(isl)
                if self.on_modify:
                    self.on_modify()
            else:
                messagebox.showwarning("Placement Invalid", "Cannot place island here: too close to another island or out of bounds.")
            self._placing = None
            self._paste_ghosts = []
            self._paste_ghost_offsets = []
            self.config(cursor="")
            self._img_cache.clear()
            self.redraw()
            return

        # ── Select-all mode: start group drag (click empty area → exit mode) ──
        if self._all_selected:
            if self._island_at(event.x, event.y) is None:
                self.deselect_all()
                return
            self._all_drag_start_s = (float(event.x), float(event.y))
            if self.template:
                from copy import deepcopy
                self._all_drag_pre_snapshot = deepcopy(self.template.elements)
                self._all_drag_orig_positions = {
                    isl._eid: isl.position
                    for isl in self.template.elements
                    if not isl.locked
                }
            return

        shift_held = bool(event.state & 0x0001)
        eid = self._island_at(event.x, event.y)

        if eid is not None:
            if shift_held:
                # Promote any existing single-selection into multi-select first
                if self.selected_eid is not None:
                    self._multi_select.add(self.selected_eid)
                # Toggle the clicked island
                if eid in self._multi_select:
                    self._multi_select.discard(eid)
                    # Keep selected_eid pointing at the clicked island's removal
                    if self.selected_eid == eid:
                        self.selected_eid = None
                else:
                    self._multi_select.add(eid)
                    self.selected_eid = eid
                    isl = self._eid_map.get(eid)
                    if self.on_select: self.on_select(isl)
                self.redraw()
                return
            else:
                isl = self._eid_map.get(eid)
                if eid in self._multi_select:
                    # Clicking a member of the existing multi-select → group drag
                    self.selected_eid = eid
                    self._multi_drag_start_s = (float(event.x), float(event.y))
                    if self.template:
                        from copy import deepcopy
                        self._multi_drag_pre_snapshot = deepcopy(self.template.elements)
                        self._multi_drag_orig_positions = {
                            e._eid: e.position
                            for e in self.template.islands
                            if e._eid in self._multi_select
                        }
                else:
                    # Normal single select - clear multi-select
                    self._multi_select.clear()
                    self.selected_eid = eid
                    self._drag_start_s = (float(event.x), float(event.y))
                    self._drag_orig_pos = isl.position if isl else (0, 0)
                    if self.template and not (isl and isl.locked):
                        from copy import deepcopy
                        self._drag_pre_snapshot = deepcopy(self.template.elements)
                if self.on_select:
                    self.on_select(isl)
        else:
            if not shift_held:
                # Start a rectangle selection drag on empty canvas
                self._rect_sel_start = (float(event.x), float(event.y))
                self._rect_sel_cur   = (float(event.x), float(event.y))
                self._multi_select.clear()
                self.selected_eid = None
                self._drag_start_s = None
                if self.on_select:
                    self.on_select(None)
        self.redraw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._placing is not None:
            self._update_ghost(event.x, event.y)
            return

        # ── Rectangle selection drag ─────────────────────────────────────────
        if self._rect_sel_start is not None:
            self._rect_sel_cur = (float(event.x), float(event.y))
            self._request_redraw()
            return

        # ── Multi-select group drag ──────────────────────────────────────────
        if self._multi_drag_start_s is not None and self._multi_select:
            if self.template is None:
                return
            dx_s = event.x - self._multi_drag_start_s[0]
            dy_s = event.y - self._multi_drag_start_s[1]
            d_gx = (dx_s - dy_s) / (self._scale * SQRT2)
            d_gy = -(dx_s + dy_s) / (self._scale * SQRT2)
            pa = self.template.playable_area
            ms = self.template.size

            # Compute proposed positions for every movable group member
            group = [e for e in self.template.islands
                     if e._eid in self._multi_select and not e.locked]
            proposed: Dict[int, Tuple[int, int]] = {}
            for isl in group:
                orig = self._multi_drag_orig_positions.get(isl._eid, isl.position)
                nx = _snap(orig[0] + d_gx)
                ny = _snap(orig[1] + d_gy)
                proposed[isl._eid] = _clamp_island_to_pa(isl, pa, nx, ny, ms)

            # Validate: check each proposed position against islands outside the group
            blocked = False
            external = [e for e in self.template.islands if e._eid not in self._multi_select]
            for isl in group:
                nx, ny = proposed[isl._eid]
                sz = isl.size_pixels
                # Overlap check vs. external islands
                for ext in external:
                    gap = (config.XL_COLLISION_GAP
                           if (isl.size == "ExtraLarge" and ext.size == "Continental") or
                              (isl.size == "Continental" and ext.size == "ExtraLarge")
                           else 0)
                    bx1, by1, bx2, by2 = ext.bounds
                    if not (nx + sz + gap > bx1 and bx2 + gap > nx
                            and ny + sz + gap > by1 and by2 + gap > ny):
                        continue
                    if gap == 0:
                        if ext.size == "Continental" and isl.size != "Continental":
                            ix1 = max(nx, bx1); iy1 = max(ny, by1)
                            ix2 = min(nx + sz, bx2); iy2 = min(ny + sz, by2)
                            if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * sz * sz:
                                continue
                        elif isl.size == "Continental" and ext.size != "Continental":
                            ext_px = config.ISLAND_SIZE_PX.get(ext.size, sz)
                            ix1 = max(nx, bx1); iy1 = max(ny, by1)
                            ix2 = min(nx + sz, bx2); iy2 = min(ny + sz, by2)
                            if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * ext_px * ext_px:
                                continue
                    blocked = True
                    break
                if blocked:
                    break
                # Spawn-coverage check
                if self.template.island_covers_spawn((nx, ny), sz):
                    blocked = True
                    break

            if not blocked:
                for isl in group:
                    isl.position = proposed[isl._eid]
                self.template.modified = True
                if self.on_modify:
                    self.on_modify()
            self._request_redraw()
            return

        # ── Select-all drag: move all non-locked islands together ────────────
        if self._all_selected:
            if self._all_drag_start_s is None:
                return
            dx_s = event.x - self._all_drag_start_s[0]
            dy_s = event.y - self._all_drag_start_s[1]
            d_gx = (dx_s - dy_s) / (self._scale * SQRT2)
            d_gy = -(dx_s + dy_s) / (self._scale * SQRT2)
            pa = self.template.playable_area if self.template else (0, 0, int(self._S), int(self._S))
            ms = self.template.size if self.template else (int(self._S), int(self._S))
            all_elements = (self.template.elements if self.template else [])
            for isl in all_elements:
                if isl.locked:
                    continue
                orig = self._all_drag_orig_positions.get(isl._eid, isl.position)
                nx = _snap(orig[0] + d_gx)
                ny = _snap(orig[1] + d_gy)
                if isl.is_ship_spawn:
                    nx = max(pa[0], min(nx, pa[2]))
                    ny = max(pa[1], min(ny, pa[3]))
                else:
                    nx, ny = _clamp_island_to_pa(isl, pa, nx, ny, ms)
                isl.position = (nx, ny)
            if self.template:
                self.template.modified = True
            if self.on_modify:
                self.on_modify()
            self._request_redraw()
            return

        # ── Normal single-island drag ─────────────────────────────────────────
        if self.selected_eid is None or self._drag_start_s is None:
            return
        isl = self._eid_map.get(self.selected_eid)
        if isl is None or isl.locked:
            return

        dx_s = event.x - self._drag_start_s[0]
        dy_s = event.y - self._drag_start_s[1]

        # Convert screen delta → game delta (inverse of the rotation)
        d_gx = (dx_s - dy_s) / (self._scale * SQRT2)
        d_gy = -(dx_s + dy_s) / (self._scale * SQRT2)

        orig = self._drag_orig_pos or isl.position
        new_x = _snap(orig[0] + d_gx)
        new_y = _snap(orig[1] + d_gy)

        # Clamp to valid bounds (PA for regular islands, map bounds for Continental)
        pa = self.template.playable_area if self.template else (0, 0, int(self._S), int(self._S))
        ms = self.template.size if self.template else (int(self._S), int(self._S))
        if isl.is_ship_spawn:
            new_x = max(pa[0], min(new_x, pa[2]))
            new_y = max(pa[1], min(new_y, pa[3]))
        else:
            new_x, new_y = _clamp_island_to_pa(isl, pa, new_x, new_y, ms)

        # Collision check
        if self.template is not None:
            if isl.is_ship_spawn:
                if self.template.spawn_in_island((new_x, new_y)):
                    return  # blocked - keep current position
            else:
                sz = isl.size_pixels
                if (
                    self.template.islands_overlap_or_too_close(
                        (new_x, new_y), sz, size_str=isl.size, exclude_eid=isl._eid)
                    or self.template.island_covers_spawn((new_x, new_y), sz)
                ):
                    return  # blocked - keep current position

        isl.position = (new_x, new_y)
        if self.template:
            self.template.modified = True
        if self.on_modify:
            self.on_modify()
        if self.on_select:
            self.on_select(isl)
        self._request_redraw()

    def _on_release(self, _event: tk.Event) -> None:
        # Finalise rectangle selection
        if self._rect_sel_start is not None:
            self._finish_rect_selection()
            self._rect_sel_start = None
            self._rect_sel_cur   = None
            self.redraw()
            return

        # Commit drag snapshot to undo stack only if something actually moved
        if self._drag_pre_snapshot is not None:
            isl = self._eid_map.get(self.selected_eid) if self.selected_eid else None
            if isl and isl.position != self._drag_orig_pos:
                self._undo_stack.append(self._drag_pre_snapshot)
                if len(self._undo_stack) > self._undo_limit:
                    self._undo_stack.pop(0)
                self._redo_stack.clear()
            self._drag_pre_snapshot = None

        if self._all_drag_pre_snapshot is not None:
            # Commit if any non-locked element moved from its original position
            moved = any(
                isl.position != self._all_drag_orig_positions.get(isl._eid, isl.position)
                for isl in (self.template.elements if self.template else [])
                if not isl.locked
            )
            if moved:
                self._undo_stack.append(self._all_drag_pre_snapshot)
                if len(self._undo_stack) > self._undo_limit:
                    self._undo_stack.pop(0)
                self._redo_stack.clear()
            self._all_drag_pre_snapshot = None

        if self._multi_drag_pre_snapshot is not None:
            moved = any(
                isl.position != self._multi_drag_orig_positions.get(isl._eid, isl.position)
                for isl in (self.template.islands if self.template else [])
                if isl._eid in self._multi_select
            )
            if moved:
                self._undo_stack.append(self._multi_drag_pre_snapshot)
                if len(self._undo_stack) > self._undo_limit:
                    self._undo_stack.pop(0)
                self._redo_stack.clear()
            self._multi_drag_pre_snapshot = None

        self._drag_start_s = None
        self._drag_orig_pos = None
        self._multi_drag_start_s = None
        self._multi_drag_orig_positions.clear()
        self._all_drag_start_s = None
        self._all_drag_orig_positions.clear()

        # Refresh selection overlay so position coordinates update in info panel
        if self.on_select and self.selected_eid is not None:
            sel_isl = self._eid_map.get(self.selected_eid)
            if sel_isl:
                self.on_select(sel_isl)

    def _on_hover(self, event: tk.Event) -> None:
        if self._placing is not None:
            self._update_ghost(event.x, event.y)
            return
        eid = self._island_at(event.x, event.y)
        if eid != self._hover_eid:
            self._hover_eid = eid
            self.config(cursor="hand2" if eid is not None else "")
            self.redraw()

    def _on_right_click(self, event: tk.Event) -> None:
        if self._placing is not None:
            self.cancel_placing()
            return
        if self._all_selected:
            eid_at = self._island_at(event.x, event.y)
            if eid_at is None:
                self.deselect_all()
                return
        eid = self._island_at(event.x, event.y)
        if eid is None:
            return
        self.selected_eid = eid
        isl = self._eid_map.get(eid)
        if isl is None:
            return
        if self.on_select:
            self.on_select(isl)
        self.redraw()
        self._show_context_menu(event, isl)

    def _cancel_place(self, _event: Optional[tk.Event] = None) -> None:
        if self._all_selected:
            self.deselect_all()
            return
        if self._placing is not None:
            self.cancel_placing()
            return
        if self._multi_select:
            self._multi_select.clear()
            self.redraw()

    # ── Rectangle selection ───────────────────────────────────────────────────

    def _draw_rect_selection(self) -> None:
        """Draw the dashed selection rectangle while the user is dragging."""
        if self._rect_sel_start is None or self._rect_sel_cur is None:
            return
        x1 = min(self._rect_sel_start[0], self._rect_sel_cur[0])
        y1 = min(self._rect_sel_start[1], self._rect_sel_cur[1])
        x2 = max(self._rect_sel_start[0], self._rect_sel_cur[0])
        y2 = max(self._rect_sel_start[1], self._rect_sel_cur[1])
        # Translucent fill
        self.create_rectangle(
            x1, y1, x2, y2,
            fill=config.SELECTION_COLOR,
            stipple="gray25",
            outline="",
            tags="rect_sel",
        )
        # Dashed border
        self.create_rectangle(
            x1, y1, x2, y2,
            fill="",
            outline=config.SELECTION_COLOR,
            width=1,
            dash=(5, 3),
            tags="rect_sel",
        )

    def _finish_rect_selection(self) -> None:
        """Select all islands whose screen-centre falls inside the drag rectangle."""
        if self.template is None or self._rect_sel_start is None or self._rect_sel_cur is None:
            return
        x1 = min(self._rect_sel_start[0], self._rect_sel_cur[0])
        y1 = min(self._rect_sel_start[1], self._rect_sel_cur[1])
        x2 = max(self._rect_sel_start[0], self._rect_sel_cur[0])
        y2 = max(self._rect_sel_start[1], self._rect_sel_cur[1])
        # Ignore tiny rects that are really just click misses
        if x2 - x1 < 5 and y2 - y1 < 5:
            return
        for isl in self.template.islands:
            cx, cy = self.gts(*isl.center)
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                self._multi_select.add(isl._eid)

    # ── Copy / Paste ──────────────────────────────────────────────────────────

    def _on_copy(self, _event: tk.Event) -> None:
        """Ctrl+C - copy all selected islands to the clipboard."""
        if self.template is None:
            return
        selected_eids = set(self._multi_select)
        if self.selected_eid is not None:
            selected_eids.add(self.selected_eid)
        if not selected_eids:
            return
        self._clipboard = [
            isl.clone()
            for isl in self.template.islands
            if isl._eid in selected_eids
        ]

    def _on_paste(self, _event: tk.Event) -> None:
        """Ctrl+V - paste clipboard islands into ghost/placement mode."""
        if self.template is None or not self._clipboard:
            return
        # Sort clipboard by position so the first island is the drag anchor
        sorted_clip = sorted(self._clipboard, key=lambda i: (i.position[0], i.position[1]))
        anchor = sorted_clip[0]
        self.start_placing(anchor)   # puts anchor into _placing ghost mode
        ax, ay = anchor.position
        # Build secondary paste ghosts from the remaining clipboard islands
        self._paste_ghosts = []
        self._paste_ghost_offsets = []
        for isl in sorted_clip[1:]:
            clone = isl.clone()
            clone.locked = False
            dx = isl.position[0] - ax
            dy = isl.position[1] - ay
            self._paste_ghosts.append(clone)
            self._paste_ghost_offsets.append((dx, dy))

    # ── Arrow-key nudge ───────────────────────────────────────────────────────

    def _on_arrow_key(self, dx_sign: int, dy_sign: int) -> None:
        """Move the selected island(s) by one GRID_SNAP step in game coordinates. dx_sign: +1=East, -1=West. dy_sign: +1=North, -1=South."""
        if self.template is None:
            return
        step = config.GRID_SNAP
        dgx = dx_sign * step
        dgy = dy_sign * step

        # Collect movable islands
        eids: set = set(self._multi_select)
        if self.selected_eid is not None:
            eids.add(self.selected_eid)
        if not eids:
            return

        movable = [isl for isl in self.template.elements
                   if isl._eid in eids and not isl.locked]
        if not movable:
            return

        pa = self.template.playable_area
        map_size = self.template.size
        external = [e for e in self.template.islands if e._eid not in eids]

        # Compute proposed positions
        proposed: Dict[int, Tuple[int, int]] = {}
        for isl in movable:
            nx = isl.position[0] + dgx
            ny = isl.position[1] + dgy
            if isl.is_ship_spawn:
                nx = max(pa[0], min(nx, pa[2]))
                ny = max(pa[1], min(ny, pa[3]))
            else:
                nx, ny = _clamp_island_to_pa(isl, pa, nx, ny, map_size)
            proposed[isl._eid] = (nx, ny)

        # Validate against external islands
        blocked = False
        for isl in movable:
            nx, ny = proposed[isl._eid]
            if isl.is_ship_spawn:
                if self.template.spawn_in_island((nx, ny)):
                    blocked = True
                    break
                continue
            sz = isl.size_pixels
            for ext in external:
                gap = (config.XL_COLLISION_GAP
                       if (isl.size == "ExtraLarge" and ext.size == "Continental") or (isl.size == "Continental" and ext.size == "ExtraLarge")
                       else 0)
                bx1, by1, bx2, by2 = ext.bounds
                if not (nx + sz + gap > bx1 and bx2 + gap > nx
                        and ny + sz + gap > by1 and by2 + gap > ny):
                    continue
                if gap == 0:
                    if ext.size == "Continental" and isl.size != "Continental":
                        ix1 = max(nx, bx1); iy1 = max(ny, by1)
                        ix2 = min(nx + sz, bx2); iy2 = min(ny + sz, by2)
                        if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * sz * sz:
                            continue
                    elif isl.size == "Continental" and ext.size != "Continental":
                        ext_px = config.ISLAND_SIZE_PX.get(ext.size, sz)
                        ix1 = max(nx, bx1); iy1 = max(ny, by1)
                        ix2 = min(nx + sz, bx2); iy2 = min(ny + sz, by2)
                        if max(0, ix2 - ix1) * max(0, iy2 - iy1) <= 0.10 * ext_px * ext_px:
                            continue
                blocked = True
                break
            if blocked:
                break
            if self.template.island_covers_spawn((nx, ny), sz):
                blocked = True
                break

        if blocked:
            return

        self.push_undo()
        for isl in movable:
            isl.position = proposed[isl._eid]
        self.template.modified = True

        if self.on_modify:
            self.on_modify()

        # Refresh selection overlay so coordinates update in the info panel
        if self.on_select and self.selected_eid is not None:
            sel_isl = self._eid_map.get(self.selected_eid) or self.template.find_by_eid(self.selected_eid)
            if sel_isl:
                self.on_select(sel_isl)

        self.redraw()

    # ── Context menu ─────────────────────────────────────────────────────────

    def _show_context_menu(self, event: tk.Event, isl: IslandElement) -> None:
        menu = tk.Menu(self, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD, font=config.FONT_FB_SMALL)
        if isl.is_ship_spawn:
            menu.add_command(label="Duplicate Spawnpoint", command=lambda: self._duplicate_island(isl))
            menu.add_separator()
            menu.add_command(label="Delete Spawnpoint", foreground="#e74c3c", command=self.delete_selected)
            menu.tk_popup(event.x_root, event.y_root)
            return
        menu.add_command(
            label=f"Edit: {isl.display_name}",
            command=lambda: self._edit_island(isl),
        )
        if not isl.is_fixed:
            menu.add_command(
                label="Convert to Custom Island…",
                command=lambda: self._convert_to_custom(isl),
            )
        menu.add_command(
            label="Duplicate",
            command=lambda: self._duplicate_island(isl),
        )
        if isl.locked:
            menu.add_command(
                label="Unlock",
                command=lambda: self._toggle_lock(isl),
            )
        else:
            menu.add_command(
                label="Lock",
                command=lambda: self._toggle_lock(isl),
            )
        menu.add_separator()
        menu.add_command(
            label="Delete",
            foreground="#e74c3c",
            command=self.delete_selected,
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _convert_to_custom(self, isl: IslandElement) -> None:
        """Convert a random island to a custom (fixed) island via the picker dialog."""
        if self.template is None or isl.is_ship_spawn or isl.is_fixed:
            return
        from dialogs import FixedIslandPickerDialog
        self.push_undo()
        region = getattr(isl, '_region', self.region)
        dlg = FixedIslandPickerDialog(self.winfo_toplevel(), region=region)
        if dlg.result:
            fixed = dlg.result
            isl.element_type   = 0
            isl.map_file_path  = fixed.map_file_path
            isl.size           = fixed.size
            isl.island_type    = fixed.island_type
            isl.island_label   = fixed.island_label
            isl.rotation90     = 0
            isl.fertility_guids      = []
            isl.randomize_fertilities = True
            self.invalidate_image(isl._eid)
            if self.on_select:
                self.on_select(isl)
            if self.on_modify:
                self.on_modify()
            self.redraw()
        else:
            self._undo_stack.pop()

    def _edit_island(self, isl: IslandElement) -> None:
        from dialogs import IslandPropertiesDialog
        self.push_undo()
        dlg = IslandPropertiesDialog(self.winfo_toplevel(), isl)
        if dlg.result:
            self.invalidate_image(isl._eid)
            if self.on_modify:
                self.on_modify()
            self.redraw()
        else:
            # Dialog cancelled - roll back the snapshot we just pushed
            self._undo_stack.pop()

    def _duplicate_island(self, isl: IslandElement) -> None:
        """Enter ghost-placement mode with a clone of *isl*.

        The user positions the ghost freely with full collision detection; a click commits it (push_undo + add_element are handled by the existing placement-commit path in _on_press).
        """
        if self.template is None:
            return
        clone = isl.clone()
        clone.locked = False
        # Set up ghost mode directly (avoids the double-clone that start_placing would introduce, since start_placing also calls .clone()).
        self._placing = clone
        self._paste_ghosts = []
        self._paste_ghost_offsets = []
        self.config(cursor="crosshair")
        self.redraw()

    def _toggle_lock(self, isl: IslandElement) -> None:
        self.push_undo()
        isl.locked = not isl.locked
        if self.template:
            self.template.modified = True
        if self.on_modify:
            self.on_modify()
        self.redraw()

    # ── Convenience aliases (used by app_window) ──────────────────────────────

    def set_template(self, template: Optional[MapTemplate]) -> None:
        """Alias for load_template; also accepts None to clear."""
        if template is None:
            self.template = None
            self.selected_eid = None
            self._placing = None
            self.clear_image_cache()
            self.redraw()
        else:
            self.load_template(template)

    def start_placement(self, ghost: IslandElement) -> None:
        """Alias for start_placing."""
        self.start_placing(ghost)

    def cancel_placement(self) -> None:
        """Alias for cancel_placing."""
        self.cancel_placing()

    # ── Zoom & fit ────────────────────────────────────────────────────────────

    def zoom(self, direction: int) -> None:
        """Zoom in (direction > 0) or out (direction < 0)."""
        factor = 1.15 if direction > 0 else (1 / 1.15)
        self._scale = max(0.05, min(5.0, self._scale * factor))
        self.redraw()

    def fit_view(self) -> None:
        """Scale and centre the map to fill the visible canvas."""
        w = self.winfo_width()  or 800
        h = self.winfo_height() or 600
        s = float(self._S)
        # The diamond fits inside a square with diagonal = s*sqrt(2).
        # We want that diagonal to fit the shorter screen dimension.
        import math
        diag = s * math.sqrt(2)
        self._scale = 0.9 * min(w, h) / diag
        self._cx = w / 2
        self._cy = h / 2
        self.redraw()

    def _on_scroll(self, event: tk.Event) -> None:
        up = event.num == 4 or getattr(event, 'delta', 0) > 0
        step = 40

        if event.state & 0x0004: # Ctrl → pan vertical
            self._cy += step if up else -step
        elif event.state & 0x0001: # Shift → pan horizontal
            self._cx += step if up else -step
        else: # plain → zoom
            factor = 1.12 if up else (1 / 1.12)
            new_scale = max(0.03, min(8.0, self._scale * factor))
            sx, sy = float(event.x), float(event.y)
            self._cx = sx + (self._cx - sx) * (new_scale / self._scale)
            self._cy = sy + (self._cy - sy) * (new_scale / self._scale)
            self._scale = new_scale
            if self.on_zoom_change:
                self.on_zoom_change(self._scale)
            # Fast mode: skip PIL image processing during rapid zoom
            self._zoom_active = True
            if self._zoom_settle_id is not None:
                self.after_cancel(self._zoom_settle_id)
            self._zoom_settle_id = self.after(225, self._zoom_settle)

        self._request_redraw()

    def _zoom_settle(self) -> None:
        """Called 225ms after the last zoom scroll event; restores full image rendering."""
        self._zoom_active = False
        self.F = None
        self._img_cache.clear()
        self.redraw()

    def _on_scroll_all(self, event: tk.Event) -> None:
        """Handles MouseWheel on Windows - only act if pointer is over this canvas and the event did not originate inside a modal dialog."""
        try:
            # If the event came from a widget in a different Toplevel (e.g. a dialog), don't scroll the canvas.
            if event.widget.winfo_toplevel() is not self.winfo_toplevel():
                return
        except Exception:
            pass
        x, y = self.winfo_rootx(), self.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        px, py = event.x_root, event.y_root
        if x <= px <= x + w and y <= py <= y + h:
            self._on_scroll(event)

    def _on_pan_start(self, event: tk.Event) -> None:
        self._pan_start_s = (float(event.x), float(event.y))
        self._pan_start_c = (self._cx, self._cy)

    def _on_pan_drag(self, event: tk.Event) -> None:
        if self._pan_start_s is None:
            return
        dx = event.x - self._pan_start_s[0]
        dy = event.y - self._pan_start_s[1]
        self._cx = self._pan_start_c[0] + dx
        self._cy = self._pan_start_c[1] + dy
        self._request_redraw()

    def _on_pan_end(self, event: tk.Event) -> None:
        # Rotate ghost island on middle-click only when mouse travel was small (distinguishes a click-to-rotate from a drag-to-pan gesture).
        if self._pan_start_s is not None:
            if self._placing is not None and not self._placing.is_ship_spawn:
                dx = event.x - self._pan_start_s[0]
                dy = event.y - self._pan_start_s[1]
                if dx * dx + dy * dy < 25:  # < 5 px radius
                    self._rotate_ghost_cw()
            self._pan_start_s = None

    def reset_zoom(self) -> None:
        """Fit the map to the canvas.  Always recomputes from current size so tabs that weren't visible at load time (Albion) get correct values."""
        self.fit_view()
        if self.on_zoom_change:
            self.on_zoom_change(self._scale)

    def _draw_legend(self) -> None:
        w = self.winfo_width() or 800
        h = self.winfo_height() or 600

        # ── Selection overlay (top-right) ─────────────────────────────────────
        # Text is drawn left-aligned at a temporary x=0 origin, then shifted so the right edge of the bounding box sits exactly 10 px from the canvas edge - matching the other legends' margins.
        if self._sel_overlay_lines:
            y = 10
            sel_ids = []
            # Golden heading first (top of box)
            sel_ids.append(self.create_text(
                0, y, text="Selection",
                anchor="nw", fill=config.FG_GOLD, font=config.FONT_XSMALL,
                tags="sel_overlay",
            ))
            y += 16
            for line in self._sel_overlay_lines:
                sel_ids.append(self.create_text(
                    0, y, text=line,
                    anchor="nw",
                    fill=config.FG_MAIN,
                    font=config.FONT_SMALL,
                    tags="sel_overlay",
                ))
                y += 17
            bb = self.bbox("sel_overlay")
            if bb and sel_ids:
                shift = (w - 10) - bb[2]
                for item_id in sel_ids:
                    self.move(item_id, shift, 0)
                bb = self.bbox("sel_overlay") # recompute after shift
                pad_x, pad_y = 8, 6
                rid = self.create_rectangle(
                    bb[0] - pad_x, bb[1] - pad_y, bb[2] + pad_x, bb[3] + pad_y,
                    fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1,
                )
                self.tag_lower(rid, sel_ids[0])

        # ── Controls legend (bottom-right) ───────────────────────────────────
        # Two-column layout: input label (left) | action (right), golden header.
        # Mirrors the abbreviation legend style on the opposite corner.
        # Text is drawn at a temporary x=0 origin, then shifted so the right edge of the bounding box sits exactly 10 px from the canvas edge - matching the left legend's 10 px left margin.
        ctrl_rows = [
            ("🖱  Scroll",         "Zoom"),
            ("🖱  Ctrl+Scroll",    "Pan ↕"),
            ("🖱  Shift+Scroll",   "Pan ↔"),
            ("🖱  Middle+Drag",    "Pan"),
        ]
        TAB_W = 118 # x offset from left of input column to start of action column
        y = h - 10
        ctrl_ids = []
        # Data rows - built bottom-to-top (reversed) so header ends up on top
        for input_lbl, action_lbl in reversed(ctrl_rows):
            ctrl_ids += [
                self.create_text(
                    0, y, text=input_lbl,
                    anchor="sw", fill=config.FG_MAIN, font=config.FONT_XSMALL,
                    tags="ctrl_legend"
                ),
                self.create_text(
                    TAB_W, y, text=action_lbl,
                    anchor="sw", fill=config.FG_DIM, font=config.FONT_XSMALL,
                    tags="ctrl_legend"
                ),
            ]
            y -= 14
        # Golden header (created last → highest z-order, visually on top)
        ctrl_ids.append(self.create_text(
            0, y, text="Controls",
            anchor="sw", fill=config.FG_GOLD, font=config.FONT_XSMALL,
            tags="ctrl_legend"
        ))
        # Shift all items so the right edge of the group sits 10 px from canvas edge
        bb = self.bbox("ctrl_legend")
        if bb and ctrl_ids:
            shift = (w - 10) - bb[2]
            for item_id in ctrl_ids:
                self.move(item_id, shift, 0)
            bb = self.bbox("ctrl_legend")   # recompute after shift
            pad_x, pad_y = 8, 6
            rid = self.create_rectangle(
                bb[0] - pad_x, bb[1] - pad_y, bb[2] + pad_x, bb[3] + pad_y,
                fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1
            )
            # Lower background below first-created (lowest z-order) ctrl item
            self.tag_lower(rid, ctrl_ids[0])

        # ── Abbreviation legend (bottom-left) ────────────────────────────────
        # Each data row: ((left_abbr, left_name), (right_abbr, right_name))
        # Header rows: plain (str, str); special rows: plain (str, str) with no right.
        # Abbr drawn at fixed x; name drawn at x+ABBR_W so all names align.
        ABBR_W  = 22 # pixels reserved for the abbreviation column ("XL" is the widest)
        COL2_X  = 100 # x offset for the right column pair
        abbr_lines = [
            ("Size", "Type"), # header
            (("S",  "Small"),       ("N", "Normal")),
            (("M",  "Medium"),      ("S", "Starter")),
            (("L",  "Large"),       ("T", "3rd Party")),
            (("XL", "Extra Large"), ("P", "Pirate")),
            (("C",  "Continental"), ("V", "Vulcan")),
            None,
            ("📌", "Fixed island"), # special
        ]
        x = 10
        y = h - 10
        abbr_ids = []
        sep_ids  = []
        for item in reversed(abbr_lines):
            if item is None:
                sep_ids.append(y - 10)
                y -= 14
                continue
            left, right = item
            if isinstance(left, tuple):
                # Data row - draw abbr at fixed x, name at x+ABBR_W (both sides)
                la, ln = left
                ra, rn = right
                abbr_ids += [
                    self.create_text(x,           y, text=la, anchor="sw", fill=config.FG_MAIN, font=config.FONT_XSMALL, tags="abbr_legend"),
                    self.create_text(x + ABBR_W,  y, text=ln, anchor="sw", fill=config.FG_DIM,  font=config.FONT_XSMALL, tags="abbr_legend"),
                    self.create_text(x + COL2_X,           y, text=ra, anchor="sw", fill=config.FG_MAIN, font=config.FONT_XSMALL, tags="abbr_legend"),
                    self.create_text(x + COL2_X + ABBR_W,  y, text=rn, anchor="sw", fill=config.FG_DIM,  font=config.FONT_XSMALL, tags="abbr_legend"),
                ]
            elif right:
                # Header or special two-string row
                abbr_ids += [
                    self.create_text(x,          y, text=left,  anchor="sw", fill=config.FG_GOLD, font=config.FONT_XSMALL, tags="abbr_legend"),
                    self.create_text(x + COL2_X, y, text=right, anchor="sw", fill=config.FG_GOLD, font=config.FONT_XSMALL, tags="abbr_legend"),
                ]
            else:
                # Single-string special row (📌)
                abbr_ids.append(
                    self.create_text(x, y, text=f"{left}  {right}" if right else left, anchor="sw", fill=config.FG_GOLD, font=config.FONT_XSMALL, tags="abbr_legend")
                )
            y -= 14
        bb2 = self.bbox("abbr_legend")
        if bb2 and abbr_ids:
            pad_x, pad_y = 8, 6
            rid2 = self.create_rectangle(
                bb2[0] - pad_x, bb2[1] - pad_y, bb2[2] + pad_x, bb2[3] + pad_y,
                fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1,
            )
            self.tag_lower(rid2, abbr_ids[0])
            # Draw separator lines inside the box
            for sep_y in sep_ids:
                self.create_line(
                    bb2[0] - pad_x + 4, sep_y,
                    bb2[2] + pad_x - 4, sep_y,
                    fill=config.FG_DIM, width=2,
                )

        # ── Statistics panel (top-left) ───────────────────────────────────────
        # Shows island counts grouped by type with size sub-rows, plus ship spawns and total.  Number column is right-aligned at a fixed x.
        if self.template is not None:
            from collections import Counter
            islands = self.template.islands

            # Build per-type size counters.  Continental is keyed by size, not island_type, because the game engine uses size=="Continental" to identify corner islands regardless of their island_type value.
            SIZE_ABBR   = [("Small", "S"), ("Medium", "M"), ("Large", "L"), ("ExtraLarge", "XL")]
            type_totals: Counter = Counter()
            type_sizes: dict = {} # type_key → Counter({size: n})
            for isl in islands:
                key = "Continental" if isl.size == "Continental" else isl.island_type
                type_totals[key] += 1
                type_sizes.setdefault(key, Counter())[isl.size] += 1

            spawn_count = len(self.template.ship_spawns)
            total = len(islands)

            # Display order: (type_key, display_label)
            stat_rows = [
                ("Normal",      config.ISLAND_TYPE_LABELS.get("Normal",      "Standard")),
                ("Starter",     config.ISLAND_TYPE_LABELS.get("Starter",     "Starter")),
                ("ThirdParty",  config.ISLAND_TYPE_LABELS.get("ThirdParty",  "3rd Party")),
                ("Pirate",      config.ISLAND_TYPE_LABELS.get("Pirate",      "Pirate")),
                ("Vulcan",      config.ISLAND_TYPE_LABELS.get("Vulcan",      "Vulcan")),
                ("Continental", config.ISLAND_TYPE_LABELS.get("Continental", "Continental")),
            ]

            x_stat   = 10
            y_stat   = 10
            NUM_X    = 140 # right edge of the count column, relative to x_stat
            INDENT   = 10 # extra left indent for size sub-rows
            stat_ids = []

            # Golden header
            stat_ids.append(self.create_text(
                x_stat, y_stat, text="Statistics",
                anchor="nw", fill=config.FG_GOLD, font=config.FONT_XSMALL,
                tags="stat_panel",
            ))
            y_stat += 16

            # One main row per island type, with an indented size sub-row below
            for type_key, label in stat_rows:
                count = type_totals[type_key]
                stat_ids.append(self.create_text(
                    x_stat, y_stat, text=label,
                    anchor="nw", fill=config.FG_MAIN, font=config.FONT_XSMALL,
                    tags="stat_panel",
                ))
                stat_ids.append(self.create_text(
                    x_stat + NUM_X, y_stat, text=str(count),
                    anchor="ne", fill=config.FG_MAIN, font=config.FONT_XSMALL,
                    tags="stat_panel",
                ))
                y_stat += 14

                # Size sub-row: only sizes present, skipped for Continental
                # (continental count IS the size count, so sub-row is redundant)
                if type_key != "Continental" and count > 0:
                    sc = type_sizes.get(type_key, Counter())
                    parts = [f"{sc[sz]} {abbr}" for sz, abbr in SIZE_ABBR if sc[sz] > 0]
                    if parts:
                        stat_ids.append(self.create_text(
                            x_stat + INDENT, y_stat,
                            text=" | ".join(parts),
                            anchor="nw", fill=config.FG_DIM, font=config.FONT_XSMALL,
                            tags="stat_panel",
                        ))
                        y_stat += 12

            sep_y_spawn = y_stat + 3
            y_stat += 10

            # Ship spawns row
            stat_ids.append(self.create_text(
                x_stat, y_stat,
                text="Ship Spawn" + ("s" if spawn_count != 1 else ""),
                anchor="nw", fill=config.FG_DIM, font=config.FONT_XSMALL,
                tags="stat_panel",
            ))
            stat_ids.append(self.create_text(
                x_stat + NUM_X, y_stat, text=str(spawn_count),
                anchor="ne", fill=config.FG_MAIN, font=config.FONT_XSMALL,
                tags="stat_panel",
            ))
            y_stat += 14

            sep_y_total = y_stat + 3
            y_stat += 10

            # Total row (golden label to match the header)
            stat_ids.append(self.create_text(
                x_stat, y_stat, text="Total",
                anchor="nw", fill=config.FG_GOLD, font=config.FONT_XSMALL,
                tags="stat_panel",
            ))
            stat_ids.append(self.create_text(
                x_stat + NUM_X, y_stat, text=str(total),
                anchor="ne", fill=config.FG_MAIN, font=config.FONT_XSMALL,
                tags="stat_panel",
            ))

            # Background box + separator lines
            bb3 = self.bbox("stat_panel")
            if bb3 and stat_ids:
                pad_x, pad_y = 8, 6
                rid3 = self.create_rectangle(
                    bb3[0] - pad_x, bb3[1] - pad_y,
                    bb3[2] + pad_x, bb3[3] + pad_y,
                    fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1,
                )
                self.tag_lower(rid3, stat_ids[0])
                for sep_y in (sep_y_spawn, sep_y_total):
                    self.create_line(
                        bb3[0] - pad_x + 4, sep_y,
                        bb3[2] + pad_x - 4, sep_y,
                        fill=config.FG_DIM, width=1,
                    )