"""
Anno 117 Map Template Editor - Aegyptus (DLC03) tab: canvas + side panel
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional

import config
import egypt_data as ed
from egypt_canvas import EgyptCanvas
from egypt_model import EgyptElement, EgyptTemplate, LAYER_AUTO, LAYER_FULL, LAYER_REDUCED

_LAYER_LABELS = {LAYER_AUTO: "game decides by map size", LAYER_FULL: "always full", LAYER_REDUCED: "always reduced"}


def _load_icon(rel_path: str, size: int):
    try:
        from PIL import Image, ImageTk
        p = config.resource_path(rel_path)
        if not os.path.isfile(p):
            return None
        return ImageTk.PhotoImage(Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS))
    except Exception:
        return None


class EgyptTab(tk.Frame):
    """The Aegyptus tab. Duck-types the parts of RegionTab the main window calls."""

    ICON = "data/ui/fhd/dlc03/icon_content/generic/icon_2d_region_egypt.png"

    def __init__(self, parent, app):
        super().__init__(parent, bg=config.BG_MAIN)
        self.region = ed.REGION
        self.app = app
        self.canvas_widget: Optional[EgyptCanvas] = None
        self._quad_rows: Dict[str, tuple] = {}
        self._build()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build(self):
        side = tk.Frame(self, bg=config.BG_SECTION, width=250)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        self._build_side(side)

        frame = tk.Frame(self, bg=config.BG_MAIN)
        frame.pack(side="left", fill="both", expand=True)
        self.canvas_widget = EgyptCanvas(frame)
        self.canvas_widget.pack(fill="both", expand=True)
        self.canvas_widget.on_select = self._on_select
        self.canvas_widget.on_modify = self._on_modify
        self.canvas_widget.on_edit = self._edit
        self.canvas_widget.on_zoom_change = self._on_zoom_change

    def _btn(self, parent, text, cmd, fg=config.FG_MAIN, bg=config.BG_HOVER, **kw):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, relief=tk.FLAT, font=config.FONT_SMALL,
                      padx=6, pady=3, cursor="hand2", activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, **kw)
        return b

    def _sep(self, side):
        tk.Frame(side, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=8, pady=4)

    def _build_side(self, side: tk.Frame):
        title = tk.Frame(side, bg=config.BG_SECTION)
        title.pack(anchor="w", pady=(14, 2), padx=6)
        self._title_icon = _load_icon(self.ICON, 24)
        if self._title_icon:
            tk.Label(title, image=self._title_icon, bg=config.BG_SECTION).pack(side="left", padx=(0, 4))
        tk.Label(title, text=ed.REGION, bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(side="left")
        self._name_var = tk.StringVar(value="")
        tk.Label(side, textvariable=self._name_var, bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_XSMALL,
                 anchor="w", wraplength=220, justify="left").pack(anchor="w", padx=8)
        self._btn(side, "Load Vanilla Aegyptus Map", self._load_vanilla, fg=config.FG_GOLD).pack(fill="x", padx=8, pady=(4, 0))

        self._sep(side)
        # The selected island's details are shown in the info box on the map (top right).
        self._sel_var = tk.StringVar(value="")
        tk.Label(side, text="Click an island to select, double-click to edit.", bg=config.BG_SECTION,
                 fg=config.FG_DIM, font=config.FONT_XSMALL, wraplength=230, justify="left").pack(anchor="w", padx=8)
        self._edit_btn = self._btn(side, "Edit Island…", self._edit_selected, state="disabled")
        self._edit_btn.pack(fill="x", padx=8)

        self._sep(side)
        tk.Label(side, text="Island Complexes", bg=config.BG_SECTION, fg=config.FG_MAIN,
                 font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=8)
        grid = tk.Frame(side, bg=config.BG_SECTION)
        grid.pack(fill="x", padx=8, pady=(4, 0))
        for i, q in enumerate(ed.QUADRANTS):
            lbl = tk.Label(grid, text=ed.quadrant_label(q), bg=config.BG_SECTION, fg=config.FG_GOLD,
                           font=config.FONT_XSMALL, width=7, anchor="w")
            lbl.grid(row=i, column=0, sticky="w")
            sel = self._btn(grid, "Select", lambda q=q: self.canvas_widget.select_quadrant(q))
            sel.config(font=config.FONT_XSMALL, pady=1)
            sel.grid(row=i, column=1, padx=2, pady=1, sticky="ew")
            tog = self._btn(grid, "Remove", lambda q=q: self._toggle_quadrant(q))
            tog.config(font=config.FONT_XSMALL, pady=1)
            tog.grid(row=i, column=2, padx=2, pady=1, sticky="ew")
            info = tk.Label(grid, text="", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL)
            info.grid(row=i, column=3, sticky="w")
            self._quad_rows[q] = (sel, tog, info)

        chk = dict(bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER,
                   activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD, cursor="hand2")
        self._free_var = tk.BooleanVar(value=False)
        tk.Checkbutton(side, text="Unlock moving / rotating", variable=self._free_var,
                       command=self._on_free_toggle, font=config.FONT_SMALL, fg=config.FG_GOLD,
                       **{k: v for k, v in chk.items() if k != "fg"}).pack(anchor="w", padx=8, pady=(4, 0))
        self._move_var = tk.BooleanVar(value=False)
        self._move_chk = tk.Checkbutton(side, text="Drag whole complexes", variable=self._move_var,
                                        command=self._on_move_toggle, font=config.FONT_XSMALL, **chk)
        self._move_chk.pack(anchor="w", padx=20)
        self._coll_var = tk.BooleanVar(value=False)
        self._coll_chk = tk.Checkbutton(side, text="Ignore collisions", variable=self._coll_var,
                                        command=self._on_coll_toggle, font=config.FONT_XSMALL, **chk)
        self._coll_chk.pack(anchor="w", padx=20)
        self._move_hint = tk.Label(side, text="Experimental. Drag moves an island, Ctrl+drag its complex. "
                                              "Rotate the selected island with . / , or Ctrl+R.",
                                   bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left",
                                   wraplength=205)
        self._move_hint.pack(anchor="w", padx=24)
        self._set_free_widgets(False)

        self._sep(side)
        self._summary_var = tk.StringVar(value="")
        tk.Label(side, textvariable=self._summary_var, bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL,
                 justify="left", wraplength=230, anchor="w").pack(anchor="w", padx=8)
        self._warn_var = tk.StringVar(value="")
        tk.Label(side, textvariable=self._warn_var, bg=config.BG_SECTION, fg="#e74c3c", font=config.FONT_XSMALL,
                 justify="left", wraplength=230, anchor="w").pack(anchor="w", padx=8, pady=(4, 0))

        self._sep(side)
        tk.Label(side, text="View", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=8)
        self._img_var = tk.BooleanVar(value=True)
        tk.Checkbutton(side, text="Show island images", variable=self._img_var, command=self._on_image_toggle,
                       bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER,
                       activebackground=config.BG_HOVER, activeforeground=config.FG_GOLD,
                       font=config.FONT_SMALL, cursor="hand2").pack(anchor="w", padx=8)
        self._reset_zoom_btn = self._btn(side, "Reset Zoom", lambda: self.canvas_widget.reset_zoom())
        self._reset_zoom_btn.pack(anchor="w", padx=8, pady=(4, 6))
        self._update_panel()

    # ── actions ──────────────────────────────────────────────────────────────

    def _load_vanilla(self):
        tmpl = self.get_template()
        if tmpl is not None and tmpl.modified and not messagebox.askyesno(
                "Replace Aegyptus Map", "Replace the current Aegyptus map with the vanilla layout?", parent=self):
            return
        try:
            self.load_template(EgyptTemplate.vanilla())
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc), parent=self)
            return
        self.set_template_name("egypt_province_default_01 (vanilla)")
        self.app.set_status("Vanilla Aegyptus map loaded.")

    def _toggle_quadrant(self, q: str):
        tmpl = self.get_template()
        if tmpl is None:
            return
        if q in tmpl.removed:
            self.canvas_widget.restore_quadrant(q)
        else:
            self.canvas_widget.select_quadrant(q)
            self.canvas_widget.delete_selected()

    def _set_free_widgets(self, on: bool):
        state = "normal" if on else "disabled"
        self._move_chk.config(state=state)
        self._coll_chk.config(state=state)
        self._move_hint.config(fg=config.FG_DIM if on else config.BG_HOVER)

    def _on_free_toggle(self):
        if self._free_var.get():
            ok = messagebox.askyesno(
                "Unlock Moving and Rotating - Experimental",
                "The Aegyptus map is one seamless landscape. Its islands are cut from it along straight "
                "borders that run across land, not along the coast, and every island touches its neighbours.\n\n"
                "Moving or rotating an island or a whole complex therefore cuts the land apart in the game: "
                "straight cliffs and gaps where it was, overlaps and seams where it lands, rivers that end "
                "abruptly, and NPCs, trade routes or the start position may end up unusable.\n\n"
                "The result can make the map ugly or unplayable. Keep a saved copy and test every change "
                "in the game before publishing a mod.\n\n"
                "I understand the risks - unlock moving and rotating?",
                icon="warning", parent=self)
            if not ok:
                self._free_var.set(False)
        on = self._free_var.get()
        self.canvas_widget.free_edit = on
        if not on:
            self._move_var.set(False)
            self._coll_var.set(False)
            self.canvas_widget.move_complexes = False
            self.canvas_widget.ignore_collisions = False
        self._set_free_widgets(on)
        self.canvas_widget.redraw()

    def _on_move_toggle(self):
        self.canvas_widget.move_complexes = self._move_var.get()
        self.canvas_widget.redraw()

    def _on_coll_toggle(self):
        self.canvas_widget.ignore_collisions = self._coll_var.get()

    def _on_image_toggle(self):
        self.canvas_widget.show_images = self._img_var.get()
        self.canvas_widget.invalidate()

    def _on_zoom_change(self, scale: float):
        pass

    def _edit_selected(self):
        e = self.canvas_widget.get_selected()
        if e and not e.is_spawn:
            self._edit(e)

    def _edit(self, e: EgyptElement):
        from egypt_dialogs import EgyptIslandDialog
        dlg = EgyptIslandDialog(self.winfo_toplevel(), e)
        if not dlg.result:
            return
        r = dlg.result
        changed = (r["fertilities"] != e.fertility_guids or r["difficulty"] != e.difficulty
                   or r["layer_mode"] != e.layer_mode)
        if not changed:
            return
        self.canvas_widget.push_undo()
        e.set_fertilities(r["fertilities"])
        if e.is_fertile:
            e.difficulty = r["difficulty"]
        recompose = r["layer_mode"] != e.layer_mode
        e.set_layer_mode(r["layer_mode"])
        self.get_template().modified = True
        self.canvas_widget._changed(recompose=recompose)
        self._on_select(e, e.quadrant)

    # ── callbacks ────────────────────────────────────────────────────────────

    def _on_select(self, e: Optional[EgyptElement], q: Optional[str]):
        lines = []
        if e is not None and e.is_spawn:
            lines = ["⚓  Ship spawn", f"Pos: {e.position}"]
            self._sel_var.set("Ship spawn - drag it to move.")
            self._edit_btn.config(state="disabled")
        elif e is not None:
            role = "★ Starter" if e.is_starter else e.kind
            fert = ", ".join(self._fert_name(g) for g in e.fertility_guids) or "random"
            text = (f"{e.short}  ·  {role}\n{ed.quadrant_label(e.quadrant)} complex\n"
                    f"Fertility group: {e.difficulty}\nFertilities: {fert}")
            if e.has_layer:
                text += f"\nVariant: {_LAYER_LABELS[e.layer_mode]}"
            if e.rotation:
                text += f"\nRotation: {config.ROTATION_LABELS[e.rotation]}"
            self._sel_var.set(text)
            lines = text.split("\n")
            self._edit_btn.config(state="normal")
        elif q is not None:
            tmpl = self.get_template()
            n = len(tmpl.quadrant_elements(q)) if tmpl else 0
            off = tmpl.quadrant_offset(q) if tmpl else (0, 0)
            moved = "islands edited one by one" if off is None else f"moved by ({off[0]}, {off[1]})"
            self._sel_var.set(f"{ed.quadrant_label(q)} complex: {n} islands\n{moved.capitalize()}\n"
                              "Delete key removes it.")
            lines = [f"{ed.quadrant_label(q)} complex", f"{n} islands, {moved}"]
            self._edit_btn.config(state="disabled")
        else:
            self._sel_var.set("Click an island. Double-click to edit.")
            self._edit_btn.config(state="disabled")
        self.canvas_widget.set_selection_overlay(lines)

    @staticmethod
    def _fert_name(guid: int) -> str:
        f = ed.fertility_data().fertilities.get(guid)
        if f:
            return f.display_name
        from fertility_registry import FertilityRegistry
        fa = FertilityRegistry.instance().find_by_guid(guid)
        return fa.display_name if fa else str(guid)

    def _on_modify(self):
        self._update_panel()
        self.app.mark_modified()

    def _update_panel(self):
        tmpl = self.get_template()
        for q, (sel, tog, info) in self._quad_rows.items():
            if tmpl is None:
                for w in (sel, tog):
                    w.config(state="disabled")
                info.config(text="")
                continue
            removed = q in tmpl.removed
            sel.config(state="disabled" if removed else "normal")
            tog.config(state="normal", text="Restore" if removed else "Remove",
                       fg=config.FG_GOLD if removed else "#e74c3c")
            off = tmpl.quadrant_offset(q)
            if removed:
                info.config(text="removed")
            elif off is None:
                info.config(text="edited")
            else:
                info.config(text=f"moved {off[0]},{off[1]}" if (off[0] or off[1]) else "")
        if tmpl is None:
            self._summary_var.set("")
            self._warn_var.set("")
            if self.canvas_widget:
                self.canvas_widget.set_warnings([])
            return
        fert = [e for e in tmpl.islands if e.fertility_guids]
        fixed = [e for e in tmpl.islands if e.can_auto_reduce and e.layer_mode != LAYER_AUTO]
        self._summary_var.set(
            f"{len(tmpl.islands)} islands · {sum(1 for e in tmpl.islands if e.is_starter)} starters · "
            f"custom fertilities: {len(fert)}\n"
            f"Fixed island variants: {len(fixed)} of {sum(1 for e in tmpl.islands if e.can_auto_reduce)}")
        warnings = tmpl.warnings()
        self._warn_var.set(f"⚠ {len(warnings)} warning(s), see map" if warnings else "")
        self.canvas_widget.set_warnings(warnings)

    # ── RegionTab-compatible API ─────────────────────────────────────────────

    def load_template(self, tmpl: Optional[EgyptTemplate]):
        self.canvas_widget.set_template(tmpl)
        self._on_select(None, None)
        self._update_panel()

    def get_template(self) -> Optional[EgyptTemplate]:
        return self.canvas_widget.template if self.canvas_widget else None

    def set_template_name(self, name: str) -> None:
        self._name_var.set(name.replace("_", " "))

    def set_difficulty(self, _difficulty: str) -> None:
        pass

    def _delete_selected(self):
        self.canvas_widget.delete_selected()
