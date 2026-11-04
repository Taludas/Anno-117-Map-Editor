"""
Anno 117 Map Template Editor - Aegyptus (DLC03) map canvas

Same 45° diamond projection as MapCanvas (canvas_view._gts/_stg), but the Aegyptus map is one fixed
jigsaw of rectangular island territories, so it is drawn differently:

  • all land is composed into ONE unrotated PIL image in game units (north-up), rotated 45° once and
    cached until the template or the zoom changes
  • three looks: the game's island images on their quadrant background, the seed-finder tile maps,
    or "cutouts" - each island's playable territory filled with its size colour
  • islands are never moved one by one (their territories tile the delta); a whole complex (quadrant)
    can be moved or removed, the ship spawn can be dragged
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import math
import os
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple

import config
import egypt_data as ed
from egypt_model import EgyptElement, EgyptTemplate, LAYER_AUTO, LAYER_FULL, LAYER_REDUCED
from canvas_view import _gts, _stg, _snap, _hex_to_rgb, SQRT2

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

MODE_IMAGES, MODE_TILES, MODE_CUTOUTS = "images", "tiles", "cutouts"
MAX_COMPOSITE_PX = 2600
UNDO_LIMIT = 50


class EgyptCanvas(tk.Canvas):

    def __init__(self, parent: tk.Widget, **kwargs):
        bg = kwargs.pop("bg", config.CANVAS_BG)
        super().__init__(parent, bg=bg, highlightthickness=0, **kwargs)
        self.region = ed.REGION
        self.template: Optional[EgyptTemplate] = None

        self._cx = 400.0
        self._cy = 400.0
        self._scale = 0.15
        self._S = float(ed.MAP_SIZE)
        self._default_scale = self._scale
        self.on_zoom_change: Optional[Callable[[float], None]] = None

        self.show_images = True
        # Moving/rotating islands and complexes cuts through land (island borders do not follow the coast), so
        # it stays off until the user explicitly unlocks it in the side panel.
        self.free_edit = False
        self.move_complexes = False
        self.ignore_collisions = False

        self.selected_eid: Optional[int] = None
        self.selected_quadrant: Optional[str] = None
        self._hover_eid: Optional[int] = None

        self._drag_kind: Optional[str] = None          # "quadrant" | "island" | "spawn"
        self._drag_start_g: Optional[Tuple[float, float]] = None
        self._drag_quadrant: Optional[str] = None
        self._drag_island: Optional[EgyptElement] = None
        self._drag_valid = True
        self._drag_delta = (0, 0)
        self._drag_spawn: Optional[EgyptElement] = None
        self._drag_snapshot: Optional[dict] = None
        self._pan_start_s: Optional[Tuple[float, float]] = None
        self._pan_start_c = (0.0, 0.0)

        self._version = 0
        self._composite_key = None
        self._composite_tk = None
        self._composite_center = (0.0, 0.0)
        self._bg_cache: Dict = {}
        self._icon_cache: Dict = {}
        self._sel_overlay_lines: List[str] = []
        self._zoom_active = False
        self._zoom_settle_id: Optional[str] = None
        self._redraw_pending = False

        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []

        self.on_select: Optional[Callable[[Optional[EgyptElement], Optional[str]], None]] = None
        self.on_modify: Optional[Callable[[], None]] = None
        self.on_edit: Optional[Callable[[EgyptElement], None]] = None

        self._needs_fit = False
        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Motion>", self._on_hover)
        self.bind("<ButtonPress-3>", self._on_right_click)
        self.bind("<ButtonPress-2>", self._on_pan_start)
        self.bind("<B2-Motion>", self._on_pan_drag)
        self.bind("<ButtonRelease-2>", lambda _e: setattr(self, "_pan_start_s", None))
        self.bind("<Button-4>", self._on_scroll)
        self.bind("<Button-5>", self._on_scroll)
        self.bind("<Escape>", lambda _e: self.deselect_all())
        self.bind(".", lambda _e: self.rotate_selection(1))
        self.bind(",", lambda _e: self.rotate_selection(-1))
        self.bind("<Delete>", lambda _e: self.delete_selected())
        self.bind("<Enter>", lambda _e: self.focus_set())
        self.after(50, self.redraw)

    # ── public API (mirrors MapCanvas where the app calls it) ────────────────

    @property
    def mode(self) -> str:
        if not self.show_images:
            return MODE_CUTOUTS
        return MODE_TILES if getattr(config, "ISLAND_IMAGE_STYLE", "artwork") == "tiles" else MODE_IMAGES

    def set_template(self, template: Optional[EgyptTemplate]) -> None:
        self.template = template
        self.selected_eid = None
        self.selected_quadrant = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.invalidate()
        self.after(10, self.fit_view)

    def invalidate(self) -> None:
        self._version += 1
        self._composite_key = None
        self._request_redraw()

    def clear_image_cache(self) -> None:
        self._composite_key = None
        self._icon_cache.clear()

    def get_selected(self) -> Optional[EgyptElement]:
        return self.template.by_eid(self.selected_eid) if (self.template and self.selected_eid) else None

    def set_selection_overlay(self, lines: List[str]) -> None:
        self._sel_overlay_lines = lines
        self._request_redraw()

    def set_warnings(self, warnings: List[str]) -> None:
        self._warnings = warnings
        self._request_redraw()

    def push_undo(self) -> None:
        if not self.template:
            return
        self._undo_stack.append(self.template.snapshot())
        if len(self._undo_stack) > UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def discard_last_undo(self) -> None:
        if self._undo_stack:
            self._undo_stack.pop()

    def undo(self) -> bool:
        return self._swap_state(self._undo_stack, self._redo_stack)

    def redo(self) -> bool:
        return self._swap_state(self._redo_stack, self._undo_stack)

    def _swap_state(self, src: List[dict], dst: List[dict]) -> bool:
        if not self.template or not src:
            return False
        dst.append(self.template.snapshot())
        self.template.restore(src.pop())
        self.selected_eid = None
        self.selected_quadrant = None
        self._notify_select()
        self._changed()
        return True

    def select_all(self) -> None:
        pass

    def deselect_all(self) -> None:
        self.selected_eid = None
        self.selected_quadrant = None
        self._notify_select()
        self._request_redraw()

    def rotate_selection(self, direction: int) -> None:
        """Turn the selected island 90° in place: +1 clockwise, -1 counter-clockwise (only with free editing on)."""
        e = self.get_selected()
        if not self.template or not e or e.is_spawn or not self.free_edit:
            return
        turns = -direction   # Rotation90 counts counter-clockwise quarter turns
        new_rot = (e.rotation + turns) % 4
        if not self.ignore_collisions and not self.template.can_place_element(e, rot=new_rot):
            self.bell()
            return
        self.push_undo()
        self.template.rotate_element(e, turns)
        self._changed()
        self._notify_select()

    def delete_selected(self) -> None:
        """Delete removes the selected complex (islands of Aegyptus cannot be removed on their own)."""
        q = self.selected_quadrant
        if not self.template or not q:
            return
        if not messagebox.askyesno(
                "Remove Complex",
                f"Remove the whole {ed.quadrant_label(q)} complex "
                f"({len(self.template.quadrant_elements(q))} islands)?\n\n"
                "It can be restored from the side panel.", parent=self):
            return
        self.push_undo()
        self.template.remove_quadrant(q)
        self.selected_eid = None
        self.selected_quadrant = None
        self._notify_select()
        self._changed()

    def restore_quadrant(self, q: str) -> None:
        if not self.template or q not in self.template.removed:
            return
        self.push_undo()
        self.template.restore_quadrant(q)
        if not self._quadrant_free(q):
            messagebox.showwarning(
                "Complex Overlaps",
                f"The {ed.quadrant_label(q)} complex was restored at its original place, which another "
                "moved complex now overlaps. Move one of them apart.", parent=self)
        self._changed()

    def _quadrant_free(self, q: str) -> bool:
        return self.template.can_place_quadrant(q, 0, 0)

    def select_quadrant(self, q: Optional[str]) -> None:
        self.selected_quadrant = q
        self.selected_eid = None
        self._notify_select()
        self._request_redraw()

    def set_layer_mode(self, e: EgyptElement, mode: str) -> None:
        if e.layer_mode == mode:
            return
        self.push_undo()
        e.set_layer_mode(mode)
        self._changed()
        self._notify_select()

    # ── transform / zoom ─────────────────────────────────────────────────────

    def gts(self, gx: float, gy: float) -> Tuple[float, float]:
        return _gts(gx, gy, self._cx, self._cy, self._scale, self._S)

    def stg(self, sx: float, sy: float) -> Tuple[float, float]:
        return _stg(sx, sy, self._cx, self._cy, self._scale, self._S)

    def _diamond_pts(self, x1, y1, x2, y2) -> list:
        return [*self.gts(x1, y1), *self.gts(x2, y1), *self.gts(x2, y2), *self.gts(x1, y2)]

    def fit_view(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 50:
            # Not laid out yet (e.g. the tab was selected in the same event): fit on the first real <Configure>.
            self._needs_fit = True
            return
        self._needs_fit = False
        # Frame the land (0..1920) rather than the mostly empty 2560 sea.
        land = 1920.0
        self._scale = 0.92 * min(w, h) / (land * SQRT2)
        self._default_scale = self._scale
        # centre of the land block
        ccx, ccy = _gts(land / 2, land / 2, 0, 0, self._scale, self._S)
        self._cx = w / 2 - ccx
        self._cy = h / 2 - ccy
        if self.on_zoom_change:
            self.on_zoom_change(self._scale)
        self.redraw()

    def _on_configure(self, event: tk.Event) -> None:
        if self._needs_fit and event.width >= 50 and event.height >= 50:
            self.fit_view()
        else:
            self._request_redraw()

    def reset_zoom(self) -> None:
        self.fit_view()

    def zoom(self, direction: int, at: Optional[Tuple[float, float]] = None) -> None:
        factor = 1.15 if direction > 0 else 1 / 1.15
        new = max(0.03, min(8.0, self._scale * factor))
        sx, sy = at if at else ((self.winfo_width() or 800) / 2, (self.winfo_height() or 600) / 2)
        self._cx = sx + (self._cx - sx) * (new / self._scale)
        self._cy = sy + (self._cy - sy) * (new / self._scale)
        self._scale = new
        if self.on_zoom_change:
            self.on_zoom_change(self._scale)
        self._zoom_active = True
        if self._zoom_settle_id is not None:
            self.after_cancel(self._zoom_settle_id)
        self._zoom_settle_id = self.after(400, self._zoom_settle)
        self._request_redraw()

    def _zoom_settle(self) -> None:
        self._zoom_active = False
        self._zoom_settle_id = None
        self.redraw()

    def _on_scroll(self, event: tk.Event) -> None:
        up = event.num == 4 or getattr(event, "delta", 0) > 0
        if event.state & 0x0004:
            self._cy += 40 if up else -40
            self._request_redraw()
        elif event.state & 0x0001:
            self._cx += 40 if up else -40
            self._request_redraw()
        else:
            self.zoom(1 if up else -1, at=(float(event.x), float(event.y)))

    def _on_scroll_all(self, event: tk.Event) -> None:
        try:
            if event.widget.winfo_toplevel() is not self.winfo_toplevel():
                return
        except Exception:
            pass
        x, y = self.winfo_rootx(), self.winfo_rooty()
        if x <= event.x_root <= x + self.winfo_width() and y <= event.y_root <= y + self.winfo_height():
            self._on_scroll(event)

    def _on_pan_start(self, event: tk.Event) -> None:
        self._pan_start_s = (float(event.x), float(event.y))
        self._pan_start_c = (self._cx, self._cy)

    def _on_pan_drag(self, event: tk.Event) -> None:
        if self._pan_start_s is None:
            return
        self._cx = self._pan_start_c[0] + event.x - self._pan_start_s[0]
        self._cy = self._pan_start_c[1] + event.y - self._pan_start_s[1]
        self._request_redraw()

    # ── drawing ──────────────────────────────────────────────────────────────

    def _request_redraw(self) -> None:
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after_idle(self._do_redraw)

    def _do_redraw(self) -> None:
        self._redraw_pending = False
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self._draw_outer_bg()
        if self.template is None:
            w, h = self.winfo_width() or 800, self.winfo_height() or 600
            tid = self.create_text(w / 2, h / 2, text="No Aegyptus map loaded.\nUse 'Load Vanilla Aegyptus Map' in the side panel\n"
                                                      "or File › Open XML… / Import .a7tinfo… on this tab.",
                                   fill=config.FG_GOLD, font=config.FONT_FB, justify=tk.CENTER)
            bb = self.bbox(tid)
            if bb:
                rid = self.create_rectangle(bb[0] - 18, bb[1] - 12, bb[2] + 18, bb[3] + 12,
                                            fill=config.BG_SECTION, outline=config.FG_SEPARATOR, width=1)
                self.tag_lower(rid, tid)
            return
        sx, sy = self.template.size
        self.create_polygon(self._diamond_pts(0, 0, sx, sy), fill=config.MAP_BORDER_FILL,
                            outline=config.MAP_BORDER_OUTLINE, width=2)
        pa = self.template.playable_area
        self.create_polygon(self._diamond_pts(*pa), fill=config.MAP_PLAY_FILL, outline="")
        self._draw_composite()
        self.create_polygon(self._diamond_pts(*pa), fill="", outline=config.MAP_PLAY_OUTLINE, width=3)
        self._draw_quadrant_frames()
        self._draw_selection()
        self._draw_labels()
        self._draw_spawns()
        self._draw_drag_ghost()
        self._draw_overlay()

    def _draw_outer_bg(self) -> None:
        w, h = self.winfo_width() or 800, self.winfo_height() or 600
        if PIL_AVAILABLE and os.path.isfile(config.MAP_BG_MAIN):
            key = (w, h)
            if key not in self._bg_cache:
                img = Image.open(config.MAP_BG_MAIN)
                sc = max(w / img.width, h / img.height)
                img = img.resize((int(img.width * sc), int(img.height * sc)), Image.LANCZOS)
                left, top = (img.width - w) // 2, (img.height - h) // 2
                self._bg_cache = {key: ImageTk.PhotoImage(img.crop((left, top, left + w, top + h)))}
            self.create_image(0, 0, image=self._bg_cache[key], anchor="nw")
        else:
            self.create_rectangle(0, 0, w, h, fill=config.CANVAS_BG, outline="")

    # composite -------------------------------------------------------------------------------------

    def _land_bbox(self) -> Tuple[int, int, int, int]:
        rects = [self.template.quadrant_rect(q) for q in self.template.present_quadrants()]
        if not rects:
            return (0, 0, 1, 1)
        return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))

    def _draw_composite(self) -> None:
        if not PIL_AVAILABLE or not self.template.islands:
            return
        bx0, by0, bx1, by1 = self._land_bbox()
        span = max(bx1 - bx0, by1 - by0)
        res = min(self._scale, MAX_COMPOSITE_PX / (span * SQRT2))
        # Quantise the resolution so small zoom steps reuse the cache.
        res = 2 ** (round(math.log2(res) * 4) / 4)
        key = (self._version, self.mode, round(res, 5), getattr(config, "ISLAND_IMAGE_STYLE", "artwork"))
        if key != self._composite_key:
            if self._zoom_active and self._composite_tk is not None:
                pass  # keep the old image while zooming, rescaled below
            else:
                img = self._compose(res, (bx0, by0, bx1, by1))
                rot = img.rotate(45, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
                self._composite_pil = rot
                self._composite_res = res
                self._composite_key = key
                self._composite_center = ((bx0 + bx1) / 2, (by0 + by1) / 2)
                self._composite_scaled = None
        rot = getattr(self, "_composite_pil", None)
        if rot is None:
            return
        f = self._scale / self._composite_res
        target = (max(1, int(rot.width * f)), max(1, int(rot.height * f)))
        if getattr(self, "_composite_scaled", None) != target:
            if max(target) > 6000:
                # Deep zoom: crop to the visible part before scaling.
                self._composite_tk = None
                self._draw_composite_cropped(rot, f)
                return
            scaled = rot if target == rot.size else rot.resize(target, Image.BILINEAR if self._zoom_active else Image.LANCZOS)
            self._composite_tk = ImageTk.PhotoImage(scaled)
            self._composite_scaled = target
        cx, cy = self.gts(*self._composite_center)
        self.create_image(cx, cy, image=self._composite_tk, anchor="center")

    def _draw_composite_cropped(self, rot, f: float) -> None:
        cx, cy = self.gts(*self._composite_center)
        w, h = self.winfo_width() or 800, self.winfo_height() or 600
        # screen rect of the scaled image
        sw, sh = rot.width * f, rot.height * f
        left, top = cx - sw / 2, cy - sh / 2
        x0, y0 = max(0, -left), max(0, -top)
        x1, y1 = min(sw, w - left), min(sh, h - top)
        if x1 <= x0 or y1 <= y0:
            return
        crop = rot.crop((int(x0 / f), int(y0 / f), int(math.ceil(x1 / f)), int(math.ceil(y1 / f))))
        crop = crop.resize((max(1, int(crop.width * f)), max(1, int(crop.height * f))), Image.NEAREST)
        self._composite_tk = ImageTk.PhotoImage(crop)
        self._composite_scaled = None
        self.create_image(left + int(x0 / f) * f, top + int(y0 / f) * f, image=self._composite_tk, anchor="nw")

    def _compose(self, res: float, bbox: Tuple[int, int, int, int]):
        bx0, by0, bx1, by1 = bbox
        W, H = max(1, int((bx1 - bx0) * res)), max(1, int((by1 - by0) * res))
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        def paste(src, gx0, gy0, gx1, gy1, resample=Image.LANCZOS):
            w, h = max(1, int(round((gx1 - gx0) * res))), max(1, int(round((gy1 - gy0) * res)))
            if src.size != (w, h):
                src = src.resize((w, h), resample)
            img.alpha_composite(src, (int(round((gx0 - bx0) * res)), int(round((by1 - gy1) * res))))

        def turned(im, rot):
            # Images are north-up; Rotation90 and PIL's rotate() both turn counter-clockwise.
            return im.rotate(90 * rot, expand=True) if rot else im

        def square_px(info):
            return max(1, int(round(info.map_size[0] * res)))

        mode = self.mode
        islands = ed.islands()
        if mode == MODE_IMAGES:
            # The quadrant artwork only adds thin edge slivers (~1.4 % of the land) and shows the vanilla
            # layout, so it is dropped as soon as islands of that complex were moved/rotated on their own.
            for q in self.template.present_quadrants():
                qi = islands.get(q)
                if qi and qi.image_path and os.path.isfile(qi.image_path) and self.template.quadrant_intact(q):
                    x0, y0, x1, y1 = self.template.quadrant_rect(q)
                    paste(Image.open(qi.image_path).convert("RGBA"), x0, y0, x1, y1)
            for e in self.template.islands:
                info = e.info
                if info and info.image_path and os.path.isfile(info.image_path):
                    paste(turned(Image.open(info.image_path).convert("RGBA"), e.rotation), *e.active_world_rect())
        elif mode == MODE_TILES:
            boxes = ed.tile_boxes()
            for e in self.template.islands:
                path = ed.tile_image_path(e.stem)
                box = boxes.get(e.stem)
                if not path or not box:
                    continue
                x, y = e.position
                b = ed.rotate_rect(box["box"], box["map_size"][0], e.rotation)
                paste(turned(Image.open(path).convert("RGBA"), e.rotation),
                      x + b[0], y + b[1], x + b[2], y + b[3], Image.NEAREST)
        if mode in (MODE_IMAGES, MODE_TILES):
            # Territory outline in the image-mode border colour of the matching Latium/Albion island type.
            for e in self.template.islands:
                info = e.info
                btype = self._border_type(e)
                if not info or not btype:
                    continue
                rim = config.ISLAND_COLORS_IMG.get(btype, config.ISLAND_COLORS_IMG["Normal"])
                x, y = e.position
                layer = self._island_layer(info, e.rotation, square_px(info), None, rim, land_only=False)
                paste(layer, x, y, x + info.map_size[0], y + info.map_size[1], Image.NEAREST)
        else:
            # Cutouts: only the island's land is filled, so the Nile channels stay visible; the land is
            # outlined in the no-image border colour of the matching Latium/Albion island type.
            for e in self.template.islands:
                info = e.info
                if not info:
                    continue
                fill = ed.KIND_COLORS["Large"] if e.is_starter else ed.KIND_COLORS.get(e.kind, "#888888")
                rim = config.ISLAND_COLORS.get(self._border_type(e))
                x, y = e.position
                layer = self._island_layer(info, e.rotation, square_px(info), fill, rim, land_only=True)
                paste(layer, x, y, x + info.map_size[0], y + info.map_size[1], Image.NEAREST)
        return img

    @staticmethod
    def _border_type(e: EgyptElement) -> Optional[str]:
        if e.is_starter:
            return "Starter"
        return ed.KIND_BORDER_TYPE.get(e.kind)

    _mask_cache: Dict = {}
    _layer_cache: Dict = {}
    _label_cache: Dict = {}

    @classmethod
    def _masks(cls, info: ed.IslandFile):
        """(territory, land) of an island as L images on its square map, 1 px per unit, north-up, unrotated.
        Land comes from the island's tile map; without one the whole territory counts as land."""
        if info.stem not in cls._mask_cache:
            from PIL import ImageChops
            gw, gh = info.grid
            cells = Image.new("L", (gw, gh), 0)
            px = cells.load()
            for cy in range(gh):
                for cx in range(gw):
                    if info.cell_set(cx, cy):
                        px[cx, gh - 1 - cy] = 255
            terr = cells.resize(info.map_size, Image.NEAREST)
            sq = ed.tile_square_image(info.stem)
            if sq is not None:
                land = sq.split()[3].point(lambda v: 255 if v >= 200 else 0)
                if land.size != terr.size:
                    land = land.resize(terr.size, Image.NEAREST)
                land = ImageChops.multiply(land, terr)
            else:
                land = terr
            cls._mask_cache[info.stem] = (terr, land)
        return cls._mask_cache[info.stem]

    @classmethod
    def _label_point(cls, info: ed.IslandFile) -> Tuple[float, float]:
        """Local game coordinates (unrotated) of the widest spot of the island's land, where its label fits best."""
        if info.stem not in cls._label_cache:
            _terr, land = cls._masks(info)
            step = 8
            small = land.resize((land.width // step, land.height // step), Image.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
            # Pad by one cell: MinFilter does not erode at the image edge, and land may touch the square's edge.
            core = Image.new("L", (small.width + 2, small.height + 2), 0)
            core.paste(small, (1, 1))
            while True:
                smaller = core.filter(ImageFilter.MinFilter(3))
                if not smaller.getbbox():
                    break
                core = smaller
            box = core.getbbox()
            if box:
                mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                px = core.load()
                sx, sy = min(((x, y) for y in range(box[1], box[3]) for x in range(box[0], box[2]) if px[x, y]),
                             key=lambda p: (p[0] + 0.5 - mx) ** 2 + (p[1] + 0.5 - my) ** 2)
                point = ((sx - 0.5) * step, land.height - (sy - 0.5) * step)
            else:
                x0, y0, x1, y1 = info.active_rect
                point = ((x0 + x1) / 2, (y0 + y1) / 2)
            cls._label_cache[info.stem] = point
        return cls._label_cache[info.stem]

    def _island_layer(self, info: ed.IslandFile, rot: int, size_px: int, fill: Optional[str], rim: Optional[str],
                      land_only: bool):
        """One island's cutout at *size_px* (its whole square map): land filled with *fill*, outlined with *rim*
        (around the land when *land_only*, else around the territory), about 2 screen pixels wide at any zoom."""
        key = (info.stem, rot % 4, size_px, fill, rim, land_only)
        cache = EgyptCanvas._layer_cache
        if key in cache:
            return cache[key]
        if len(cache) > 400:
            cache.clear()
        from PIL import ImageChops
        terr, land = self._masks(info)
        if rot % 4:
            terr, land = terr.rotate(90 * rot), land.rotate(90 * rot)
        size = (size_px, size_px)
        terr_s = terr.resize(size, Image.NEAREST)
        land_s = land.resize(size, Image.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        if fill:
            out.paste(Image.new("RGBA", size, _hex_to_rgb(fill) + (255,)), (0, 0), land_s)
        if rim:
            shape = land_s if land_only else terr_s
            # Pad by one pixel so a shape touching the square's edge still gets its outline there.
            padded = Image.new("L", (size_px + 2, size_px + 2), 0)
            padded.paste(shape, (1, 1))
            edge = padded.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 0 else 0)
            edge = edge.filter(ImageFilter.MaxFilter(3)).crop((1, 1, size_px + 1, size_px + 1))
            edge = ImageChops.multiply(edge, shape)
            out.paste(Image.new("RGBA", size, _hex_to_rgb(rim) + (255,)), (0, 0), edge)
        cache[key] = out
        return out

    # overlays --------------------------------------------------------------------------------------

    def _draw_quadrant_frames(self) -> None:
        for q in self.template.present_quadrants():
            sel = q == self.selected_quadrant
            if not (sel or (self.free_edit and self.move_complexes)):
                continue
            x0, y0, x1, y1 = self.template.quadrant_rect(q)
            self.create_polygon(self._diamond_pts(x0, y0, x1, y1), fill="",
                                outline=config.FG_GOLD if sel else config.FG_DIM, width=2 if sel else 1, dash=(8, 5))
            lx, ly = self.gts(x0 + 40, y1 - 40)
            self.create_text(lx, ly, text=ed.quadrant_label(q), fill=config.FG_GOLD if sel else config.FG_DIM,
                             font=config.FONT_FB_SMALL, anchor="n")

    def _draw_selection(self) -> None:
        for eid, color, width in ((self._hover_eid, config.HOVER_TINT, 1), (self.selected_eid, config.SELECTION_COLOR, 3)):
            e = self.template.by_eid(eid) if eid else None
            r = e.active_world_rect() if e else None
            if r:
                self.create_polygon(self._diamond_pts(*r), fill="", outline=color, width=width)

    def _fert_icon(self, guid: int, size: int):
        key = (guid, size)
        if key not in self._icon_cache:
            f = ed.fertility_data().fertilities.get(guid)
            icon = None
            if f and os.path.isfile(f.icon_path) and PIL_AVAILABLE:
                try:
                    icon = ImageTk.PhotoImage(Image.open(f.icon_path).convert("RGBA").resize((size, size), Image.LANCZOS))
                except Exception:
                    icon = None
            if icon is None:
                from fertility_registry import FertilityRegistry
                fa = FertilityRegistry.instance().find_by_guid(guid)
                if fa and os.path.isfile(fa.icon_path) and PIL_AVAILABLE:
                    icon = ImageTk.PhotoImage(Image.open(fa.icon_path).convert("RGBA").resize((size, size), Image.LANCZOS))
            self._icon_cache[key] = icon
        return self._icon_cache[key]

    def _draw_labels(self) -> None:
        mode = self.mode
        font_px = max(8, min(16, int(9 + self._scale * 20)))
        for e in self.template.islands:
            if not e.active_world_rect():
                continue
            lx, ly = ed.rotate_point(*self._label_point(e.info), e.info.map_size[0], e.rotation)
            cx, cy = self.gts(e.position[0] + lx, e.position[1] + ly)
            label = ed.KIND_LABELS.get(e.kind, "")
            text_px = font_px if len(label) < 3 else max(8, font_px - 4)
            if e.is_starter:
                label = "★" + label
            if e.layer_mode == LAYER_REDUCED:
                label += "↓"
            if not label:
                continue
            if mode == MODE_CUTOUTS:
                self.create_text(cx, cy, text=label,
                                 fill=config.FG_GOLD if e.is_starter else ed.KIND_LABEL_COLORS.get(e.kind, config.FG_MAIN),
                                 font=(config.FONT_HEADER[0], text_px, "bold"))
            elif e.is_fertile or e.kind != "Decoration":
                self.create_text(cx + 1, cy + 1, text=label, fill="#000000", font=("TkDefaultFont", text_px, "bold"))
                self.create_text(cx, cy, text=label, fill=config.FG_GOLD if e.is_starter else config.FG_MAIN,
                                 font=("TkDefaultFont", text_px, "bold"))
            guids = e.fertility_guids
            if guids and self._scale > 0.12:
                sz = max(12, min(22, int(self._scale * 40)))
                total = len(guids) * (sz + 1)
                x = cx - total / 2 + sz / 2
                for g in guids:
                    ic = self._fert_icon(g, sz)
                    if ic:
                        self.create_image(x, cy + font_px + sz / 2, image=ic)
                    x += sz + 1

    def _draw_spawns(self) -> None:
        r = max(5, int(self._scale * 30))
        for s in self.template.spawns:
            x, y = s.position
            if self._drag_kind == "spawn" and s is self._drag_spawn:
                x, y = x + self._drag_delta[0], y + self._drag_delta[1]
            sx, sy = self.gts(x, y)
            self.create_oval(sx - r, sy - r, sx + r, sy + r, fill=config.SHIP_SPAWN_COLOR, outline="#ffffff",
                             width=3 if s.eid == self.selected_eid else 1)
            self.create_text(sx, sy, text="⚓", fill="#ffffff", font=config.FONT_SPAWN_ICON)

    def _draw_drag_ghost(self) -> None:
        if self._drag_kind == "island" and self._drag_island and self._drag_delta != (0, 0):
            r = self._drag_island.active_world_rect(*self._drag_delta)
            if r:
                self.create_polygon(self._diamond_pts(*r), fill="",
                                    outline=config.GHOST_VALID if self._drag_valid else config.GHOST_INVALID, width=3)
            return
        if self._drag_kind != "quadrant" or not self._drag_quadrant:
            return
        dx, dy = self._drag_delta
        x0, y0, x1, y1 = self.template.quadrant_rect(self._drag_quadrant)
        ok = self.ignore_collisions or self.template.can_place_quadrant(self._drag_quadrant, dx, dy)
        self.create_polygon(self._diamond_pts(x0 + dx, y0 + dy, x1 + dx, y1 + dy), fill="",
                            outline=config.GHOST_VALID if ok else config.GHOST_INVALID, width=3)
        for e in self.template.quadrant_elements(self._drag_quadrant):
            r = e.active_world_rect()
            if r:
                self.create_polygon(self._diamond_pts(r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy), fill="",
                                    outline=config.GHOST_VALID if ok else config.GHOST_INVALID, width=1)

    def _draw_overlay(self) -> None:
        warnings = getattr(self, "_warnings", [])
        if warnings:
            h = self.winfo_height() or 600
            tid = self.create_text(18, h - 16, text="\n".join("⚠ " + w for w in warnings), fill="#e74c3c",
                                   font=config.FONT_FB_SMALL, anchor="sw", justify="left", width=520)
            bb = self.bbox(tid)
            if bb:
                rid = self.create_rectangle(bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6, fill=config.BG_SECTION,
                                            outline=config.FG_SEPARATOR)
                self.tag_lower(rid, tid)
        if not self._sel_overlay_lines:
            return
        w = self.winfo_width() or 800
        tid = self.create_text(0, 10, text="\n".join(self._sel_overlay_lines), fill=config.FG_MAIN,
                               font=config.FONT_FB_SMALL, anchor="nw", justify="left")
        bb = self.bbox(tid)
        if bb:
            dx = w - 10 - bb[2]
            self.move(tid, dx, 0)
            bb = self.bbox(tid)
            rid = self.create_rectangle(bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6, fill=config.BG_SECTION,
                                        outline=config.FG_SEPARATOR)
            self.tag_lower(rid, tid)

    # ── interaction ──────────────────────────────────────────────────────────

    def _spawn_at(self, sx: float, sy: float) -> Optional[EgyptElement]:
        r = max(8, int(self._scale * 30)) + 3
        for s in self.template.spawns:
            px, py = self.gts(*s.position)
            if (px - sx) ** 2 + (py - sy) ** 2 <= r * r:
                return s
        return None

    def _on_press(self, event: tk.Event) -> None:
        self.focus_set()
        if not self.template:
            return
        gx, gy = self.stg(event.x, event.y)
        spawn = self._spawn_at(event.x, event.y)
        if spawn:
            self.selected_eid, self.selected_quadrant = spawn.eid, None
            self._drag_kind, self._drag_spawn = "spawn", spawn
            self._drag_start_g, self._drag_delta = (gx, gy), (0, 0)
            self._notify_select()
            self._request_redraw()
            return
        e = self.template.element_at(gx, gy)
        q = e.quadrant if e else self.template.quadrant_at(gx, gy)
        complex_drag = self.free_edit and (self.move_complexes or bool(event.state & 0x0004)) and q
        if complex_drag:
            self.selected_quadrant, self.selected_eid = q, None
            self._drag_kind, self._drag_quadrant = "quadrant", q
            self._drag_start_g, self._drag_delta = (gx, gy), (0, 0)
        else:
            self.selected_eid = e.eid if e else None
            self.selected_quadrant = q if e else None
            if e and self.free_edit:
                self._drag_kind, self._drag_island = "island", e
                self._drag_start_g, self._drag_delta, self._drag_valid = (gx, gy), (0, 0), True
        self._notify_select()
        self._request_redraw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_kind not in ("quadrant", "island", "spawn") or self._drag_start_g is None:
            return
        gx, gy = self.stg(event.x, event.y)
        delta = (_snap(gx - self._drag_start_g[0]), _snap(gy - self._drag_start_g[1]))
        if delta == self._drag_delta:
            return
        self._drag_delta = delta
        if self._drag_kind == "island":
            self._drag_valid = self.ignore_collisions or self.template.can_place_element(self._drag_island, *delta)
        self._request_redraw()

    def _on_release(self, _event: tk.Event) -> None:
        kind, dx, dy = self._drag_kind, *self._drag_delta
        self._drag_kind = None
        if kind == "quadrant" and (dx or dy):
            q = self._drag_quadrant
            if self.ignore_collisions or self.template.can_place_quadrant(q, dx, dy):
                self.push_undo()
                self.template.move_quadrant(q, dx, dy)
                self._changed()
            else:
                self.bell()
        elif kind == "island" and (dx or dy):
            e = self._drag_island
            if self.ignore_collisions or self.template.can_place_element(e, dx, dy):
                self.push_undo()
                self.template.move_element(e, dx, dy)
                self._changed()
            else:
                self.bell()
        elif kind == "spawn" and (dx or dy):
            s = self._drag_spawn
            x, y = s.position
            w, h = self.template.size
            nx, ny = max(0, min(w, x + dx)), max(0, min(h, y + dy))
            if self.ignore_collisions or not self.template.element_at(nx, ny):
                self.push_undo()
                s.position = (nx, ny)
                self.template.modified = True
                self._changed(recompose=False)
            else:
                self.bell()
        self._drag_quadrant = self._drag_spawn = self._drag_island = None
        self._drag_delta = (0, 0)
        self._notify_select()
        self._request_redraw()

    def _on_double_click(self, event: tk.Event) -> None:
        if not self.template:
            return
        e = self.template.element_at(*self.stg(event.x, event.y))
        if e and self.on_edit:
            self.selected_eid, self.selected_quadrant = e.eid, e.quadrant
            self._notify_select()
            self.on_edit(e)

    def _on_hover(self, event: tk.Event) -> None:
        if not self.template or self._drag_kind:
            return
        e = self.template.element_at(*self.stg(event.x, event.y))
        eid = e.eid if e else None
        if eid != self._hover_eid:
            self._hover_eid = eid
            self._request_redraw()

    def _on_right_click(self, event: tk.Event) -> None:
        if not self.template:
            return
        gx, gy = self.stg(event.x, event.y)
        e = self.template.element_at(gx, gy)
        q = e.quadrant if e else self.template.quadrant_at(gx, gy)
        if e:
            self.selected_eid, self.selected_quadrant = e.eid, q
            self._notify_select()
            self._request_redraw()
        m = tk.Menu(self, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN,
                    activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD)
        if e:
            m.add_command(label=f"Edit {e.short}…", command=lambda: self.on_edit and self.on_edit(e))
            if e.has_layer:
                # Inline radio items: a cascade's native arrow is black and invisible on the dark menu.
                var = tk.StringVar(value=e.layer_mode)
                m.add_command(label="Island variant:", state="disabled")
                if e.can_auto_reduce:
                    m.add_radiobutton(label="   Game decides (by map size)", variable=var, value=LAYER_AUTO, selectcolor="#ffffff",
                                      command=lambda: self.set_layer_mode(e, LAYER_AUTO))
                m.add_radiobutton(label="   Always full island", variable=var, value=LAYER_FULL, selectcolor="#ffffff",
                                  command=lambda: self.set_layer_mode(e, LAYER_FULL))
                m.add_radiobutton(label="   Always reduced (_layer01)", variable=var, value=LAYER_REDUCED, selectcolor="#ffffff",
                                  command=lambda: self.set_layer_mode(e, LAYER_REDUCED))
                m._var = var
            if self.free_edit:
                m.add_command(label="Rotate 90° CW   ( . )", command=lambda: self.rotate_selection(1))
                m.add_command(label="Rotate 90° CCW  ( , )", command=lambda: self.rotate_selection(-1))
            m.add_separator()
        if q:
            m.add_command(label=f"Select {ed.quadrant_label(q)} complex", command=lambda: self.select_quadrant(q))
            m.add_command(label=f"Remove {ed.quadrant_label(q)} complex…",
                          command=lambda: (self.select_quadrant(q), self.delete_selected()))
        if self.template.removed:
            if q:
                m.add_separator()
            for rq in list(self.template.removed):
                m.add_command(label=f"Restore {ed.quadrant_label(rq)} complex",
                              command=lambda rq=rq: self.restore_quadrant(rq))
        if m.index("end") is not None:
            m.tk_popup(event.x_root, event.y_root)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _notify_select(self) -> None:
        if self.on_select:
            self.on_select(self.get_selected(), self.selected_quadrant)

    def _changed(self, recompose: bool = True) -> None:
        if recompose:
            self.invalidate()
        else:
            self._request_redraw()
        if self.on_modify:
            self.on_modify()

    # ── PNG export ───────────────────────────────────────────────────────────

    def export_png(self, filepath: str, img_size: int = 1024, show_region_name: bool = False) -> None:
        if not PIL_AVAILABLE or not self.template:
            raise RuntimeError("Nothing to export.")
        S = float(self.template.size[0])
        pa = self.template.playable_area
        span = pa[2] - pa[0]
        res = img_size / (span * SQRT2)
        land = self._compose(res * 1.0, (pa[0], pa[1], pa[2], pa[3]))
        rot = land.rotate(45, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
        base = Image.new("RGBA", rot.size, _hex_to_rgb(config.MAP_PLAY_FILL) + (255,))
        mask = Image.new("L", land.size, 255).rotate(45, expand=True, fillcolor=0)
        out = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        out.paste(base, (0, 0), mask)
        out.alpha_composite(rot)
        out = out.resize((img_size, img_size), Image.LANCZOS)
        if show_region_name:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(os.path.join(config.FONTS_DIR, "PlayfairDisplaySC-Regular.ttf"),
                                          max(1, int(64 * img_size / 1024)))
            except Exception:
                font = None
            ImageDraw.Draw(out).text((20, 20), ed.REGION, fill="#ffffff", font=font)
        out.convert("RGB").save(filepath, "PNG")
