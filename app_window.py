from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

"""
Anno 117 Map Template Editor - Main Application Window
"""

import glob
import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Dict, List
import concurrent.futures
import threading
import webbrowser

try:
    from PIL import Image as _PILImage, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

import config
import _version
import settings as _settings
import rda_handler
from models import IslandElement, MapTemplate
from canvas_view import MapCanvas
import filedb_handler as _fdb
from xml_io import load_xml, save_xml
from dialogs import IslandPropertiesDialog, NewMapDialog, AboutDialog
import mod_exporter as _mod_exp


# ─── Icon loader ────────────────────────────────────────────────────────────

_APP_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_icon(rel_path: str, size: int = 16):
    """Return a PhotoImage for *rel_path* (relative to the app directory), resized to *size*×*size*.  Returns None when PIL is unavailable or the file does not exist."""
    if not _PIL_OK:
        return None
    full = os.path.join(_APP_DIR, rel_path)
    if not os.path.isfile(full):
        return None
    try:
        img = _PILImage.open(full).convert("RGBA").resize((size, size), _PILImage.LANCZOS)
        return _PILImageTk.PhotoImage(img)
    except Exception:
        return None


# ─── Hover helper ───────────────────────────────────────────────────────────

def _bind_hover(widget, bg_idle: str, bg_hover: str) -> None:
    """Bind Enter/Leave events to flash *widget* background on hover."""
    widget.bind("<Enter>", lambda _e: widget.config(bg=bg_hover))
    widget.bind("<Leave>", lambda _e: widget.config(bg=bg_idle))


# ─── Style helpers ──────────────────────────────────────────────────────────

def _apply_ttk_style(root: tk.Tk):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TNotebook", background=config.BG_MAIN, borderwidth=0, tabmargins=[2, 4, 2, 0])
    style.configure("TNotebook.Tab", background=config.BG_SECTION, foreground=config.FG_DIM, font=config.FONT_TAB_BOLD, padding=[16, 6])
    style.map("TNotebook.Tab", background=[("selected", config.BG_HOVER), ("active", "#2e4d6e")], foreground=[("selected", config.FG_GOLD), ("active", config.FG_MAIN)])

    style.configure("Anno.TCombobox", fieldbackground=config.BG_HOVER, background=config.BG_HOVER, foreground=config.FG_MAIN, arrowcolor=config.FG_MAIN, selectbackground=config.BG_HOVER, selectforeground=config.FG_GOLD, borderwidth=0)
    style.map("Anno.TCombobox", fieldbackground=[("readonly", config.BG_HOVER)], foreground=[("readonly", config.FG_MAIN)])

    style.configure("Vertical.TScrollbar", background=config.BG_SECTION, troughcolor=config.BG_MAIN, arrowcolor=config.FG_DIM, borderwidth=0)


# ─── Region Tab ─────────────────────────────────────────────────────────────

