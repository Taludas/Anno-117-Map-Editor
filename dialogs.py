"""
Anno 117 Map Template Editor - Dialogs
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List

import config
import terrain_builder
from models import IslandElement

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ─── Helpers ────────────────────────────────────────────────────────────────

def _label(parent, text, font=None, fg=None, **kw):
    return tk.Label(
        parent, text=text,
        bg=config.BG_SECTION,
        fg=fg or config.FG_MAIN,
        font=font or config.FONT_BODY,
        **kw
    )


def _entry(parent, textvariable=None, width=28, **kw):
    e = tk.Entry(
        parent,
        textvariable=textvariable,
        bg=config.BG_HOVER,
        fg=config.FG_MAIN,
        insertbackground=config.FG_MAIN,
        relief=tk.FLAT,
        font=config.FONT_BODY,
        width=width,
        **kw
    )
    return e


def _combo(parent, values, textvariable=None, width=25, **kw):
    style_name = "Anno.TCombobox"
    cb = ttk.Combobox(
        parent,
        values=values,
        textvariable=textvariable,
        state="readonly",
        width=width,
        font=config.FONT_BODY,
        style=style_name,
        **kw
    )
    return cb


def _sep(parent):
    return tk.Frame(parent, height=1, bg=config.FG_SEPARATOR)


def _confirm_oversized_map(parent, size: int) -> bool:
    """
    Ask before committing to a map size the game does not render reliably.

    Returns True to proceed.  Sizes at or below NewMapDialog._SIZE_WARN pass
    without a prompt.  Building the terrain is cheap; what degrades past 4096 is
    the game's own object rendering, so the wording is about that, not the export.
    """
    if size <= NewMapDialog._SIZE_WARN:
        return True

    # In-game findings, same save, buildings placed across the map:
    #   4096 - no problems at all
    #   6144 - fine except very close to the map border
    #   8192 - buildings stop being drawn although they still work
    # The failing zone grows inward with map size, which points at a fixed
    # streaming range in the engine rather than anything in the map data.
    if size >= 8192:
        risk = ("At this size the game stops drawing buildings. They still "
                "function - menus, production and trade all work - but they are "
                "invisible.")
    elif size >= 6144:
        risk = ("At this size the game renders correctly except very close to "
                "the map border, where buildings may stop being drawn.")
    else:
        risk = ("Sizes above 4096 have not been tested individually; 6144 shows "
                "rendering problems near the map border, 8192 across the map.")

    return messagebox.askyesno(
        "Very Large Map",
        f"Map size {size}x{size} is well beyond anything the game ships "
        f"(2048, or 2688 enlarged), and only 4096 has been verified to work.\n\n"
        f"{risk}\n\n"
        "The map is still fully playable - this affects what you see, not what "
        "works.\n\n"
        "Create it anyway?",
        parent=parent,
    )


def _btn(parent, text, command, fg=None, bg=None, **kw):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg or config.BG_HOVER,
        fg=fg or config.FG_MAIN,
        activebackground=config.BG_HOVER,
        activeforeground=config.FG_GOLD,
        relief=tk.FLAT,
        font=config.FONT_BODY,
        padx=10, pady=4,
        cursor="hand2",
        **kw
    )


# ─── Base Modal ─────────────────────────────────────────────────────────────

class _BaseDialog(tk.Toplevel):
    def __init__(self, parent, title: str, width: int = 520, height: Optional[int] = 480):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(bg=config.BG_SECTION)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - (height or 400)) // 2

        if height is not None:
            self.geometry(f"{width}x{height}+{max(0,px)}+{max(0,py)}")
        else:
            # Placeholder: let content define height, then recentre
            self.geometry(f"{width}x1+{max(0,px)}+{max(0,py)}")

        self._build()

        if height is None:
            self.update_idletasks()
            actual_h = self.winfo_reqheight()
            py = parent.winfo_rooty() + (parent.winfo_height() - actual_h) // 2
            self.geometry(f"{width}x{actual_h}+{max(0,px)}+{max(0,py)}")

        self.wait_window(self)

    def _build(self):
        raise NotImplementedError


# ─── Island Properties Dialog ────────────────────────────────────────────────

class IslandPropertiesDialog(_BaseDialog):
    """Edit properties of an existing island element."""

    def __init__(self, parent, island: IslandElement):
        self._isl = island
        super().__init__(parent, "Island Properties", width=480, height=None)

    def _build(self):
        tk.Label(self, text="Island Properties", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 4))
        _sep(self).pack(fill="x", padx=10, pady=4)

        body = tk.Frame(self, bg=config.BG_SECTION)
        body.pack(fill="x", padx=16)

        # Size  (hidden for fixed islands - determined by asset)
        self._size_var = tk.StringVar(value=self._isl.size)
        self._size_frame = tk.Frame(body, bg=config.BG_SECTION)
        self._size_frame.pack(fill="x", pady=5)
        tk.Label(self._size_frame, text="Size", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, width=16, anchor="w").pack(side="left")
        _combo(self._size_frame, config.ISLAND_SIZES, self._size_var, width=14).pack(side="left")

        # Type  (hidden for fixed islands - determined by asset)
        # Initial options are filtered to only those valid for the current size.
        type_lbl = config.ISLAND_TYPE_LABELS.get(self._isl.island_type, self._isl.island_type)
        self._type_var = tk.StringVar(value=type_lbl)
        self._type_frame = tk.Frame(body, bg=config.BG_SECTION)
        self._type_frame.pack(fill="x", pady=5)
        tk.Label(self._type_frame, text="Type", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, width=16, anchor="w").pack(side="left")
        self._rand_type_combo = _combo(
            self._type_frame,
            self._type_options_for_size(self._isl.size, fixed=False),
            self._type_var, width=14,
        )
        self._rand_type_combo.pack(side="left")

        # Keep type options in sync whenever size changes
        self._size_var.trace_add("write", self._on_rand_size_change)

        # Fixed island state - set from island, not user-togglable here
        self._fixed_var = tk.BooleanVar(value=self._isl.is_fixed)
        self._rand_fert_var = tk.BooleanVar(value=getattr(self._isl, 'randomize_fertilities', False))

        self._fixed_frame = tk.Frame(body, bg=config.BG_SECTION)
        self._fixed_frame.pack(fill="x")

        # Position (read-only info)
        _sep(body).pack(fill="x", pady=6)
        pos = self._isl.position
        tk.Label(body, text=f"Position:  ({pos[0]}, {pos[1]})", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w")

        _sep(self).pack(fill="x", padx=10, pady=8)
        btn_f = tk.Frame(self, bg=config.BG_SECTION)
        btn_f.pack()
        _btn(btn_f, "  Apply  ", self._apply, fg=config.BG_MAIN, bg=config.FG_GOLD).pack(side="left", padx=8)
        _btn(btn_f, "  Cancel  ", self.destroy).pack(side="left", padx=8)

        # Expand fixed options if island is already fixed
        self._on_fixed_toggle()

    # In _on_fixed_toggle, build island picker if registry available
    def _on_fixed_toggle(self):
        from island_registry import IslandRegistry
        show = self._fixed_var.get()

        # Hide size/type dropdowns for fixed islands - asset defines them
        if show:
            self._size_frame.pack_forget()
            self._type_frame.pack_forget()
        else:
            self._size_frame.pack(fill="x", pady=5, before=self._fixed_frame)
            self._type_frame.pack(fill="x", pady=5, before=self._fixed_frame)

        # Clear and rebuild fixed frame contents
        for w in self._fixed_frame.winfo_children():
            w.destroy()

        if not show:
            return

        reg = IslandRegistry.instance()

        if reg.is_loaded:
            # Island picker dropdown
            tk.Label(self._fixed_frame, text="Select Island", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w")

            region = getattr(self._isl, '_region', 'Latium')
            islands = reg.for_region(region)
            # Group by type
            options = [f"{i.name}  [{i.size} / {i.island_type}]" for i in islands]
            self._island_options = islands

            self._picker_var = tk.StringVar()
            # Pre-select current if already fixed
            if self._isl.map_file_path:
                current = reg.find_by_name(self._isl.map_file_path)
                if current:
                    idx = islands.index(current) if current in islands else 0
                    self._picker_var.set(options[idx] if options else "")
            elif options:
                self._picker_var.set(options[0])

            cb = ttk.Combobox(self._fixed_frame, values=options, textvariable=self._picker_var, state="readonly", width=40, font=config.FONT_XSMALL, style="Anno.TCombobox")
            cb.pack(fill="x", pady=2)
            cb.bind("<<ComboboxSelected>>", self._on_island_picked)
        else:
            # Fallback to manual entry if registry not loaded
            tk.Label(self._fixed_frame, text="Map File Path", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w")
            self._mappath_var = tk.StringVar(value=self._isl.map_file_path or "")
            tk.Entry(self._fixed_frame, textvariable=self._mappath_var, bg=config.BG_HOVER, fg=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_XSMALL, width=40).pack(fill="x", pady=2)

        # Island Type (settable for fixed islands - controls RandomIslandConfig/value/Type/id)
        # ThirdParty/Pirate/Continental are reserved for specific assets only.
        # Vulcan is only valid on Small or Medium fixed islands.
        type_f = tk.Frame(self._fixed_frame, bg=config.BG_SECTION)
        type_f.pack(fill="x", pady=2)
        tk.Label(type_f, text="Island Type", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, width=12, anchor="w").pack(side="left")
        fixed_type_opts = self._type_options_for_size(self._isl.size, fixed=True)
        if self._type_var.get() not in fixed_type_opts:
            self._type_var.set(config.ISLAND_TYPE_LABELS["Normal"])
        self._fixed_type_combo = _combo(type_f, fixed_type_opts, self._type_var, width=14)
        self._fixed_type_combo.pack(side="left")

        # Island Label (editable; defaults to .a7m stem)
        lbl_f = tk.Frame(self._fixed_frame, bg=config.BG_SECTION)
        lbl_f.pack(fill="x", pady=2)
        tk.Label(lbl_f, text="Island Label", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, width=12, anchor="w").pack(side="left")
        default_label = self._isl.island_label or ""
        if not default_label and self._isl.map_file_path:
            default_label = os.path.splitext(os.path.basename(self._isl.map_file_path))[0]
        self._label_var = tk.StringVar(value=default_label)
        _entry(lbl_f, textvariable=self._label_var,
               width=30).pack(side="left", fill="x", expand=True)

        # Rotation
        rot_f = tk.Frame(self._fixed_frame, bg=config.BG_SECTION)
        rot_f.pack(fill="x", pady=2)
        tk.Label(rot_f, text="Rotation", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, width=12, anchor="w").pack(side="left")
        if not hasattr(self, '_rot_label_var'):
            current_rot_lbl = config.ROTATION_LABELS[self._isl.rotation90 % 4]
            self._rot_label_var = tk.StringVar(value=current_rot_lbl)
        ttk.Combobox(rot_f, values=config.ROTATION_LABELS, textvariable=self._rot_label_var, state="readonly", width=8, font=config.FONT_XSMALL, style="Anno.TCombobox").pack(side="left")

        # Fertilities - visual picker
        self._build_fertility_picker(self._fixed_frame)

        def _on_rand_fert_toggle():
            """When Randomise is ticked, clear all manually selected fertilities."""
            if self._rand_fert_var.get():
                for v in self._fert_check_vars.values():
                    v.set(False)

        self._rand_fert_chk = tk.Checkbutton(
            self._fixed_frame, text="Randomise fertilities",
            variable=self._rand_fert_var,
            command=_on_rand_fert_toggle,
            bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, font=config.FONT_XSMALL
        )
        self._rand_fert_chk.pack(anchor="w", pady=2)
        # If fertilities are already selected, clear the Randomise flag (but leave checkbox enabled)
        if any(v.get() for v in self._fert_check_vars.values()):
            self._rand_fert_var.set(False)

    @staticmethod
    def _type_options_for_size(size: str, fixed: bool) -> list:
        """
        Return the allowed Island Type labels for an island of *size*.

        Rules (apply to both random and fixed unless noted):
          Small       → Normal, 3rd Party, Vulcan
          Medium      → Normal, Pirate, Vulcan
          Large       → Normal, Starter
          ExtraLarge  → Normal, Starter
          Continental → Continental  (fixed only - random continental not valid)
        """
        L = config.ISLAND_TYPE_LABELS
        if size == "Small":
            return [L["Normal"], L["ThirdParty"], L["Vulcan"]]
        if size == "Medium":
            return [L["Normal"], L["Pirate"], L["Vulcan"]]
        if size in ("Large", "ExtraLarge"):
            return [L["Normal"], L["Starter"]]
        if size == "Continental" and fixed:
            return [L["Continental"]]
        # Fallback (e.g. unknown size or continental random - shouldn't normally occur)
        return [L["Normal"]]

    def _on_rand_size_change(self, *_):
        """Update the random-island type dropdown when the size selection changes."""
        size = self._size_var.get()
        new_opts = self._type_options_for_size(size, fixed=False)
        self._rand_type_combo.configure(values=new_opts)
        if self._type_var.get() not in new_opts:
            self._type_var.set(new_opts[0])

    def _on_island_picked(self, _event=None):
        """Update island metadata when user picks from dropdown."""
        sel = self._picker_var.get()
        if not sel or not hasattr(self, '_island_options'):
            return
        try:
            idx = [f"{i.name}  [{i.size} / {i.island_type}]"
                for i in self._island_options].index(sel)
            asset = self._island_options[idx]
            # Auto-set size from registry
            self._size_var.set(asset.size)
            # Refresh type dropdown options based on new size
            if hasattr(self, '_fixed_type_combo'):
                new_opts = self._type_options_for_size(asset.size, fixed=True)
                self._fixed_type_combo.configure(values=new_opts)
                if self._type_var.get() not in new_opts:
                    self._type_var.set(config.ISLAND_TYPE_LABELS["Normal"])
            # Default label to the .a7m file stem
            if hasattr(self, '_label_var'):
                stem = os.path.splitext(os.path.basename(asset.file_path))[0]
                self._label_var.set(stem)
        except (ValueError, IndexError):
            pass

    def _build_fertility_picker(self, parent: tk.Frame) -> None:
        """Build a scrollable 3-column icon-grid for selecting fertilities."""
        from fertility_registry import FertilityRegistry
        reg = FertilityRegistry.instance()

        tk.Label(parent, text="Fertilities", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", pady=(4, 1))

        # Outer frame with fixed height and scrollbar
        outer = tk.Frame(parent, bg=config.BG_SECTION)
        outer.pack(fill="x")
        canvas = tk.Canvas(outer, bg=config.BG_SECTION, highlightthickness=0, height=160)
        sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=config.BG_SECTION)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        canvas.bind("<Button-4>",   lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>",   lambda e: canvas.yview_scroll(1, "units"))

        # Pre-selected GUIDs from the island
        selected_guids: set = set(self._isl.fertility_guids)
        region = getattr(self._isl, '_region', 'Latium')

        self._fert_check_vars: dict = {}  # guid → BooleanVar
        self._fert_icon_refs:  list = []  # keep PhotoImage refs alive

        if not reg.is_loaded:
            tk.Label(inner, text="Registry not loaded - enter GUIDs manually:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w")
            if not hasattr(self, '_fert_var'):
                self._fert_var = tk.StringVar(
                    value=" ".join(str(g) for g in self._isl.fertility_guids))
            tk.Entry(inner, textvariable=self._fert_var, bg=config.BG_HOVER, fg=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_XSMALL, width=36).pack(fill="x", pady=2)
            return

        fertilities = reg.for_region(region)

        # Group: shared (Both) first, then region-specific
        shared   = [f for f in fertilities if f.region == "Both"]
        specific = [f for f in fertilities if f.region != "Both"]

        def _on_check_toggle():
            """When any fertility is manually ticked, clear the Randomise flag."""
            has_selected = any(v.get() for v in self._fert_check_vars.values())
            if has_selected:
                self._rand_fert_var.set(False)

        COLS = 3

        def _add_group(label: str, items):
            if not items:
                return
            tk.Label(inner, text=label, bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_XSMALL).pack(anchor="w", padx=4, pady=(4, 1))

            # Build items into rows of COLS columns using grid
            grid_frame = tk.Frame(inner, bg=config.BG_SECTION)
            grid_frame.pack(fill="x", padx=4, pady=1)
            for col in range(COLS):
                grid_frame.columnconfigure(col, weight=1, uniform="col")

            for idx, fert in enumerate(items):
                row_idx, col_idx = divmod(idx, COLS)
                var = tk.BooleanVar(value=(fert.guid in selected_guids))
                self._fert_check_vars[fert.guid] = var

                cell = tk.Frame(grid_frame, bg=config.BG_SECTION)
                cell.grid(row=row_idx, column=col_idx, sticky="ew", padx=2, pady=1)

                # Icon (20×20)
                if PIL_AVAILABLE and os.path.isfile(fert.icon_path):
                    try:
                        img = Image.open(fert.icon_path).convert("RGBA").resize((20, 20), Image.LANCZOS)
                        tk_img = ImageTk.PhotoImage(img)
                        self._fert_icon_refs.append(tk_img)
                        tk.Label(cell, image=tk_img, bg=config.BG_SECTION).pack(side="left", padx=(0, 2))
                    except Exception:
                        tk.Label(cell, text="•", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, width=2).pack(side="left")
                else:
                    tk.Label(cell, text="•", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, width=2).pack(side="left")

                tk.Checkbutton(
                    cell, text=fert.display_name,
                    variable=var,
                    command=_on_check_toggle,
                    bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION, activeforeground=config.FG_GOLD, font=config.FONT_XSMALL, anchor="w").pack(side="left", fill="x", expand=True)

        region_label = "Roman (Latium)" if region == "Latium" else "Celtic (Albion)"
        _add_group("Universal", shared)
        _add_group(region_label, specific)

        # Forward scroll events from all child widgets to the canvas scrollbar
        def _bind_scroll(widget):
            widget.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
            widget.bind("<Button-4>",   lambda _: canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>",   lambda _: canvas.yview_scroll(1, "units"))
            for child in widget.winfo_children():
                _bind_scroll(child)
        _bind_scroll(inner)

    def _apply(self):
        size = self._size_var.get()
        lbl  = self._type_var.get()
        island_type = next((k for k, v in config.ISLAND_TYPE_LABELS.items() if v == lbl), "Normal")
        is_fixed = self._fixed_var.get()

        # ── Validate rules (random islands only - fixed assets define their own size/type) ──
        if not is_fixed:
            errors = []
            if island_type == "ThirdParty" and size != "Small":
                errors.append("3rd Party islands must be Size: Small.")
            if island_type == "Pirate" and size != "Medium":
                errors.append("Pirate islands must be Size: Medium.")
            if island_type == "Vulcan" and size not in ("Medium", "Small"):
                errors.append("Vulcan islands must be Size: Medium or Small.")
            if size == "Continental" and island_type != "Continental":
                errors.append("Continental size requires Continental type.")
            if island_type == "Continental" and size != "Continental":
                errors.append("Continental type requires Continental size.")
            if size == "Continental":
                errors.append("Continental islands must be Fixed (specific map file).")
            if island_type == "Continental":
                errors.append("Continental islands must be Fixed (specific map file).")
            if errors:
                messagebox.showerror("Invalid Configuration",
                                     "\n".join(errors), parent=self)
                return  # keep dialog open

        isl = self._isl
        isl.size = size
        isl.island_type = island_type

        if self._fixed_var.get():
            # Get path from picker or manual entry
            from island_registry import IslandRegistry
            reg = IslandRegistry.instance()
            if reg.is_loaded and hasattr(self, '_picker_var') and hasattr(self, '_island_options'):
                sel = self._picker_var.get()
                options = [f"{i.name}  [{i.size} / {i.island_type}]"
                        for i in self._island_options]
                try:
                    idx = options.index(sel)
                    asset = self._island_options[idx]
                    isl.map_file_path = asset.file_path
                    isl.size = asset.size
                    # island_type comes from the Type dropdown (user can override registry value)
                except (ValueError, IndexError):
                    pass
            else:
                isl.map_file_path = getattr(self, '_mappath_var', tk.StringVar()).get().strip() or None

            isl.island_label  = getattr(self, '_label_var', None) and self._label_var.get().strip() or None
            rot_lbl = getattr(self, '_rot_label_var', None)
            if rot_lbl is not None:
                try:
                    isl.rotation90 = config.ROTATION_LABELS.index(rot_lbl.get())
                except ValueError:
                    isl.rotation90 = 0
            if hasattr(self, '_fert_check_vars') and self._fert_check_vars:
                isl.fertility_guids = [guid for guid, var in self._fert_check_vars.items() if var.get()]
            elif hasattr(self, '_fert_var') and self._fert_var is not None:
                isl.fertility_guids = [int(x) for x in self._fert_var.get().strip().split() if x.isdigit()]
            isl.randomize_fertilities = self._rand_fert_var.get()
            isl.element_type = 0
        else:
            isl.map_file_path = None
            isl.element_type  = 1

        self.result = isl
        self.destroy()


# ─── New Map Dialog ──────────────────────────────────────────────────────────

class NewMapDialog(_BaseDialog):
    """Ask for region / difficulty / playable-area for a new blank map.

    Map size is user-adjustable per region (default 2048, 2688 while "Enlarged" is checked for Latium).
    The PlayableArea border is user-adjustable in 4 px steps per region, minimum 20 px on any side, maximum 50 % of the map dimension per axis.
    InitialPlayableArea is always derived automatically (never user-editable).
    """

    # DLC expansion adds this many px to PA x2/y2 on enlarged Latium.
    _ENL_EXP = config.ENL_PA_EXPANSION  # 420

    # Default / enlarged map size ("Enlarged" only nudges Latium to _SIZE_ENL).
    _SIZE_STD = 2048
    _SIZE_ENL = 2688
    # Sizes must land on the .a7te chunk grid (64) - see terrain_builder.
    # Cost grows with S squared, because the .a7t holds two height maps of
    # (2*S+1)^2 samples.  Building it is cheap - 0.2 s at 2048, 0.6 s at 4096,
    # 2.3 s at 8192 - so the limit is not the export.
    #
    # What limits the size is the game: tested in-game, 4096 renders perfectly,
    # 6144 fails only very close to the map border, and at 8192 buildings stop
    # being drawn altogether (they still function).  The failing zone grows
    # inward as the map grows, so it looks like a fixed streaming range in the
    # engine, not anything in the map data - nothing here can widen it.
    #
    # Larger sizes stay available because the maps are still playable, but
    # anything past _SIZE_WARN has to be confirmed.  The FileDB format itself
    # runs out just under 16384, where the height maps overflow its 32-bit
    # offsets; filedb_io raises there.
    _SIZE_MIN  = terrain_builder.MIN_SIZE
    _SIZE_MAX  = 8192
    _SIZE_WARN = 4096
    _SIZE_STEP = terrain_builder.CHUNK_SIZE

    def __init__(self, parent):
        super().__init__(parent, "New Map Template", width=450, height=None)

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        tk.Label(self, text="New Map Template", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 4))
        _sep(self).pack(fill="x", padx=10, pady=4)

        body = tk.Frame(self, bg=config.BG_SECTION)
        body.pack(fill="x", padx=16)

        # Region
        self._region_var = tk.StringVar(value="Latium")
        rf = tk.Frame(body, bg=config.BG_SECTION)
        rf.pack(fill="x", pady=5)
        tk.Label(rf, text="Region", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, width=20, anchor="w").pack(side="left")
        _combo(rf, ["Latium", "Albion"], self._region_var, width=12).pack(side="left")
        self._region_var.trace_add("write", self._on_region_change)

        # Difficulty
        diff_labels = list(config.DIFFICULTY_LABELS.values())
        self._diff_var = tk.StringVar(value=config.DIFFICULTY_LABELS["easy"])
        df = tk.Frame(body, bg=config.BG_SECTION)
        df.pack(fill="x", pady=5)
        tk.Label(df, text="Difficulty", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, width=20, anchor="w").pack(side="left")
        _combo(df, diff_labels, self._diff_var, width=12).pack(side="left")

        # Enlarged option (Latium only)
        self._enlarged_var = tk.BooleanVar(value=False)
        self._enlarged_chk = tk.Checkbutton(
            body, text="Enlarged template (DLC expansion)",
            variable=self._enlarged_var,
            command=self._on_enlarged_toggle,
            bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION, activeforeground=config.FG_GOLD, font=config.FONT_SMALL)
        self._enlarged_chk.pack(anchor="w", pady=4)

        # ── Playable Area sliders ──────────────────────────────────────────────
        _sep(body).pack(fill="x", pady=(6, 4))
        tk.Label(body, text="Playable Area  (2 px steps · PA coords always /4)", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_XSMALL).pack(anchor="w", pady=(0, 4))

        # Info var must exist before any slider trace fires _update_info.
        self._info_var = tk.StringVar()

        # Per-region map size. Freely adjustable in both modes; toggling
        # "Enlarged" only swaps Latium between the two defaults.
        self._size_var: dict = {}

        # Per-region slider vars: dist = border distance, ox/oy = axis offsets.
        # PA formula: (dist+ox, dist+oy, size-dist+ox, size-dist+oy)
        self._pa_dist: dict = {}
        self._pa_ox:   dict = {}
        self._pa_oy:   dict = {}
        # Scale widget references for dynamic limit updates
        self._pa_ox_sl: dict = {}
        self._pa_oy_sl: dict = {}

        SL_KW = dict(orient=tk.HORIZONTAL, length=180, showvalue=False, bg=config.BG_SECTION, fg=config.FG_MAIN, troughcolor=config.BG_HOVER, activebackground=config.FG_GOLD, highlightthickness=0)

        def _make_slider_row(parent, label, var, from_, to_, resolution=2):
            row = tk.Frame(parent, bg=config.BG_SECTION)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, width=17, anchor="w", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(side="left")

            # sl_ref lets _entry_to_slider read the live slider bounds even
            # though the Scale widget doesn't exist yet when the closure is made.
            sl_ref = [None]
            entry_var = tk.StringVar()

            def _slider_to_entry(*_):
                """Slider changed → update the entry field."""
                entry_var.set(str(var.get()))
                self._update_info()

            def _entry_to_slider(*_):
                """Entry committed (Return / FocusOut) → parse, snap, clamp, apply."""
                try:
                    raw = int(entry_var.get())
                except ValueError:
                    entry_var.set(str(var.get()))   # revert to current value
                    return
                snapped = round(raw / resolution) * resolution
                sl = sl_ref[0]
                if sl is not None:
                    lo = int(float(sl.cget("from")))
                    hi = int(float(sl.cget("to")))
                    snapped = max(lo, min(hi, snapped))
                var.set(snapped)   # triggers _slider_to_entry via trace

            var.trace_add("write", _slider_to_entry)
            _slider_to_entry()   # initialise entry with current var value

            sl = tk.Scale(row, variable=var, from_=from_, to=to_, resolution=resolution, command=lambda *_: None, **SL_KW)
            sl.pack(side="left")
            sl_ref[0] = sl

            ent = _entry(row, textvariable=entry_var, width=6)
            ent.pack(side="left", padx=2)
            ent.bind("<Return>",   _entry_to_slider)
            ent.bind("<FocusOut>", _entry_to_slider)
            tk.Label(row, text="px", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(side="left")
            return sl

        for region in ["Latium", "Albion"]:
            size_var = tk.IntVar(value=self._SIZE_STD)
            self._size_var[region] = size_var

            dist_var = tk.IntVar(value=24)
            ox_var   = tk.IntVar(value=-4)
            oy_var   = tk.IntVar(value=-4)
            self._pa_dist[region] = dist_var
            self._pa_ox[region]   = ox_var
            self._pa_oy[region]   = oy_var

            rf = tk.Frame(body, bg=config.BG_SECTION)
            rf.pack(fill="x", pady=(4, 0))
            tk.Label(rf, text=f"{region}:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w")

            _make_slider_row(rf, "Map size", size_var,
                             self._SIZE_MIN, self._SIZE_MAX, resolution=self._SIZE_STEP)

            # Initial offset range: [20-dist, dist-20] = [-4, 4] for default dist=24.
            _make_slider_row(rf, "Border distance", dist_var, 0, 2048, resolution=2)
            ox_sl = _make_slider_row(rf, "X axis offset", ox_var, -4, 4, resolution=2)
            oy_sl = _make_slider_row(rf, "Y axis offset", oy_var, -4, 4, resolution=2)
            self._pa_ox_sl[region] = ox_sl
            self._pa_oy_sl[region] = oy_sl

            # When dist changes: recompute offset bounds to enforce a 20 px
            # minimum border on all four sides.
            # PA x1 = dist+ox ≥ 20  →  ox ≥ 20-dist
            # PA x2 = size-dist+ox ≤ size-20  →  ox ≤ dist-20
            def _make_dist_trace(reg, dv, xv, yv):
                def _on_dist(*_):
                    dist = dv.get()
                    lo = 20 - dist
                    hi = dist - 20
                    if hi < lo:   # dist < 20: no valid offset possible
                        lo = hi = 0
                    xv.set(max(lo, min(hi, xv.get())))
                    yv.set(max(lo, min(hi, yv.get())))
                    self._pa_ox_sl[reg].configure(from_=lo, to=hi)
                    self._pa_oy_sl[reg].configure(from_=lo, to=hi)
                return _on_dist
            dist_var.trace_add("write", _make_dist_trace(region, dist_var, ox_var, oy_var))

        # Info label - monospace font so space-padded columns align correctly;
        # fixed height for the 6-line enlarged case.
        tk.Label(body, textvariable=self._info_var,
                 bg=config.BG_SECTION, fg=config.FG_DIM,
                 font=("Consolas", 9), justify="left",
                 height=6, anchor="nw").pack(anchor="w", pady=(6, 4))

        # ── Live preview canvas ────────────────────────────────────────────────
        _sep(body).pack(fill="x", pady=(2, 4))
        tk.Label(body, text="Preview", bg=config.BG_SECTION, fg=config.FG_GOLD,
                 font=config.FONT_XSMALL).pack(anchor="w")
        self._preview_canvas = tk.Canvas(body, width=380, height=100, bg=config.BG_MAIN, highlightthickness=0)
        self._preview_canvas.pack(pady=(2, 6))

        self._update_info()

        _sep(self).pack(fill="x", padx=10, pady=8)
        btn_f = tk.Frame(self, bg=config.BG_SECTION)
        btn_f.pack(pady=(0, 12))
        _btn(btn_f, "  Create  ", self._create, fg=config.BG_MAIN, bg=config.FG_GOLD).pack(side="left", padx=8)
        _btn(btn_f, "  Cancel  ", self.destroy).pack(side="left", padx=8)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _read_pa(self, region: str) -> tuple:
        """Return (x1,y1,x2,y2) derived from the three sliders for *region*."""
        size = self._size_var[region].get()
        dist = self._pa_dist[region].get()
        ox   = self._pa_ox[region].get()
        oy   = self._pa_oy[region].get()
        # Sliders use 2 px resolution; snap the final PA coordinates to multiples of 4 so the XML output is always on the game's preferred 4 px grid.
        def _s4(v):
            return (v // 4) * 4
        return (
            _s4(dist + ox),
            _s4(dist + oy),
            _s4(size - dist + ox),
            _s4(size - dist + oy),
        )

    @staticmethod
    def _ipa_from_pa(pa: tuple, enlarged: bool) -> tuple:
        """Compute InitialPlayableArea from PlayableArea (Latium enlarged only)."""
        if enlarged:
            exp = config.ENL_PA_EXPANSION
            return (pa[0], pa[1], pa[2] - exp, pa[3] - exp)
        return pa

    def _lat_size(self) -> int:
        return self._size_var["Latium"].get()

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _on_region_change(self, *_):
        if self._region_var.get() == "Albion":
            self._enlarged_var.set(False)
            self._enlarged_chk.config(state="disabled")
        else:
            self._enlarged_chk.config(state="normal")
        self._update_info()

    def _on_enlarged_toggle(self):
        # Switch Latium sliders to the enlarged or standard defaults.
        # Setting dist fires the trace which automatically expands the ox/oy limits before the ox/oy set() calls happen (trace runs synchronously).
        # The size slider stays live either way. It used to be locked to 2688
        # here because the enlarged .a7t/.a7te were pre-baked at that size;
        # terrain_builder generates them per size now, so any size works.
        # Only nudge the size to the enlarged default when the user has not
        # picked one of their own, so an existing choice is never overwritten.
        if self._enlarged_var.get():
            if self._size_var["Latium"].get() == self._SIZE_STD:
                self._size_var["Latium"].set(self._SIZE_ENL)
            # dist=134, ox=oy=-114 → PA = (20,20,2440,2440) at 2688, all coords /4
            self._pa_dist["Latium"].set(134)
            self._pa_ox["Latium"].set(-114)
            self._pa_oy["Latium"].set(-114)
        else:
            if self._size_var["Latium"].get() == self._SIZE_ENL:
                self._size_var["Latium"].set(self._SIZE_STD)
            self._pa_dist["Latium"].set(24)
            self._pa_ox["Latium"].set(-4)
            self._pa_oy["Latium"].set(-4)
        self._update_info()

    def _update_preview(self, lat_pa: tuple, alb_pa: tuple, enlarged: bool) -> None:
        """Redraw the isometric preview canvas showing both region PA diamonds."""
        if not hasattr(self, "_preview_canvas"):
            return
        cv = self._preview_canvas
        cv.delete("all")

        W = int(cv["width"])
        H = int(cv["height"])
        import math

        lat_size = self._size_var["Latium"].get()
        alb_size = self._size_var["Albion"].get()

        # We lay out the two regions side-by-side.
        # Each slot is (W//2) × H; the isometric diamond of a square map with side S fits in a box of width S*√2 × height S*√2.
        # We want the larger diamond (enlarged Latium = 2688) to fill its slot.
        slot_w = W // 2
        slot_h = H
        margin = 6 # px padding around each diamond

        region = self._region_var.get()

        def _gts(gx, gy, cx, cy, scale, S):
            """Game-to-screen isometric transform centred at (cx, cy)."""
            sx = cx + scale * (gx - S / 2 - (gy - S / 2)) / math.sqrt(2)
            sy = cy - scale * (gx - S / 2 + (gy - S / 2)) / math.sqrt(2)
            return sx, sy

        def _draw_region(label, pa, size, slot_x):
            # Scale so the full diamond fits the slot with margin.
            # Diamond half-width = size * scale / sqrt(2) → target = slot_w//2 - margin
            half_target = min(slot_w // 2 - margin, slot_h // 2 - margin)
            scale = half_target * math.sqrt(2) / size

            cx = slot_x + slot_w // 2
            cy = slot_h // 2

            corners = [(0, 0), (size, 0), (size, size), (0, size)]
            pts = [_gts(gx, gy, cx, cy, scale, size) for gx, gy in corners]
            flat = [c for p in pts for c in p]

            # Map border diamond (dim)
            dim_col = "#2a3a4a"
            cv.create_polygon(flat, fill=dim_col, outline="#3a5060", width=1)

            # PA diamond
            pa_corners = [(pa[0], pa[1]), (pa[2], pa[1]), (pa[2], pa[3]), (pa[0], pa[3])]
            pa_pts = [_gts(gx, gy, cx, cy, scale, size) for gx, gy in pa_corners]
            pa_flat = [c for p in pa_pts for c in p]
            highlight = "#c8a84b" if label == region else "#4a8fc7"
            cv.create_polygon(pa_flat, fill="", outline=highlight, width=2)

            # Label
            cv.create_text(cx, cy + half_target + 4, text=label, fill=highlight, font=("Segoe UI", 7), anchor="n")

        _draw_region("Latium", lat_pa, lat_size, 0)
        _draw_region("Albion", alb_pa, alb_size, slot_w)

        # Divider
        cv.create_line(slot_w, 2, slot_w, H - 2, fill="#334455", width=1)

    def _update_info(self):
        try:
            lat = self._read_pa("Latium")
            alb = self._read_pa("Albion")
        except Exception:
            return

        enlarged = self._enlarged_var.get()
        lat_ipa  = self._ipa_from_pa(lat, enlarged)
        lat_size = self._size_var["Latium"].get()
        alb_size = self._size_var["Albion"].get()

        def _f(pa):
            return f"{pa[0]} {pa[1]} {pa[2]} {pa[3]}"

        self._update_preview(lat, alb, enlarged)

        if enlarged:
            self._info_var.set(
                f"Latium size:           {lat_size} × {lat_size}\n"
                f"Latium playable area:  {_f(lat)}\n"
                f"Latium initial PA:     {_f(lat_ipa)}  (auto)\n"
                f"Albion size:           {alb_size} × {alb_size}\n"
                f"Albion playable area:  {_f(alb)}\n"
                f"Albion initial PA:     {_f(alb)}  (auto)"
            )
        else:
            self._info_var.set(
                f"Latium size:           {lat_size} × {lat_size}\n"
                f"Latium playable area:  {_f(lat)}\n"
                f"Latium initial PA:     {_f(lat)}  (auto)\n"
                f"Albion size:           {alb_size} × {alb_size}\n"
                f"Albion playable area:  {_f(alb)}\n"
                f"Albion initial PA:     {_f(alb)}  (auto)"
            )

    # ── create ────────────────────────────────────────────────────────────────

    def _create(self):
        region   = self._region_var.get()
        enlarged = self._enlarged_var.get() and region == "Latium"
        diff_lbl = self._diff_var.get()
        difficulty = next(
            (k for k, v in config.DIFFICULTY_LABELS.items() if v == diff_lbl), "easy"
        )

        lat = self._read_pa("Latium")
        alb = self._read_pa("Albion")

        lat_size = self._size_var["Latium"].get()
        alb_size = self._size_var["Albion"].get()

        # Validate both regions
        # With sliders: pa = (dist+ox, dist+oy, size-dist+ox, size-dist+oy)
        # All four borders must be ≥ 20; playable span = size-2*dist ≥ size//2.
        for name, pa, sz in (("Latium", lat, lat_size), ("Albion", alb, alb_size)):
            min_b = 20
            errors = []
            if pa[0] < min_b or pa[1] < min_b:
                errors.append(f"Left/bottom border < {min_b} px  (increase distance or raise offset)")
            if sz - pa[2] < min_b or sz - pa[3] < min_b:
                errors.append(f"Right/top border < {min_b} px  (increase distance or lower offset)")
            if pa[2] - pa[0] < sz // 2 or pa[3] - pa[1] < sz // 2:
                errors.append(f"Playable span < 50 % of map  (reduce border distance)")
            if pa[2] <= pa[0] or pa[3] <= pa[1]:
                errors.append("Playable area has zero or negative size")
            if errors:
                messagebox.showerror(
                    "Invalid Playable Area",
                    f"{name}:\n" + "\n".join(f"• {e}" for e in errors),
                    parent=self,
                )
                return

        # Terrain build cost grows with the square of the map size, and the map
        # is only built at export time - warn here rather than let someone find
        # out after designing a whole map.
        if not _confirm_oversized_map(self, max(lat_size, alb_size)):
            return

        companion_pa   = alb if region == "Latium" else lat
        primary_pa     = lat if region == "Latium" else alb
        primary_size   = (lat_size, lat_size) if region == "Latium" else (alb_size, alb_size)
        companion_size = (alb_size, alb_size) if region == "Latium" else (lat_size, lat_size)

        self.result = {
            "region":                  region,
            "size":                    primary_size,
            "playable_area":           primary_pa,
            "initial_playable_area":   primary_pa, # canvas uses this; save_xml derives IPA fresh
            "enlargement_offset":      (0, 0),
            "is_enlarged":             enlarged,
            "difficulty":              difficulty,
            "companion_playable_area": companion_pa,
            "companion_size":          companion_size,
        }
        self.destroy()

# ─── Resize Map ─────────────────────────────────────────────────────────────

class ResizeMapDialog(_BaseDialog):
    """Grow the total map size of an already-created template.

    Only enlarging is allowed - shrinking would risk pushing existing islands
    outside the map/PA bounds. New space is always added on the north/east
    edges (x2/y2); the existing Playable Area border widths (and therefore
    every island already placed) are left completely untouched.
    """

    _SIZE_MAX  = NewMapDialog._SIZE_MAX
    _SIZE_STEP = NewMapDialog._SIZE_STEP

    def __init__(self, parent, current_size: int, region: str):
        self._current_size = current_size
        self._region = region
        super().__init__(parent, "Resize Map", width=380, height=None)

    def _build(self):
        tk.Label(self, text=f"Resize {self._region} Map", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 4))
        _sep(self).pack(fill="x", padx=10, pady=4)

        body = tk.Frame(self, bg=config.BG_SECTION)
        body.pack(fill="x", padx=16, pady=(4, 0))

        tk.Label(body, text=f"Current size: {self._current_size} × {self._current_size} px", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL).pack(anchor="w", pady=(0, 8))

        row = tk.Frame(body, bg=config.BG_SECTION)
        row.pack(fill="x")
        tk.Label(row, text="New size", width=10, anchor="w", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL).pack(side="left")

        self._size_var = tk.IntVar(value=self._current_size)
        entry_var = tk.StringVar(value=str(self._current_size))

        sl = tk.Scale(row, variable=self._size_var, from_=self._current_size, to=self._SIZE_MAX,
                       resolution=self._SIZE_STEP, orient=tk.HORIZONTAL, length=180, showvalue=False,
                       bg=config.BG_SECTION, fg=config.FG_MAIN, troughcolor=config.BG_HOVER,
                       activebackground=config.FG_GOLD, highlightthickness=0,
                       command=lambda *_: entry_var.set(str(self._size_var.get())))
        sl.pack(side="left")

        def _entry_to_slider(*_):
            try:
                raw = int(entry_var.get())
            except ValueError:
                entry_var.set(str(self._size_var.get()))
                return
            # Snap to the same step the slider uses - a tk.Scale does not coerce
            # a value written straight into its variable, so an unsnapped one
            # would survive into the template and leave the .a7tinfo size off the
            # .a7te chunk grid.
            snapped = round(raw / self._SIZE_STEP) * self._SIZE_STEP
            snapped = max(self._current_size, min(self._SIZE_MAX, snapped))
            self._size_var.set(snapped)
            entry_var.set(str(snapped))

        ent = _entry(row, textvariable=entry_var, width=6)
        ent.pack(side="left", padx=(4, 2))
        ent.bind("<Return>",   _entry_to_slider)
        ent.bind("<FocusOut>", _entry_to_slider)
        tk.Label(row, text="px", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(side="left")

        tk.Label(body, text="New space is added on the north/east edges.\nExisting islands and the Playable Area borders\naround them stay exactly where they are.",
                 bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left").pack(anchor="w", pady=(10, 4))

        _sep(self).pack(fill="x", padx=10, pady=8)
        btn_f = tk.Frame(self, bg=config.BG_SECTION)
        btn_f.pack(pady=(0, 12))
        _btn(btn_f, "  Resize  ", self._confirm, fg=config.BG_MAIN, bg=config.FG_GOLD).pack(side="left", padx=8)
        _btn(btn_f, "  Cancel  ", self.destroy).pack(side="left", padx=8)

    def _confirm(self):
        new_size = self._size_var.get()
        if new_size <= self._current_size:
            messagebox.showinfo("No Change", "New size must be larger than the current size.", parent=self)
            return
        if not _confirm_oversized_map(self, new_size):
            return
        self.result = new_size
        self.destroy()

# ─── Fixed Island Picker ────────────────────────────────────────────────────────────

class FixedIslandPickerDialog(_BaseDialog):
    """Pick a specific island asset for fixed placement."""

    def __init__(self, parent, region: str = "Latium"):
        self._region = region
        super().__init__(parent, "Select Fixed Island", width=700, height=480)

    def _build(self):
        from island_registry import IslandRegistry
        reg = IslandRegistry.instance()

        tk.Label(self, text="Select Fixed Island", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14,4))
        _sep(self).pack(fill="x", padx=10, pady=4)

        if not reg.is_loaded:
            tk.Label(self, text="Island registry not loaded.\nExtract game files first via File → Import from Game.", bg=config.BG_SECTION, fg="#e74c3c", font=config.FONT_SMALL).pack(pady=20)
            _btn(self, "Close", self.destroy).pack()
            return

        # Filter bar - row 1: text search
        fbar1 = tk.Frame(self, bg=config.BG_SECTION)
        fbar1.pack(fill="x", padx=12, pady=(4, 1))
        tk.Label(fbar1, text="Filter:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL).pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._populate())
        tk.Entry(fbar1, textvariable=self._filter_var, width=28, bg=config.BG_HOVER, fg=config.FG_MAIN, insertbackground=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_SMALL).pack(side="left", padx=6)

        # Filter bar - row 2: type radio buttons
        fbar2 = tk.Frame(self, bg=config.BG_SECTION)
        fbar2.pack(fill="x", padx=12, pady=(1, 4))
        tk.Label(fbar2, text="Type:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL).pack(side="left")
        self._type_filter_var = tk.StringVar(value="All")
        for t in ("All", "Normal", "Continental", "ThirdParty", "Pirate", "Vulcan"):
            tk.Radiobutton(fbar2, text=t, variable=self._type_filter_var, value=t, command=self._populate, bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, font=config.FONT_XSMALL, activebackground=config.BG_SECTION).pack(side="left", padx=2)

        # Treeview
        tree_frame = tk.Frame(self, bg=config.BG_SECTION)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)
        cols = ("name", "size", "type")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("name", text="Island Name")
        self._tree.heading("size", text="Size")
        self._tree.heading("type", text="Type")
        self._tree.column("name", width=280)
        self._tree.column("size", width=90, anchor="center")
        self._tree.column("type", width=100, anchor="center")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda e: self._confirm())

        self._islands = reg.for_region(self._region)
        self._populate()

        btn_f = tk.Frame(self, bg=config.BG_SECTION)
        btn_f.pack(pady=(4, 12))
        _btn(btn_f, "  Place  ", self._confirm,
             fg=config.BG_MAIN, bg=config.FG_GOLD).pack(side="left", padx=8)
        _btn(btn_f, "  Cancel  ", self.destroy).pack(side="left", padx=8)

    def _populate(self, *_):
        self._tree.delete(*self._tree.get_children())
        flt  = self._filter_var.get().lower()
        tfilter = self._type_filter_var.get()
        for isl in self._islands:
            if tfilter == "Continental":
                if isl.size != "Continental":
                    continue
            elif tfilter != "All" and isl.island_type != tfilter:
                continue
            if flt and flt not in isl.name.lower() and flt not in isl.a7m_name.lower():
                continue
            self._tree.insert("", "end", iid=isl.a7m_name, values=(
                isl.name, isl.size,
                config.ISLAND_TYPE_LABELS.get(isl.island_type, isl.island_type)
            ))

    def _confirm(self):
        sel = self._tree.selection()
        if not sel:
            return
        from island_registry import IslandRegistry
        asset = IslandRegistry.instance().find_by_name(sel[0])
        if asset is None:
            return
        from models import IslandElement
        isl = IslandElement(
            size=asset.size,
            island_type=asset.island_type,
            element_type=0,
            map_file_path=asset.file_path,
            island_label=asset.name,
        )
        self.result = isl
        self.destroy()

# ─── About Dialog ────────────────────────────────────────────────────────────

class AboutDialog(_BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "About", width=380, height=250)

    def _build(self):
        tk.Label(self, text="Anno 117 Map Template Editor", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(pady=(24, 6))
        tk.Label(self, text="A community tool for creating & editing\nAnno 117 map templates (.a7tinfo).", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_SMALL, justify="center").pack(pady=6)
        tk.Label(self, text="Requires FileDBReader by anno-mods\nRequires RDAConsole by anno-mods", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(pady=2)
        _sep(self).pack(fill="x", padx=20, pady=12)
        _btn(self, "  Close  ", self.destroy).pack()