class RegionTab(tk.Frame):
    """One tab (Latium or Albion) containing a MapCanvas + side panel."""

    def __init__(self, parent, region: str, app: "MapEditorApp"):
        super().__init__(parent, bg=config.BG_MAIN)
        self.region = region
        self.app = app
        self.canvas_widget: Optional[MapCanvas] = None
        self._build()

    def _build(self):
        # ── Side panel (right) ───────────────────────────────────────────────
        side = tk.Frame(self, bg=config.BG_SECTION, width=230)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        self._build_side(side)

        # ── Canvas area ──────────────────────────────────────────────────────
        canvas_frame = tk.Frame(self, bg=config.BG_MAIN)
        canvas_frame.pack(side="left", fill="both", expand=True)

        self.canvas_widget = MapCanvas(
            canvas_frame,
            region=self.region,
        )
        self.canvas_widget.on_select = self._on_island_select
        self.canvas_widget.on_modify = self._on_modify
        self.canvas_widget.pack(fill="both", expand=True)
        self.canvas_widget.on_zoom_change = self._on_zoom_change

    # ── Zoom ─────────────────────────────────────────────────────────────
    def _reset_zoom(self):
        if self.canvas_widget:
            self.canvas_widget.reset_zoom()

    def _on_zoom_change(self, scale: float):
        if self.canvas_widget:
            is_default = abs(scale - getattr(self.canvas_widget, '_default_scale', scale)) < 0.001
            self._reset_zoom_btn.config(
                state="disabled" if is_default else "normal",
                fg=config.FG_DIM if is_default else config.FG_MAIN
        )

    # ── Side panel ───────────────────────────────────────────────────────────

    def _build_side(self, side: tk.Frame):
        pad = dict(padx=12, pady=4)

        # Title - region name with the same icon used on the tab button
        _icon_path = (
            "data/ui/fhd/base/icon_content/generic/icon_2d_region_heartlands.png"
            if self.region == "Latium"
            else "data/ui/fhd/base/icon_content/generic/icon_2d_region_wetlands.png"
        )
        self._side_region_icon = _load_icon(_icon_path, 24)
        title_f = tk.Frame(side, bg=config.BG_SECTION)
        title_f.pack(anchor="w", pady=(14, 2), padx=2)
        if self._side_region_icon:
            tk.Label(title_f, image=self._side_region_icon, bg=config.BG_SECTION).pack(side="left", padx=(0, 4))
        tk.Label(title_f, text=self.region, bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(side="left")
        self._template_name_var = tk.StringVar(value="")
        self._template_name_lbl = tk.Label(side, textvariable=self._template_name_var, bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_XSMALL, anchor="w", wraplength=200, justify="left")
        self._template_name_lbl.pack(anchor="w", padx=2, pady=(0, 2))

        # Difficulty selector (per-region; relevant for fixed-island fertility resolution)
        diff_f = tk.Frame(side, bg=config.BG_SECTION)
        diff_f.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(diff_f, text="Difficulty:", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_XSMALL, width=10, anchor="w").pack(side="left")
        self._diff_var = tk.StringVar(value=config.DIFFICULTY_LABELS["easy"])
        diff_labels = list(config.DIFFICULTY_LABELS.values())
        self._diff_cb = ttk.Combobox(diff_f, values=diff_labels, textvariable=self._diff_var, state="readonly", width=9, font=config.FONT_XSMALL, style="Anno.TCombobox")
        self._diff_cb.pack(side="left")
        self._diff_var.trace_add("write", self._on_difficulty_change)

        tk.Frame(side, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=8, pady=4)

        # ── Place Islands - numpad-style button grid ──────────────────────────
        tk.Label(side, text="Place Islands", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=8, pady=(4, 2))

        def _pb(parent, text, cmd, fg=config.FG_MAIN, bg=config.BG_HOVER):
            """Button wrapped in a 1px border frame.
            width=1 removes natural-size pressure from long labels so that expand=True / fill='x' on the frame distributes space equally."""
            border = tk.Frame(parent, bg=config.FG_MAIN)
            btn = tk.Button(border, text=text, command=cmd, bg=bg, fg=fg, relief=tk.FLAT, font=config.FONT_SMALL, width=1, padx=4, pady=5, cursor="hand2", activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD)
            btn.pack(fill="both", expand=True, padx=1, pady=1)
            _bind_hover(btn, bg, "#2e4d6e")
            return border

        def _row_lbl(parent, text):
            tk.Label(parent, text=text, bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_XSMALL, width=7, anchor="w").pack(side="left")

        pad = tk.Frame(side, bg=config.BG_SECTION)
        pad.pack(fill="x", padx=8, pady=2)

        # Row 1 - Spawn Point
        r0 = tk.Frame(pad, bg=config.BG_SECTION)
        r0.pack(fill="x", pady=1)
        _row_lbl(r0, "Spawn")
        _pb(r0, "⚓", self._start_spawn_placement, fg=config.SHIP_SPAWN_COLOR).pack(side="left", expand=True, fill="x")

        # Row 2 - Starter
        r1 = tk.Frame(pad, bg=config.BG_SECTION)
        r1.pack(fill="x", pady=1)
        _row_lbl(r1, "Starter")
        _pb(r1, "L",  lambda: self._place_random("Large",      "Starter")).pack(side="left", expand=True, fill="x")
        if self.region == "Latium":
            _pb(r1, "XL", lambda: self._place_random("ExtraLarge", "Starter")).pack(side="left", expand=True, fill="x")

        # Row 3 - Normal
        r2 = tk.Frame(pad, bg=config.BG_SECTION)
        r2.pack(fill="x", pady=1)
        _row_lbl(r2, "Normal")
        _pb(r2, "S",  lambda: self._place_random("Small",      "Normal")).pack(side="left", expand=True, fill="x")
        _pb(r2, "M",  lambda: self._place_random("Medium",     "Normal")).pack(side="left", expand=True, fill="x")
        _pb(r2, "L",  lambda: self._place_random("Large",      "Normal")).pack(side="left", expand=True, fill="x")
        if self.region == "Latium":
            _pb(r2, "XL", lambda: self._place_random("ExtraLarge", "Normal")).pack(side="left", expand=True, fill="x")

        # Row 4 - NPCs (3rd Party / Pirate)
        r3 = tk.Frame(pad, bg=config.BG_SECTION)
        r3.pack(fill="x", pady=1)
        _row_lbl(r3, "NPCs")
        _pb(r3, "3rd Party", lambda: self._place_random("Small",  "ThirdParty")).pack(side="left", expand=True, fill="x")
        _pb(r3, "Pirate",    lambda: self._place_random("Medium", "Pirate"    )).pack(side="left", expand=True, fill="x")

        # Row 5 - Vulcan (Latium only)
        if self.region == "Latium":
            r4 = tk.Frame(pad, bg=config.BG_SECTION)
            r4.pack(fill="x", pady=1)
            _row_lbl(r4, "Vulcan")
            _pb(r4, "S", lambda: self._place_random("Small",  "Vulcan")).pack(side="left", expand=True, fill="x")
            _pb(r4, "M", lambda: self._place_random("Medium", "Vulcan")).pack(side="left", expand=True, fill="x")

        # Custom (fixed) island picker - equal spacing above and below
        _pb(side, "📌  Place Custom Island…", self._start_fixed_placement,
            fg=config.FG_GOLD).pack(fill="x", padx=8, pady=(12, 0))

        tk.Frame(side, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=8, pady=(6, 6))

        # ── Selection actions (info lives in the canvas overlay) ─────────────
        sel_btn_f = tk.Frame(side, bg=config.BG_SECTION)
        sel_btn_f.pack(fill="x", padx=12, pady=4)

        def _bind_hover_active(widget, bg_idle, bg_hover):
            """Hover + hand2 cursor only when the button is enabled."""
            def _enter(_e):
                if str(widget["state"]) == "normal":
                    widget.config(bg=bg_hover, cursor="hand2")
            def _leave(_e):
                widget.config(bg=bg_idle, cursor="")
            widget.bind("<Enter>", _enter)
            widget.bind("<Leave>", _leave)

        self._edit_btn = tk.Button(sel_btn_f, text="Edit", command=self._edit_selected, bg=config.BG_HOVER, fg=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=4, state="disabled", activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD)
        self._edit_btn.pack(side="left", padx=(0, 4))
        _bind_hover_active(self._edit_btn, config.BG_HOVER, "#2e4d6e")

        self._convert_btn = tk.Button(sel_btn_f, text="Convert", command=self._convert_selected, bg=config.BG_HOVER, fg=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=4, state="disabled", activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD)
        self._convert_btn.pack(side="left", padx=(0, 4))
        _bind_hover_active(self._convert_btn, config.BG_HOVER, "#2e4d6e")

        self._del_btn = tk.Button(sel_btn_f, text="✕", command=self._delete_selected, bg="#2a0a0a", fg="#e74c3c", relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=4, state="disabled", activebackground=config.BG_MAIN, activeforeground="#e74c3c")
        self._del_btn.pack(side="left")
        _bind_hover_active(self._del_btn, "#2a0a0a", "#3a1010")

        tk.Frame(side, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=8, pady=6)

        # ── Limits warning ───────────────────────────────────────────────────
        self._limits_lbl = tk.Label(side, text="", bg=config.BG_SECTION, fg="#e74c3c", font=config.FONT_XSMALL, justify="left", wraplength=210)
        self._limits_lbl.pack(anchor="w", padx=12)

        # ── Starter island counter (always visible when a map is loaded) ──────
        self._starter_lbl = tk.Label(side, text="", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left", wraplength=210)
        self._starter_lbl.pack(anchor="w", padx=12, pady=(2, 0))

        # ── Display toggles ──────────────────────────────────────────────────
        tk.Frame(side, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=8, pady=4)

        tk.Label(side, text="View", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=12, pady=(0, 2))

        self._img_toggle_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(side, text="Show island images", variable=self._img_toggle_var, command=self._on_image_toggle, bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD, font=config.FONT_SMALL, cursor="hand2")
        chk.pack(anchor="w", padx=12)
        _bind_hover(chk, config.BG_SECTION, config.BG_HOVER)

        self._reset_zoom_btn = tk.Button(side, text="Reset Zoom", command=self._reset_zoom, bg=config.BG_HOVER, fg=config.FG_DIM, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=3, state="disabled")
        self._reset_zoom_btn.pack(anchor="w", padx=12, pady=(4, 6))
        _bind_hover_active(self._reset_zoom_btn, config.BG_SECTION, config.BG_HOVER)

    # ── Side-panel callbacks ─────────────────────────────────────────────────

    def _place_random(self, size: str, island_type: str):
        """Enter placement mode for a new random island of the given size and type."""
        if self.canvas_widget is None or self.canvas_widget.template is None:
            messagebox.showinfo("No Map", "Please open or create a map first.", parent=self.app.root)
            return
        ghost = IslandElement(size=size, island_type=island_type, element_type=1)
        self.canvas_widget.start_placing(ghost)
        type_lbl = config.ISLAND_TYPE_LABELS.get(island_type, island_type)
        self.app.set_status(
            f"Placement - {size} {type_lbl}. Click to place, Esc to cancel."
        )

    def _start_fixed_placement(self):
        if self.canvas_widget is None or self.canvas_widget.template is None:
            messagebox.showinfo("No Map", "Please open or create a map first.", parent=self.app.root)
            return
        from dialogs import FixedIslandPickerDialog
        dlg = FixedIslandPickerDialog(self.winfo_toplevel(), region=self.region)
        if dlg.result and self.canvas_widget and self.canvas_widget.template:
            self.canvas_widget.start_placing(dlg.result)
            self.app.set_status(f"Place custom island: {dlg.result.display_name}  - click to place, . / middle-click to rotate, Esc to cancel.")

    def _start_spawn_placement(self):
        if self.canvas_widget is None or self.canvas_widget.template is None:
            messagebox.showinfo("No Map", "Please open or create a map first.", parent=self.app.root)
            return
        spawn = IslandElement(position=(0, 0), element_type=2, size="Small")
        self.canvas_widget.start_placement(spawn)
        self.app.set_status("Place spawn point - click to place. Esc to cancel.")

    def _cancel_placement(self):
        if self.canvas_widget:
            self.canvas_widget.cancel_placing()
        self.app.set_status("Placement cancelled.")

    def _on_island_select(self, isl: Optional[IslandElement]):
        if isl is None:
            self._edit_btn.config(state="disabled")
            self._convert_btn.config(state="disabled")
            self._del_btn.config(state="disabled")
            if self.canvas_widget:
                self.canvas_widget.set_selection_overlay([])
            return

        if isl.is_ship_spawn:
            lines = [
                "⚓  Spawn Point",
                f"Pos: ({isl.position[0]}, {isl.position[1]})",
            ]
            self._edit_btn.config(state="disabled")
            self._convert_btn.config(state="disabled")
            self._del_btn.config(state="normal")
        else:
            type_lbl = config.ISLAND_TYPE_LABELS.get(isl.island_type, isl.island_type)
            lines = [
                f"{isl.size}  ·  {type_lbl}",
                f"Pos: ({isl.position[0]}, {isl.position[1]})",
            ]
            if isl.is_fixed:
                lines.append(f"📌  {os.path.basename(isl.map_file_path or '') or '(no file)'}")
                lines.append(f"Rot: {config.ROTATION_LABELS[isl.rotation90]}")
            self._edit_btn.config(state="normal")
            self._convert_btn.config(state="disabled" if isl.is_fixed else "normal")
            self._del_btn.config(state="normal")

        if self.canvas_widget:
            self.canvas_widget.set_selection_overlay(lines)
        self._update_limits()

    def _convert_selected(self):
        if self.canvas_widget is None:
            return
        isl = self.canvas_widget.get_selected()
        if isl and not isl.is_fixed and not isl.is_ship_spawn:
            self.canvas_widget._convert_to_custom(isl)
            self.app.mark_modified()

    def _edit_selected(self):
        if self.canvas_widget is None:
            return
        isl = self.canvas_widget.get_selected()
        if isl:
            self.canvas_widget.push_undo()
            dlg = IslandPropertiesDialog(self.winfo_toplevel(), isl)
            if dlg.result:
                self.canvas_widget.invalidate_image(isl._eid)
                self.canvas_widget.redraw()
                self._on_island_select(isl)
                self.app.mark_modified()
            else:
                self.canvas_widget._undo_stack.pop()

    def set_template_name(self, name: str) -> None:
        """Update the template name shown below the region heading."""
        self._template_name_var.set(name.replace("_", " "))

    def _delete_selected(self):
        if self.canvas_widget:
            self.canvas_widget.delete_selected()
            self._on_island_select(None)
            self._update_limits()

    def _on_modify(self):
        self._update_limits()
        self.app.mark_modified()

    def _on_image_toggle(self):
        if self.canvas_widget:
            self.canvas_widget.show_images = self._img_toggle_var.get()
            self.canvas_widget.redraw()

    def _update_limits(self):
        if self.canvas_widget is None or self.canvas_widget.template is None:
            self._limits_lbl.config(text="")
            self._starter_lbl.config(text="")
            return
        tmpl = self.canvas_widget.template
        type_limits = config.ISLAND_LIMITS.get(self.region, {})
        warnings: List[str] = []

        for itype, size_limits in type_limits.items():
            if not size_limits:
                continue
            islands_of_type = [
                e for e in tmpl.elements
                if e.island_type == itype and not e.is_fixed and not e.is_ship_spawn
            ]
            if "any" in size_limits:
                count = len(islands_of_type)
                if count > size_limits["any"]:
                    warnings.append(f"⚠ {itype}: {count}/{size_limits['any']}")
            else:
                for size, max_count in size_limits.items():
                    count = sum(1 for e in islands_of_type if e.size == size)
                    if count > max_count:
                        warnings.append(f"⚠ {itype} {size}: {count}/{max_count}")

        self._limits_lbl.config(text="\n".join(warnings) if warnings else "")

        # ── Starter island counter ────────────────────────────────────────────
        _STARTER_MIN = 4
        starter_count = sum(
            1 for e in tmpl.islands if e.island_type == "Starter"
        )
        if starter_count >= _STARTER_MIN:
            self._starter_lbl.config(text=f"✓ Starter: {starter_count}/{_STARTER_MIN}", fg=config.FG_DIM)
        else:
            self._starter_lbl.config(text=f"⚠ Starter: {starter_count}/{_STARTER_MIN} required", fg="#e74c3c")

    def _on_difficulty_change(self, *_):
        """Push the UI difficulty selection into the active template."""
        tmpl = self.get_template()
        if tmpl is None:
            return
        lbl = self._diff_var.get()
        key = next((k for k, v in config.DIFFICULTY_LABELS.items() if v == lbl), "easy")
        tmpl.difficulty = key
        tmpl.difficulty_asked = True

    def set_difficulty(self, difficulty: str) -> None:
        """Update the dropdown to match a template's stored difficulty."""
        lbl = config.DIFFICULTY_LABELS.get(difficulty, config.DIFFICULTY_LABELS["easy"])
        self._diff_var.set(lbl)

    # ── Public ───────────────────────────────────────────────────────────────

    def load_template(self, tmpl: MapTemplate):
        if self.canvas_widget:
            self.canvas_widget.set_template(tmpl)
        self.set_difficulty(tmpl.difficulty)
        self._update_limits()

    def get_template(self) -> Optional[MapTemplate]:
        if self.canvas_widget:
            return self.canvas_widget.template
        return None


# ─── Main Window ─────────────────────────────────────────────────────────────

class MapEditorApp(tk.Frame):
    REGIONS = ["Latium", "Albion"]

    def __init__(self, root: tk.Tk):
        super().__init__(root, bg=config.BG_MAIN)
        self.root = root
        self.pack(fill="both", expand=True)

        self._current_file: Optional[str] = None
        self._import_name: str = ""   # display name for imported .a7tinfo templates
        self._modified = False

        # ← initialise vars here so all methods can access them regardless of build order
        self._game_path_var = tk.StringVar()
        self._fdb_path_var  = tk.StringVar(value=_fdb.find_filedb() or "")
        self._rda_path_var  = tk.StringVar(value=rda_handler.find_rda_console() or "")
        self._status_var = tk.StringVar(value="Ready.")

        # Replace the bare StringVar initializations with:
        self._game_path_var = tk.StringVar(value=_settings.get("game_path", ""))
        self._fdb_path_var  = tk.StringVar(value=_settings.get("fdb_path", _fdb.find_filedb() or ""))
        self._rda_path_var  = tk.StringVar(value=_settings.get("rda_path", rda_handler.find_rda_console() or ""))

        self.region_tabs: Dict[str, RegionTab] = {}

        _apply_ttk_style(root)
        config.load_custom_fonts()

        # Set window icon — iconphoto works on both Windows and Linux (PNG via PIL).
        _app_icon = _load_icon("data/ui/app_icon.png", 64)
        if _app_icon:
            root.iconphoto(True, _app_icon)
            self._app_icon_ref = _app_icon  # prevent GC

        self._build()
        self._update_title()


    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self):
        self._build_menubar()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()
        # Validate / auto-detect game path after the window is rendered
        self.after(600, self._startup_path_check)

    def _build_menubar(self):
        mb = tk.Menu(self.root, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD, relief=tk.FLAT, borderwidth=0)
        self.root.config(menu=mb)

        # File menu
        file_menu = tk.Menu(mb, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD)
        mb.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New…",                    accelerator="Ctrl+N",       command=self.cmd_new)
        file_menu.add_command(label="Import from Game…",       accelerator="Ctrl+O",       command=self.cmd_import_game)
        file_menu.add_command(label="Import .a7tinfo…",        accelerator="Alt+Ctrl+O",   command=self.cmd_import_a7tinfo)
        file_menu.add_separator()
        file_menu.add_command(label="Open XML…",               accelerator="Shift+Ctrl+O", command=self.cmd_open)
        file_menu.add_command(label="Save XML",                accelerator="Shift+Ctrl+S", command=self.cmd_save)
        file_menu.add_command(label="Save XML As…",                                        command=self.cmd_save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export .a7tinfo…",        accelerator="Alt+Ctrl+E", command=self.cmd_export_a7tinfo)
        #file_menu.add_command(label="Export All Difficulties…",                            command=self.cmd_export_all_difficulties)
        file_menu.add_command(label="Export PNG…",             accelerator="PrtScn",       command=self.cmd_export_png)
        file_menu.add_separator()
        file_menu.add_command(label="Export as Mod (.zip)…",   accelerator="Ctrl+S",       command=self.cmd_export_mod)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",                                                command=self._on_close)

        # Edit menu
        edit_menu = tk.Menu(mb, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD)
        mb.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo",          command=self.cmd_undo,        accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo",          command=self.cmd_redo,        accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All",    command=self._select_all,     accelerator="Ctrl+A")
        edit_menu.add_command(label="Deselect All",  command=self._deselect_all,   accelerator="Escape")
        edit_menu.add_command(label="Delete Selected", command=self._delete_selected)
        edit_menu.add_separator()
        edit_menu.add_command(label="Set Game Path…",         command=self._browse_game_path)
        edit_menu.add_command(label="Set FileDBReader Path…", command=self._browse_fdb)
        edit_menu.add_command(label="Set RdaConsole Path…",   command=self._browse_rda)

        # View menu
        view_menu = tk.Menu(mb, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD)
        mb.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Zoom In",      accelerator="Ctrl++", command=lambda: self._zoom(1))
        view_menu.add_command(label="Zoom Out",     accelerator="Ctrl+-", command=lambda: self._zoom(-1))
        view_menu.add_command(label="Fit to Window",                      command=self._fit_view)

        # Help
        help_menu = tk.Menu(mb, tearoff=0, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD)
        mb.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation on GitHub", command=lambda: webbrowser.open("https://github.com/taludas/anno-117-map-editor"))
        help_menu.add_separator()
        help_menu.add_command(label="About…", command=lambda: AboutDialog(self.root))

        # Keyboard shortcuts
        # Primary workflow
        self.root.bind("<Control-n>",   lambda e: self.cmd_new())
        self.root.bind("<Control-o>",   lambda e: self.cmd_import_game())   # Ctrl+O  → Import from game
        self.root.bind("<Control-s>",   lambda e: self.cmd_export_mod())    # Ctrl+S  → Export Mod
        self.root.bind("<Control-Alt-o>", lambda e: self.cmd_import_a7tinfo())  # Alt+Ctrl+O → Import a7tinfo
        self.root.bind("<Control-Alt-O>", lambda e: self.cmd_import_a7tinfo())  # (shift-insensitive variant)
        # XML file operations (Shift variants)
        self.root.bind("<Control-O>",   lambda e: self.cmd_open())          # Shift+Ctrl+O → Open XML
        self.root.bind("<Control-S>",   lambda e: self.cmd_save())          # Shift+Ctrl+S → Save XML
        self.root.bind("<Control-Alt-e>",   lambda e: self.cmd_export_a7tinfo()) # Alt+Ctrl+E → Export a7tinfo
        self.root.bind("<Control-Alt-E>",   lambda e: self.cmd_export_a7tinfo()) # (shift-insensitive variant)
        self.root.bind("<Print>",       lambda e: self.cmd_export_png())    # PrtScn → Export PNG
        # View / edit shortcuts
        self.root.bind("<Control-equal>", lambda e: self._zoom(1))
        self.root.bind("<Control-minus>",  lambda e: self._zoom(-1))
        self.root.bind("<Control-a>",      lambda e: self._select_all())
        self.root.bind("<Control-z>",      lambda e: self.cmd_undo())
        self.root.bind("<Control-y>",      lambda e: self.cmd_redo())

    def _build_header(self):
        hdr = tk.Frame(self, bg=config.BG_SECTION, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Title (left)
        tk.Label(hdr, text="Anno 117 - Map Template Editor", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_TITLE).pack(side="left", padx=18, pady=8)

        # Icon refs - initialised here so all sections can write into it safely
        self._hdr_icons: dict = {}

        # Helper: vertical separator bar
        def _vsep():
            tk.Frame(hdr, bg=config.FG_MAIN, width=1).pack(side="right", fill="y", padx=6, pady=8)

        # ── Section 2: PNG export (right side, plain style) ──────────────────
        ico_png = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_camera.png", 24)
        self._hdr_icons["png"] = ico_png

        def _s2btn(label, cmd, ico=None):
            kw = {"image": ico, "compound": tk.LEFT} if ico else {}
            btn = tk.Button(hdr, text=label, command=cmd, bg=config.BG_HOVER, fg=config.FG_MAIN, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=4, cursor="hand2", **kw)
            btn.pack(side="right", padx=2, pady=8)
            _bind_hover(btn, config.BG_HOVER, "#2e4d6e")

        _s2btn(" Export PNG", self.cmd_export_png, ico_png)

        _vsep()

        # ── Section 1: Primary workflow (coloured, with icons) ────────────────
        # Icons kept alive in self._hdr_icons to prevent GC.
        # Pack right-to-left → visual L→R: New Map | Import | Export as Mod
        ico_mod = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_save.png", 24)
        ico_imp = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_advance_options.png", 24)
        ico_new = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_province_map.png", 24)
        self._hdr_icons.update({"mod": ico_mod, "imp": ico_imp, "new": ico_new})

        def _cbutton(text, cmd, ico, bg_idle, bg_hover):
            kw = {"image": ico, "compound": tk.LEFT} if ico else {}
            btn = tk.Button(hdr, text=text, command=cmd, bg=bg_idle, fg="white", activebackground=bg_hover, activeforeground="white", relief=tk.FLAT, font=config.FONT_SMALL, padx=10, pady=4, cursor="hand2", **kw)
            btn.pack(side="right", padx=2, pady=8)
            _bind_hover(btn, bg_idle, bg_hover)

        _cbutton(" Export as Mod", self.cmd_export_mod, ico_mod, "#c8860a", "#e09a10")
        _cbutton(" Import from Game", self.cmd_import_game, ico_imp, "#b85c00", "#d06a00")
        _cbutton(" New Map", self.cmd_new, ico_new, "#2e7d32", "#388e3c")

    def _build_notebook(self):
        nb_frame = tk.Frame(self, bg=config.BG_MAIN)
        nb_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(nb_frame, style="TNotebook")
        self.notebook.pack(fill="both", expand=True)

        def _nb_motion(event):
            region = self.notebook.identify(event.x, event.y)
            self.notebook.config(cursor="hand2" if region in ("tab", "label") else "")
        self.notebook.bind("<Motion>", _nb_motion)
        self.notebook.bind("<Leave>", lambda _e: self.notebook.config(cursor=""))

        # Tab icons - refs kept alive in self._tab_icons to prevent GC
        ico_lat = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_region_heartlands.png", 24)
        ico_alb = _load_icon("data/ui/fhd/base/icon_content/generic/icon_2d_region_wetlands.png", 24)
        self._tab_icons = {"Latium": ico_lat, "Albion": ico_alb}

        _tab_ico = {"Latium": ico_lat, "Albion": ico_alb}
        for region in self.REGIONS:
            tab = RegionTab(self.notebook, region, app=self)
            ico = _tab_ico.get(region)
            if ico:
                self.notebook.add(tab, text=f" {region} ", image=ico, compound="left")
            else:
                self.notebook.add(tab, text=f"  {region}  ")
            self.region_tabs[region] = tab

        self.root.bind("<MouseWheel>", self._on_root_scroll)

        # ── Community buttons - overlaid in the notebook tab strip, right-aligned ──
        # Placed directly on the notebook widget so they sit in the tab bar row.
        comm = tk.Frame(self.notebook, bg=config.BG_MAIN, bd=0, highlightthickness=0)
        comm.place(relx=1.0, y=2, anchor="ne")

        ico_kofi = _load_icon("data/ui/kofi/kofi_symbol.png", 16)
        ico_github  = _load_icon("data/ui/github/github_symbol.png", 16)
        ico_discord = _load_icon("data/ui/discord/discord_symbol.png", 16)
        self._nb_icons = {"kofi": ico_kofi, "github": ico_github, "discord": ico_discord}

        def open_kofi(): webbrowser.open("https://ko-fi.com/W7W8L558T")
        def open_discord(): webbrowser.open("https://discord.gg/m4e7ZanMVp")
        def open_docs(): webbrowser.open("https://github.com/taludas/anno-117-map-editor")

        def _cbtn(text, cmd, ico, bg_idle, bg_hover):
            kw = {"image": ico, "compound": tk.LEFT} if ico else {}
            btn = tk.Button(comm, text=text, command=cmd, bg=bg_idle, fg="white", activebackground=bg_hover, activeforeground="white", relief=tk.FLAT, font=config.FONT_SMALL, padx=8, pady=3, cursor="hand2", **kw)
            btn.pack(side="right", padx=2, pady=2)
            btn.bind("<Enter>", lambda _e, b=btn, c=bg_hover: b.config(bg=c))
            btn.bind("<Leave>", lambda _e, b=btn, c=bg_idle:  b.config(bg=c))

        # Pack right-to-left → visual L→R: Discord | GitHub | Ko-fi
        _cbtn(" Ko-fi Support", open_kofi, ico_kofi, "#5F032E", "#82043f")
        _cbtn(" Documentation", open_docs, ico_github, "#4c565f", "#627080")
        _cbtn(" Modding Discord", open_discord, ico_discord, "#5865F2", "#7289da")

    def _build_statusbar(self):
        sb = tk.Label(self, textvariable=self._status_var, bg=config.BG_MAIN, fg=config.FG_DIM, font=config.FONT_XSMALL, anchor="w")
        sb.pack(fill="x", side="bottom", padx=8, pady=2)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _on_root_scroll(self, event: tk.Event) -> None:
    # Forward to whichever canvas tab is currently visible
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            tab.canvas_widget._on_scroll_all(event)

    def refresh_all_canvases(self):
        """Clear image caches and redraw all canvases. Called after island registry finishes loading."""
        for tab in self.region_tabs.values():
            if tab.canvas_widget:
                tab.canvas_widget.clear_image_cache()
                tab.canvas_widget.redraw()

    def set_status(self, msg: str):
        self._status_var.set(msg)
        self.update_idletasks()

    def mark_modified(self):
        self._modified = True
        self._update_title()

    def _update_title(self):
        base = f"Taludas Anno 117 Map Editor (TAMPER) v{_version.__VERSION__}"
        mod = " *" if self._modified else ""
        if self._current_file:
            self.root.title(f"{base} - {os.path.basename(self._current_file)}{mod}")
        else:
            self.root.title(f"{base}{mod}")

    def _set_all_tabs_template_name(self, name: str) -> None:
        for tab in self.region_tabs.values():
            tab.set_template_name(name)

    def _current_tab(self) -> Optional[RegionTab]:
        name = self.notebook.tab(self.notebook.select(), "text").strip()
        return self.region_tabs.get(name)

    def _zoom(self, direction: int):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            tab.canvas_widget.zoom(direction)

    def _fit_view(self):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            tab.canvas_widget.fit_view()

    def _delete_selected(self):
        tab = self._current_tab()
        if tab:
            tab._delete_selected()

    def _select_all(self):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            tab.canvas_widget.select_all()

    def _deselect_all(self):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            tab.canvas_widget.deselect_all()

    def _browse_game_path(self):
        path = filedialog.askdirectory(title="Select Anno 117 Installation Folder", parent=self.root)
        if path:
            self._game_path_var.set(path)
            self._save_settings()

    def _get_drive_letters(self) -> list:
        """Return a list of available drive root paths (Windows) or ['/'] (Unix)."""
        if not config.IS_WINDOWS:
            return ["/"]
        import string
        import ctypes
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(letter + ":")
            bitmask >>= 1
        return drives

    def _find_game_path(self) -> Optional[str]:
        """
        Search for the Anno 117 installation and return the game root folder, or None.
        Checks known fixed paths first, then globs across all drives.
        """
        possible_roots: List[str] = list(config.ANNO_INSTALL_CANDIDATES)

        if config.IS_WINDOWS:
            pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            pf   = os.environ.get("ProgramFiles", r"C:\Program Files")
            for base in (pf86, pf):
                possible_roots.append(os.path.join(base, "Ubisoft", "Ubisoft Game Launcher", "games", "Anno 117 - Pax Romana", "Anno 117"))
                possible_roots.append(os.path.join(base, "Steam", "steamapps", "common", "Anno 117 - Pax Romana", "Anno 117"))

        # Glob across every drive for the exe at up to 6 folder levels deep
        exe_patterns = [
            os.path.join("Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
            os.path.join("*", "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
            os.path.join("*", "*", "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
            os.path.join("*", "*", "*", "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
            os.path.join("*", "*", "*", "*", "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
            os.path.join("*", "*", "*", "*", "*", "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
        ]

        for drive in self._get_drive_letters():
            for pattern in exe_patterns:
                full_pattern = os.path.join(drive + os.sep, pattern)
                try:
                    for match in glob.glob(full_pattern):
                        if os.path.isfile(match):
                            # game root is 3 levels above the exe (…/Anno 117 - Pax Romana/Bin/Win64/exe)
                            return os.path.abspath(
                                os.path.dirname(os.path.dirname(os.path.dirname(match)))
                            )
                except Exception:
                    continue

        # Fallback: check the known-root candidates directly
        for root in list(dict.fromkeys(possible_roots)):
            if not root or not os.path.exists(root):
                continue
            for target in (
                os.path.join(root, "Bin", "Win64", "Anno117.exe"),
                os.path.join(root, "Anno 117 - Pax Romana", "Bin", "Win64", "Anno117.exe"),
                os.path.join(root, "Anno117.exe"),
            ):
                if os.path.exists(target):
                    return os.path.abspath(root)

        return None

    def _auto_detect_game(self, silent=False):
        if not silent:
            self.set_status("Searching for Anno 117 installation…")

        def _search():
            result = self._find_game_path()
            def _apply():
                if result:
                    self._game_path_var.set(result)
                    self._save_settings()
                    if not silent:
                        self.set_status(f"Game path detected: {result}")
                elif not silent:
                    self.set_status("Ready.")
                    messagebox.showinfo(
                        "Auto-detect",
                        "Could not auto-detect Anno 117 installation.\n"
                        "Use  Edit › Set Game Path…  to configure it manually.",
                        parent=self.root,
                    )
            self.root.after(0, _apply)

        threading.Thread(target=_search, daemon=True).start()

    def _startup_path_check(self):
        """Called once after startup: validate stored game path or trigger auto-detect."""
        stored = self._game_path_var.get().strip()
        if stored and os.path.isdir(stored):
            return  # valid path already saved
        self._auto_detect_game(silent=False)

    def _browse_rda(self):
        path = filedialog.askopenfilename(
            title="Select RdaConsole executable",
            filetypes=[("Executable", "*.exe" if config.IS_WINDOWS else "*"), ("All", "*")],
            parent=self.root,
        )
        if path:
            self._rda_path_var.set(path)
            self._save_settings()

    def _browse_fdb(self):
        path = filedialog.askopenfilename(
            title="Select FileDBReader executable",
            filetypes=[("Executable", "*.exe" if config.IS_WINDOWS else "*"), ("All", "*")],
            parent=self.root,
        )
        if path:
            self._fdb_path_var.set(path)
            self._save_settings()

    def _get_filedb(self):
        path = self._fdb_path_var.get().strip()
        if path:
            _fdb.FILEDB_PATH = path  # override if user set one
        if not _fdb.find_filedb():
            messagebox.showerror("FileDBReader Not Found",
                "FileDBReader not found.\nUse Edit › Set FileDBReader Path…  to configure it manually.\n\n"
                "Download: https://github.com/anno-mods/FileDBReader/releases",
                parent=self.root)
            return False
        return True

    def _save_settings(self):
        _settings.save({
            "game_path": self._game_path_var.get().strip(),
            "fdb_path":  self._fdb_path_var.get().strip(),
            "rda_path":  self._rda_path_var.get().strip(),
        })

    def _on_close(self):
        self._save_settings()
        if self._confirm_discard():
            self.root.destroy()

    def _confirm_discard(self) -> bool:
        if not self._modified:
            return True
        return messagebox.askyesno(
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            parent=self.root
        )

    # ── Edit commands ─────────────────────────────────────────────────────────

    def cmd_undo(self):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            if not tab.canvas_widget.undo():
                self.set_status("Nothing to undo.")

    def cmd_redo(self):
        tab = self._current_tab()
        if tab and tab.canvas_widget:
            if not tab.canvas_widget.redo():
                self.set_status("Nothing to redo.")

    # ── File commands ─────────────────────────────────────────────────────────

    def cmd_new(self):
        if not self._confirm_discard():
            return
        # Clear all visible canvases while the dialog is open so there's no stale map content visible behind it.
        for tab in self.region_tabs.values():
            if tab.canvas_widget:
                tab.canvas_widget.delete("all")
        from dialogs import NewMapDialog
        dlg = NewMapDialog(self.root)
        if dlg.result is None:
            # Restore the canvas content if the user cancelled.
            for tab in self.region_tabs.values():
                if tab.canvas_widget:
                    tab.canvas_widget.redraw()
            return
        region = dlg.result["region"]
        from models import MapTemplate
        tmpl = MapTemplate(
            region=dlg.result["region"],
            size=dlg.result["size"],
            playable_area=dlg.result["playable_area"],
            initial_playable_area=dlg.result["initial_playable_area"],
            enlargement_offset=dlg.result["enlargement_offset"],
            is_enlarged=dlg.result["is_enlarged"],
            difficulty=dlg.result.get("difficulty", "easy"),
            difficulty_asked=True,
        )
        self.region_tabs[region].load_template(tmpl)

        # Also create a default blank template for the other region so both canvases are editable without needing to save/reload between tabs.
        other = "Albion" if region == "Latium" else "Latium"
        other_pa = dlg.result.get("companion_playable_area", (20, 20, 2020, 2020))
        other_tmpl = MapTemplate(
            region=other,
            size=(2048, 2048),
            playable_area=other_pa,
            initial_playable_area=other_pa,
            enlargement_offset=(0, 0),
            is_enlarged=False,
        )
        self.region_tabs[other].load_template(other_tmpl)

        self._current_file = None
        self._import_name = ""
        self._modified = False
        self._update_title()
        self._set_all_tabs_template_name("")
        # Switch to the selected region's tab
        idx = list(self.region_tabs.keys()).index(region)
        self.notebook.select(idx)
        self.set_status(f"New {region} map created ({tmpl.size[0]}×{tmpl.size[1]}). Both regions initialized.")

    def cmd_open(self):
        path = filedialog.askopenfilename(
            title="Open Map Template XML",
            filetypes=[("XML files", "*.xml"), ("All", "*")],
            parent=self.root,
        )
        if not path:
            return
        tab = self._current_tab()
        region = tab.region if tab else "Latium"
        self._load_xml_file(path, region=region)

    def _load_xml_file(self, path: str, region: str = "Latium"):
        try:
            self.set_status(f"Loading {os.path.basename(path)}…")
            tmpl = load_xml(path, region=region)
            self.region_tabs[region].load_template(tmpl)
            self._current_file = path
            self._import_name = ""
            self._modified = False
            self._update_title()
            self.region_tabs[region].set_template_name(os.path.basename(path))
            self.set_status(f"Loaded: {os.path.basename(path)}  ({tmpl.size[0]}×{tmpl.size[1]}, "
                            f"{len(tmpl.elements)} elements)")
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc), parent=self.root)
            self.set_status("Load failed.")

    def cmd_import_game(self):
        from import_dialog import ImportDialog
        game_path = self._game_path_var.get().strip()
        rda_exe   = self._rda_path_var.get().strip() or None

        ImportDialog(
            self.root,
            game_path=game_path,
            extracted_root=config.EXTRACTED_DIR,
            rda_exe=rda_exe,
            on_import=self._on_template_selected,
            on_extracted=self._on_rda_extracted,
        )

    def _on_rda_extracted(self):
        """Reload all registries after a fresh RDA extraction and refresh canvases.
        Called on the main thread immediately after extraction completes."""
        from island_registry import IslandRegistry
        from fertility_registry import FertilityRegistry
        from fertility_set_registry import FertilitySetRegistry

        def _reload():
            IslandRegistry.instance().load(force=True)
            FertilityRegistry.instance().load(force=True)
            FertilitySetRegistry.instance().load(force=True)
            self.root.after(0, self.refresh_all_canvases)

        threading.Thread(target=_reload, daemon=True).start()

    def cmd_import_a7tinfo(self):
        """Import a .a7tinfo file from any location - decompresses via FileDBReader then loads."""
        if not self._get_filedb():
            return
        path = filedialog.askopenfilename(
            title="Import .a7tinfo Map Template",
            filetypes=[("a7tinfo files", "*.a7tinfo"), ("All files", "*")],
            parent=self.root,
        )
        if not path:
            return
        tab = self._current_tab()
        region = tab.region if tab else "Latium"
        ok = self._import_a7tinfo(path, region)
        if ok:
            self._current_file = None
            self._import_name = os.path.basename(path).replace(".a7tinfo", "")
            self._modified = True
            self._update_title()
            self.set_status(f"Imported: {self._import_name}  - ready.")

    def _on_template_selected(self, path: str, want_enlarged: bool):
        """Called by ImportDialog when user confirms a selection."""
        import re
        src_norm = path.replace("\\", "/").lower()
        region = "Albion" if "celtic" in src_norm else "Latium"
        other  = "Albion" if region == "Latium" else "Latium"

        counterpart = self._find_counterpart_path(path, region, want_enlarged)
        tasks = [(path, region)] + ([(counterpart, other)] if counterpart else [])

        self.set_status("Decompressing map templates…")
        self.root.config(cursor="wait")
        self.root.update_idletasks()

        def _load_one(src: str, rgn: str):
            xml_path = self._cached_decompress(src)
            tmpl = load_xml(xml_path, region=rgn)
            dm = re.search(r"_(easy|medium|hard)(?:[_.]|$)",
                           os.path.basename(src), re.IGNORECASE)
            if dm:
                tmpl.difficulty = dm.group(1).lower()
                tmpl.difficulty_asked = True
            return (rgn, tmpl)

        def _worker():
            results, errors = [], []
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(_load_one, src, rgn): rgn
                           for src, rgn in tasks}
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        results.append(fut.result())
                    except Exception as exc:
                        errors.append((futures[fut], str(exc)))
            self.root.after(0, lambda: _apply(results, errors))

        def _apply(results, errors):
            self.root.config(cursor="")
            for rgn, err in errors:
                messagebox.showerror(f"Import Error ({rgn})", err, parent=self.root)
            for rgn, tmpl in results:
                self.region_tabs[rgn].load_template(tmpl)
                src_for_name = path if rgn == region else (counterpart or path)
                self.region_tabs[rgn].set_template_name(
                    os.path.basename(src_for_name).replace(".a7tinfo", "")
                )
            # Switch back to the tab the user actually selected
            idx = list(self.region_tabs.keys()).index(region)
            self.notebook.select(idx)
            self._current_file = None
            self._import_name = os.path.basename(path).replace(".a7tinfo", "")
            self._modified = True
            self._update_title()
            self.set_status(f"Imported: {self._import_name}  - ready.")

        threading.Thread(target=_worker, daemon=True).start()

    def _cached_decompress(self, src: str) -> str:
        """
        Return the XML path for a cached .a7tinfo in EXTRACTED_DIR.
        Reuses a sidecar .xml when it exists and is not older than the source,
        otherwise decompresses via FileDBReader and saves the result as the sidecar.
        Safe to call from a background thread.
        """
        cache_xml = src.replace(".a7tinfo", ".xml")
        if (os.path.isfile(cache_xml) and
                os.path.getmtime(cache_xml) >= os.path.getmtime(src)):
            print(f"[import] XML cache hit: {os.path.basename(cache_xml)}")
            return cache_xml
        print(f"[import] Decompressing: {os.path.basename(src)}")
        return _fdb.decompress(
            src,
            interpreter_path=config.INTERPRETER_PATH,
            output_path=cache_xml,
        )

    def _import_a7tinfo(self, src: str, region: str) -> bool:
        """Decompress and load one .a7tinfo into the given region tab. Returns success."""
        try:
            self.set_status(f"Decompressing {os.path.basename(src)}…")
            xml_path = _fdb.decompress(src, interpreter_path=config.INTERPRETER_PATH)
            tmpl = load_xml(xml_path, region=region)
            # Detect difficulty from the filename (e.g. "…_easy.a7tinfo")
            import re as _re
            _dm = _re.search(r"_(easy|medium|hard)(?:[_.]|$)", os.path.basename(src), _re.IGNORECASE)
            if _dm:
                tmpl.difficulty = _dm.group(1).lower()
                tmpl.difficulty_asked = True
            self.region_tabs[region].load_template(tmpl)
            # Set the region-specific template name on this tab only
            self.region_tabs[region].set_template_name(
                os.path.basename(src).replace(".a7tinfo", "")
            )
            # Switch to the tab that was just loaded
            idx = list(self.region_tabs.keys()).index(region)
            self.notebook.select(idx)
            return True
        except Exception as exc:
            messagebox.showerror(f"Import Error ({region})", str(exc), parent=self.root)
            return False

    def _find_counterpart_path(self, src: str, src_region: str, want_enlarged: bool = False) -> Optional[str]:
        import re
        # Look in extracted cache, not game directory
        search_root = config.EXTRACTED_DIR

        basename = os.path.basename(src).replace(".a7tinfo", "")

        # ── Campaign template ────────────────────────────────────────────────
        camp_m = re.match(r"(roman|celtic)_province_campaign_(\d+)(_dlc01expanded)?$", basename)
        if camp_m:
            other    = "celtic" if src_region == "Latium" else "roman"
            num      = camp_m.group(2)
            # For enlarged campaign templates (dlc01expanded), the Albion counterpart is the standard (non-enlarged) campaign template - it doesn't have an expanded variant
            cname = f"{other}_province_campaign_{num}"
            path  = os.path.join(search_root, "data", "base", "provinces", other, "templates", "campaign", cname, f"{cname}.a7tinfo")
            print(f"[counterpart] Campaign counterpart: {path}")
            return path if os.path.isfile(path) else None

        # ── Standard pool template ───────────────────────────────────────────
        m = re.match(
            r"(roman|celtic)_province_(chain|corners|default|donut|rift)"
            r"_(\d+)_(easy|medium|hard)(_dlc01expanded)?",
            basename
        )
        if not m:
            print(f"[counterpart] No regex match for basename: {basename!r}")
            return None

        _culture, ptype, _num, diff, expanded = m.groups()
        print(f"[counterpart] Parsed - culture={_culture} type={ptype} diff={diff} expanded={expanded}")

        if src_region == "Latium":
            cname = f"celtic_province_{ptype}_01_{diff}"
            path = os.path.join(search_root, "data", "base", "provinces", "celtic", "templates", "pool", cname, f"{cname}.a7tinfo")
            print(f"[counterpart] Looking for Albion at: {path}")
            return path if os.path.isfile(path) else None

        else:
            if want_enlarged:
                cname = f"roman_province_{ptype}_01_{diff}_dlc01expanded"
                path = os.path.join(search_root, "data", "dlc01", "provinces", "roman", "templates", "pool", cname, f"{cname}.a7tinfo")
            else:
                cname = f"roman_province_{ptype}_01_{diff}"
                path = os.path.join(search_root, "data", "base", "provinces", "roman", "templates", "pool", cname, f"{cname}.a7tinfo")
            print(f"[counterpart] Looking for Latium at: {path}")
            return path if os.path.isfile(path) else None

    def cmd_save(self):
        if self._current_file is None:
            self.cmd_save_as()
            return
        self._save_to(self._current_file)

    def cmd_save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Map Template XML",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All", "*")],
            parent=self.root,
        )
        if path:
            self._save_to(path)

    def _save_to(self, path: str):
        # Save only the active tab's template - XML export targets one region at a time.
        tab = self._current_tab()
        tmpl = tab.get_template() if tab else None
        if tmpl is None:
            messagebox.showinfo("Nothing to Save", "No map loaded.", parent=self.root)
            return
        if not self._warn_before_export([tmpl]):
            return
        try:
            self._resolve_and_save_xml(tmpl, path)
            self._current_file = path
            self._modified = False
            self._update_title()
            self.set_status(f"Saved: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self.root)

    # ── Fertility resolution helper ───────────────────────────────────────────

    def _has_pseudo_random_fertilities(self, tmpls) -> bool:
        """True if any template has a fixed island with unresolved randomized fertilities.
        Continental islands are excluded - they use the game's FertilitySet mechanism."""
        for tmpl in tmpls:
            for isl in tmpl.islands:
                if (isl.is_fixed and isl.randomize_fertilities
                        and not isl.fertility_guids
                        and isl.size != "Continental"):
                    return True
        return False

    def _warn_pseudo_random(self, tmpls) -> bool:
        """
        If any fixed island uses randomized fertility, show a one-time warning
        explaining the pseudo-randomization workaround.
        Returns True to proceed, False if the user cancels.
        """
        if not self._has_pseudo_random_fertilities(tmpls):
            return True
        return messagebox.askyesno(
            "Pseudo-randomized Fertilities",
            "One or more fixed islands are set to 'Random Fertilities'.\n\n"
            "Because the game engine does not support truly random fertilities on "
            "fixed islands, the editor will now assign a specific set of fertilities "
            "by simulating the game's selection logic.\n\n"
            "Important: these fertilites are fixed at save time and will be identical "
            "for every map seed the game generates - they do not change between playthroughs.\n\n"
            "Proceed?",
            parent=self.root,
        )

    def _needs_difficulty_prompt(self, tmpls) -> bool:
        """True if any template has a fixed island with randomize_fertilities=True
        and has not yet had its difficulty explicitly confirmed by the user.
        Continental islands are excluded - they use the game's FertilitySet mechanism."""
        for tmpl in tmpls:
            if tmpl.difficulty_asked:
                continue
            for isl in tmpl.islands:
                if (isl.is_fixed and isl.randomize_fertilities
                        and not isl.fertility_guids
                        and isl.size != "Continental"):
                    return True
        return False

    def _prompt_difficulty(self, tmpl) -> bool:
        """Ask the user for a difficulty if not yet set. Returns False if cancelled."""
        from dialogs import _combo, _btn, _sep   # local helpers
        import tkinter as tk

        win = tk.Toplevel(self.root)
        win.title("Map Difficulty")
        win.configure(bg=config.BG_SECTION)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Map Difficulty", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 4))
        _sep(win).pack(fill="x", padx=10, pady=4)

        tk.Label(
            win,
            text=(
                "This template contains fixed islands with randomized fertilities.\n"
                "Choose the difficulty this template is designed for.\n"
                "Use 'Export All Difficulties' to generate all three variants."
            ),
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, justify="left", wraplength=360
        ).pack(anchor="w", padx=16, pady=(0, 8))

        diff_labels = list(config.DIFFICULTY_LABELS.values())
        current_lbl = config.DIFFICULTY_LABELS.get(tmpl.difficulty, diff_labels[1])
        diff_var = tk.StringVar(value=current_lbl)
        row = tk.Frame(win, bg=config.BG_SECTION)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Difficulty:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, width=12, anchor="w").pack(side="left")
        _combo(row, diff_labels, diff_var, width=12).pack(side="left")

        _sep(win).pack(fill="x", padx=10, pady=8)
        confirmed = [False]

        def _ok():
            lbl = diff_var.get()
            key = next((k for k, v in config.DIFFICULTY_LABELS.items() if v == lbl), "easy")
            tmpl.difficulty = key
            tmpl.difficulty_asked = True
            # Sync the tab dropdown
            tab = self.region_tabs.get(tmpl.region)
            if tab:
                tab.set_difficulty(key)
            confirmed[0] = True
            win.destroy()

        btn_f = tk.Frame(win, bg=config.BG_SECTION)
        btn_f.pack(pady=(0, 12))
        _btn(btn_f, "  Confirm  ", _ok, fg=config.BG_MAIN, bg=config.FG_GOLD).pack(side="left", padx=8)
        _btn(btn_f, "  Cancel  ", win.destroy).pack(side="left", padx=8)

        win.update_idletasks()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry(f"{w}x{h}+{rx + (pw - w)//2}+{ry + (ph - h)//2}")
        win.wait_window()
        return confirmed[0]

    def _resolve_and_save_xml(self, tmpl, xml_path: str) -> None:
        """Deep-copy *tmpl* and write it to *xml_path*. Original template is untouched."""
        from copy import deepcopy
        copy = deepcopy(tmpl)
        save_xml(copy, xml_path)

    def _compress_xml(self, xml_path: str, out_path: str) -> bool:
        """Compress xml_path → out_path. Returns True on success."""
        try:
            _fdb.compress(xml_path, out_path, interpreter_path=config.INTERPRETER_PATH)
            return True
        except _fdb.FileDBError as exc:
            messagebox.showerror("Compression Failed", str(exc), parent=self.root)
            return False

    # ── Export commands ───────────────────────────────────────────────────────

    def cmd_export_a7tinfo(self):
        """Save the active tab's map as a compressed .a7tinfo file."""
        if not self._get_filedb():
            return

        tab = self._current_tab()
        tmpl = tab.get_template() if tab else None
        if not tmpl:
            messagebox.showinfo("Nothing to Export", "No map loaded.", parent=self.root)
            return
        if not self._warn_before_export([tmpl]):
            return

        xml_path = filedialog.asksaveasfilename(
            title="Export as .a7tinfo (choose output path)",
            defaultextension=".a7tinfo",
            filetypes=[("a7tinfo", "*.a7tinfo"), ("All", "*")],
            parent=self.root,
        )
        if not xml_path:
            return

        import tempfile
        tmp_xml = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
                tmp_xml = tmp.name
            self._resolve_and_save_xml(tmpl, tmp_xml)
            self.set_status(f"Compressing {tmpl.region}…")
            if self._compress_xml(tmp_xml, xml_path):
                self.set_status(f"Exported: {os.path.basename(xml_path)}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc), parent=self.root)
        finally:
            if tmp_xml:
                try:
                    os.unlink(tmp_xml)
                except Exception:
                    pass

    def cmd_export_all_difficulties(self):
        """Export all three difficulty variants for every loaded region."""
        if not self._get_filedb():
            return

        tmpls = [t for t in (tab.get_template() for tab in self.region_tabs.values()) if t]
        if not tmpls:
            messagebox.showinfo("Nothing to Export", "No map loaded.", parent=self.root)
            return
        if not self._require_deployment_ready(tmpls):
            return
        if not self._warn_before_export(tmpls):
            return

        xml_path = filedialog.asksaveasfilename(
            title="Export All Difficulties - choose base output path",
            defaultextension=".a7tinfo",
            filetypes=[("a7tinfo", "*.a7tinfo"), ("All", "*")],
            parent=self.root,
        )
        if not xml_path:
            return

        from fertility_set_registry import FertilitySetRegistry
        FertilitySetRegistry.instance().load()

        import tempfile
        from copy import deepcopy

        base, ext = os.path.splitext(xml_path)
        exported: List[str] = []

        for tmpl in tmpls:
            for diff_key in config.DIFFICULTY_KEYS:
                diff_copy = deepcopy(tmpl)
                diff_copy.difficulty = diff_key
                diff_copy.difficulty_asked = True

                out = f"{base}_{tmpl.region}_{diff_key}{ext}"
                self.set_status(
                    f"Exporting {tmpl.region} / {config.DIFFICULTY_LABELS[diff_key]}…"
                )
                try:
                    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
                        tmp_xml = tmp.name
                    self._resolve_and_save_xml(diff_copy, tmp_xml)
                    if self._compress_xml(tmp_xml, out):
                        exported.append(os.path.basename(out))
                except Exception as exc:
                    messagebox.showerror("Export Error", str(exc), parent=self.root)
                finally:
                    try:
                        os.unlink(tmp_xml)
                    except Exception:
                        pass

        if exported:
            self.set_status(f"Exported {len(exported)} files: {', '.join(exported)}")

    def cmd_export_png(self):
        """Export the active tab's map as a PNG cropped to the playable area."""
        tab = self._current_tab()
        canvas = tab.canvas_widget if tab else None
        if canvas is None or canvas.template is None:
            messagebox.showinfo("Nothing to Export", "No map loaded.", parent=self.root)
            return

        filepath = filedialog.asksaveasfilename(
            title="Export map as PNG",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*")],
            parent=self.root,
        )
        if not filepath:
            return

        self.set_status("Exporting PNG…")
        try:
            canvas.export_png(filepath)
            self.set_status(f"PNG exported: {os.path.basename(filepath)}")
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self.root)
            self.set_status("PNG export failed.")

    def cmd_export_mod(self):
        """Package the current map templates into a playable mod zip file."""
        if not self._get_filedb():
            return

        tmpls = [t for t in (tab.get_template() for tab in self.region_tabs.values()) if t]
        if not tmpls:
            messagebox.showinfo("Nothing to Export", "No map loaded.", parent=self.root)
            return

        if not self._require_deployment_ready(tmpls):
            return
        if not self._warn_before_export(tmpls):
            return

        # DLC01 enlargement warning - non-enlarged maps won't grow with Continental islands
        if not any(t.is_enlarged for t in tmpls):
            if not messagebox.askyesno(
                "DLC01 Compatibility Warning",
                "None of your map templates use the Enlarged (DLC01) setting.\n\n"
                "If players have the 'Prophecies of Ash' DLC active, the map will NOT expand and when no Continental island is manually placed in the regular playable area, the DLC01 content will not be fully available.\n\n"
                "To support DLC01, use 'New Map' with the Enlarged setting enabled, or edit the playable area to match an enlarged template.\n\n"
                "Proceed with export anyway?",
                parent=self.root,
            ):
                return

        # Enlarged template with no locked islands - base-game file will be empty
        for tmpl in tmpls:
            if tmpl.is_enlarged and not any(e.locked for e in tmpl.elements):
                if not messagebox.askyesno(
                    "No Locked Islands in Enlarged Template",
                    f"The {tmpl.region} template is set to Enlarged (DLC01), but no islands are marked as Locked.\n\n"
                    "Locked islands appear in the base-game map file (visible without DLC). Without any locked islands the base-game version of this map will be completely empty (no islands at all).\n\n"
                    "To mark an island as Locked, right-click it on the canvas and enable 'Locked'.\n\n"
                    "Proceed with export anyway?",
                    parent=self.root,
                ):
                    return

        # Show dialog - collects mod name, description, GUID, and output path
        dlg = _mod_exp.ModExportDialog(self.root, self)
        self.root.wait_window(dlg)
        if dlg._result is None:
            return  # user cancelled

        slug, display_name, description, start_guid, zip_path, install_path, debug_xml, auto_derive = dlg._result
        personal_mode = getattr(dlg, "_personal_mode", False)

        self.set_status("Building mod zip…")
        try:
            _mod_exp.build_mod_zip(
                templates=tmpls,
                slug=slug,
                display_name=display_name,
                description=description,
                start_guid=start_guid,
                zip_path=zip_path,
                app=self,
                install_path=install_path,
                debug_xml=debug_xml,
                auto_derive=auto_derive,
            )
        except _fdb.FileDBError as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self.root)
            self.set_status("Mod export failed.")
            return
        except Exception as exc:
            messagebox.showerror("Export Failed",
                                 f"An unexpected error occurred:\n{exc}",
                                 parent=self.root)
            self.set_status("Mod export failed.")
            return

        # Clean up temp zip used for personal-mode install-only exports
        if personal_mode and zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass

        self.set_status(
            f"Mod installed: {display_name}" if personal_mode
            else f"Mod exported: {os.path.basename(zip_path)}"
        )
        next_steps = (
            "1. Start a new game.\n"
            f"2. In game creation, select  \"{display_name}\"  under:\n"
            "   Difficulty \u2192 Game World \u2192 Map Layout\n\n"
            "Enjoy your custom map!"
        )
        if personal_mode:
            msg = (
                f"Mod installed to:\n{install_path}\n\n"
                "Next steps:\n" + next_steps
            )
        elif install_path:
            msg = (
                f"Mod saved to:\n{zip_path}\n\n"
                f"Mod installed to:\n{install_path}\n\n"
                "Next steps:\n" + next_steps
            )
        else:
            msg = (
                f"Mod saved to:\n{zip_path}\n\n"
                "Next steps:\n"
                "1. Install the mod via the Anno mod manager,\n"
                "   or extract the zip into your Anno 117 mods folder.\n"
                "2. Start a new game.\n"
                f"3. In game creation, select  \"{display_name}\"  under:\n"
                "   Difficulty \u2192 Game World \u2192 Map Layout\n\n"
                "Enjoy your custom map!"
            )
        messagebox.showinfo("Mod Created Successfully", msg, parent=self.root)

    def _collect_template_warnings(self, tmpl) -> List[str]:
        """Return all rule/placement warnings for one template."""
        warnings: List[str] = []
        region = tmpl.region
        pa = tmpl.playable_area  # (x1, y1, x2, y2)

        # ── Type-size rule violations ─────────────────────────────────────────
        for isl in tmpl.islands:
            if isl.is_fixed:
                continue  # fixed islands are controlled by the asset definition
            name = isl.display_name
            if isl.island_type == "ThirdParty" and isl.size != "Small":
                warnings.append(f"[{region}] {name}: 3rd Party must be Small (is {isl.size}).")
            if isl.island_type == "Pirate" and isl.size != "Medium":
                warnings.append(f"[{region}] {name}: Pirate must be Medium (is {isl.size}).")
            if isl.island_type == "Vulcan" and isl.size not in ("Medium", "Small"):
                warnings.append(f"[{region}] {name}: Vulcan must be M or S (is {isl.size}).")
            if isl.size == "Continental" and isl.island_type != "Continental":
                warnings.append(f"[{region}] {name}: Continental size requires Continental type.")
            if isl.island_type == "Continental" and isl.size != "Continental":
                warnings.append(f"[{region}] {name}: Continental type requires Continental size.")
            if isl.size == "Continental":
                warnings.append(f"[{region}] {name}: Continental islands must be Fixed.")
            if isl.island_type == "Vulcan" and region == "Albion":
                warnings.append(f"[{region}] {name}: Vulcan islands are not allowed in Albion.")
            if isl.size == "ExtraLarge" and region == "Albion":
                warnings.append(f"[{region}] {name}: ExtraLarge islands are not allowed in Albion.")

        # ── Pool / random-island limits ───────────────────────────────────────
        type_limits = config.ISLAND_LIMITS.get(region, {})
        for itype, size_limits in type_limits.items():
            if not size_limits:
                continue
            islands_of_type = [
                e for e in tmpl.islands
                if e.island_type == itype and not e.is_fixed
            ]
            if "any" in size_limits:
                count = len(islands_of_type)
                cap = size_limits["any"]
                if count > cap:
                    warnings.append(
                        f"[{region}] {itype}: {count} random islands exceed pool limit of {cap}."
                    )
            else:
                for size, cap in size_limits.items():
                    count = sum(1 for e in islands_of_type if e.size == size)
                    if count > cap:
                        warnings.append(
                            f"[{region}] {itype} {size}: {count} random islands exceed pool limit of {cap}."
                        )

        # ── Islands outside valid bounds ──────────────────────────────────────
        sx, sy = tmpl.size
        for isl in tmpl.islands:
            if isl.size == "Continental":
                # Use the raw game-coord side length for continental bounds checks.
                cs = isl.size_pixels   # 768
                px, py = isl.position
                x1, y1, x2, y2 = px, py, px + cs, py + cs
                # Hard constraint: must fit within map bounds
                if x1 < 0 or y1 < 0 or x2 > sx or y2 > sy:
                    warnings.append(
                        f"[{region}] {isl.display_name} at ({px},{py})"
                        f" extends outside the map bounds."
                    )
                else:
                    # Soft warning: >50 % of side length into the PA border zone
                    half = cs / 2
                    if (x1 < pa[0] - half or y1 < pa[1] - half or
                            x2 > pa[2] + half or y2 > pa[3] + half):
                        warnings.append(
                            f"[{region}] {isl.display_name} at ({px},{py})"
                            f" is >50 % into the PA border zone - may cause visual bugs or NPC issues."
                        )
            else:
                x1, y1, x2, y2 = isl.bounds
                if x1 < pa[0] or y1 < pa[1] or x2 > pa[2] or y2 > pa[3]:
                    warnings.append(
                        f"[{region}] {isl.display_name} at ({isl.position[0]},{isl.position[1]})"
                        f" is outside the playable area."
                    )

        # ── Missing spawn point ───────────────────────────────────────────────
        if not tmpl.ship_spawns:
            warnings.append(
                f"[{region}] No spawn point - the game will crash on load without one."
            )

        # ── Starter island minimum ────────────────────────────────────────────
        starter_count = sum(1 for e in tmpl.islands if e.island_type == "Starter")
        if starter_count < 4:
            warnings.append(
                f"[{region}] Only {starter_count}/4 Starter islands "
                f"- a map template should contain at least 4 to ensure correct NPC behaviour."
            )

        return warnings

    def _require_deployment_ready(self, tmpls) -> bool:
        """
        Hard-block guard for 'Export All Difficulties' and 'Export Mod'.

        Checks (in order, stops at first failure):
          1. Both Latium and Albion templates must be loaded.
          2. Every loaded template must have at least one ship spawn point.

        Shows an error dialog describing exactly what is missing.
        Returns True only when all checks pass.
        """
        loaded_regions = {t.region for t in tmpls}
        missing = [r for r in self.REGIONS if r not in loaded_regions]
        if missing:
            messagebox.showerror(
                "Both Regions Required",
                "Both Latium and Albion map templates must be loaded before exporting.\n\n"
                f"Missing: {', '.join(missing)}\n\n"
                "Open or import the missing region's XML in its tab, then try again.",
                parent=self.root,
            )
            return False

        no_spawn = [t.region for t in tmpls if not t.ship_spawns]
        if no_spawn:
            messagebox.showerror(
                "Missing Spawn Point",
                "Every map template must have at least one ship spawn point - the game will crash on load without one.\n\n"
                f"Missing in: {', '.join(no_spawn)}\n\n"
                "Add a spawn point via the toolbar, then try again.",
                parent=self.root,
            )
            return False

        _STARTER_MIN = 4
        few_starters = [
            (t.region, sum(1 for e in t.islands if e.island_type == "Starter"))
            for t in tmpls
            if sum(1 for e in t.islands if e.island_type == "Starter") < _STARTER_MIN
        ]
        if few_starters:
            details = "\n".join(
                f"  {region}: {count}/{_STARTER_MIN}" for region, count in few_starters
            )
            messagebox.showerror(
                "Insufficient Starter Islands",
                f"Each region needs at least {_STARTER_MIN} Starter islands so the game can assign one to each player slot and ensure correct NPC behaviour.\n\n"
                f"{details}\n\n"
                "Add more Starter islands and try again.",
                parent=self.root,
            )
            return False

        return True

    def _warn_before_export(self, tmpls) -> bool:
        """Collect warnings from all templates; show confirmation dialog if any. Returns True to proceed, False to abort."""
        all_warnings: List[str] = []
        for tmpl in tmpls:
            all_warnings.extend(self._collect_template_warnings(tmpl))

        if not all_warnings:
            return True

        msg = (
            "The following issues were detected:\n\n"
            + "\n".join(f"• {w}" for w in all_warnings)
            + "\n\nProceed anyway?"
        )
        return messagebox.askyesno("Export Warnings", msg, parent=self.root)

    # ── App lifecycle ─────────────────────────────────────────────────────────

    def _on_close(self):
        if self._confirm_discard():
            self.root.destroy()
