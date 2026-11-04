"""
Anno 117 Map Template Editor - Aegyptus (DLC03) dialogs
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import tkinter as tk
from typing import Dict, List, Optional

import config
import egypt_data as ed
from dialogs import _BaseDialog, _sep, _btn
from egypt_model import EgyptElement, LAYER_AUTO, LAYER_FULL, LAYER_REDUCED

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class EgyptIslandDialog(_BaseDialog):
    """
    Edit one Aegyptus island: fertilities (random or a fixed list), difficulty group and island variant.
    After closing, ``result`` is a dict {fertilities, difficulty, layer_mode} or None when cancelled.
    """

    def __init__(self, parent, element: EgyptElement):
        self._e = element
        super().__init__(parent, f"Aegyptus Island - {element.short}", width=520, height=None)

    def _build(self):
        e = self._e
        tk.Label(self, text=e.short.replace("_", " ").title(), bg=config.BG_SECTION, fg=config.FG_GOLD,
                 font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 0))
        role = "Starter island" if e.is_starter else {"Village": "NPC village", "Trader": "Trader",
                                                        "Project": "Sector project", "Pirate": "Pirate",
                                                        "Decoration": "Decoration"}.get(e.kind, f"{e.kind} island")
        tk.Label(self, text=f"{role}  ·  {ed.quadrant_label(e.quadrant or '')} complex  ·  {e.stem}",
                 bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=16)
        _sep(self).pack(fill="x", padx=10, pady=6)

        body = tk.Frame(self, bg=config.BG_SECTION)
        body.pack(fill="x", padx=16)

        # ── Difficulty (only meaningful where the game rolls a FertilitySet) ─────
        self._diff_var = tk.StringVar(value=e.difficulty)
        if e.is_fertile:
            row = tk.Frame(body, bg=config.BG_SECTION)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="Fertility group", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL,
                     width=16, anchor="w").pack(side="left")
            for label, val in (("Normal (with gold)", "Normal"), ("Hard (no gold)", "Hard")):
                tk.Radiobutton(row, text=label, variable=self._diff_var, value=val, bg=config.BG_SECTION,
                               fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION,
                               activeforeground=config.FG_GOLD, font=config.FONT_XSMALL).pack(side="left", padx=(0, 8))
            tk.Label(body, text="Decides which Egyptian FertilitySet the game rolls when fertilities are random.",
                     bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", pady=(0, 4))

        # ── Island variant ────────────────────────────────────────────────────
        self._layer_var = tk.StringVar(value=e.layer_mode)
        if e.has_layer:
            tk.Label(body, text="Island variant", bg=config.BG_SECTION, fg=config.FG_DIM,
                     font=config.FONT_SMALL).pack(anchor="w", pady=(4, 0))
            opts = []
            if e.can_auto_reduce:
                opts.append(("Game decides by map size (vanilla)", LAYER_AUTO))
            opts += [("Always the full island", LAYER_FULL), ("Always the reduced island (_layer01)", LAYER_REDUCED)]
            for label, val in opts:
                tk.Radiobutton(body, text=label, variable=self._layer_var, value=val, bg=config.BG_SECTION,
                               fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION,
                               activeforeground=config.FG_GOLD, font=config.FONT_XSMALL).pack(anchor="w", padx=12)

        # ── Fertilities ───────────────────────────────────────────────────────
        _sep(self).pack(fill="x", padx=10, pady=6)
        fbody = tk.Frame(self, bg=config.BG_SECTION)
        fbody.pack(fill="x", padx=16)
        self._rand_var = tk.BooleanVar(value=not e.fertility_guids)
        tk.Checkbutton(fbody, text="Random fertilities (the game rolls the island's FertilitySet)",
                       variable=self._rand_var, command=self._on_rand_toggle, bg=config.BG_SECTION,
                       fg=config.FG_MAIN, selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION,
                       activeforeground=config.FG_GOLD, font=config.FONT_SMALL).pack(anchor="w")
        tk.Label(fbody, text="Unticked: exactly the fertilities ticked below, in this order (click order).",
                 bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", pady=(0, 4))

        # Only the fertilities the Egyptian sets use: the others have no Aegyptus localisation and no production there.
        ferts = list(ed.fertility_data().fertilities.values())
        allowed = {f.guid for f in ferts}
        self._order: List[int] = [g for g in e.fertility_guids if g in allowed]
        self._vars: Dict[int, tk.BooleanVar] = {}
        self._icons: list = []
        self._checks: list = []
        grid = tk.Frame(fbody, bg=config.BG_SECTION)
        grid.pack(fill="x")
        for i, f in enumerate(ferts):
            v = tk.BooleanVar(value=f.guid in self._order)
            self._vars[f.guid] = v
            ic = self._icon(f.icon_path)
            cb = tk.Checkbutton(grid, text=f" {f.display_name}", image=ic, compound="left", variable=v,
                                command=lambda g=f.guid: self._on_check(g), bg=config.BG_SECTION, fg=config.FG_MAIN,
                                selectcolor=config.BG_HOVER, activebackground=config.BG_SECTION,
                                activeforeground=config.FG_GOLD, font=config.FONT_XSMALL, anchor="w")
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=2, pady=1)
            self._checks.append(cb)
        self._order_var = tk.StringVar()
        tk.Label(fbody, textvariable=self._order_var, bg=config.BG_SECTION, fg=config.FG_GOLD,
                 font=config.FONT_XSMALL, wraplength=480, justify="left").pack(anchor="w", pady=(4, 0))
        self._on_rand_toggle()
        self._update_order()

        # ── Buttons ──────────────────────────────────────────────────────────
        _sep(self).pack(fill="x", padx=10, pady=8)
        btns = tk.Frame(self, bg=config.BG_SECTION)
        btns.pack(pady=(0, 14))
        _btn(btns, "Cancel", self.destroy).pack(side="left", padx=6)
        _btn(btns, "Apply", self._ok, fg=config.FG_GOLD).pack(side="left", padx=6)

    def _icon(self, path: str):
        if not PIL_AVAILABLE or not os.path.isfile(path):
            return None
        try:
            ic = ImageTk.PhotoImage(Image.open(path).convert("RGBA").resize((22, 22), Image.LANCZOS))
        except Exception:
            return None
        self._icons.append(ic)
        return ic

    def _on_rand_toggle(self):
        state = "disabled" if self._rand_var.get() else "normal"
        for cb in self._checks:
            cb.config(state=state)
        self._update_order()

    def _on_check(self, guid: int):
        if self._vars[guid].get():
            if guid not in self._order:
                self._order.append(guid)
        elif guid in self._order:
            self._order.remove(guid)
        self._update_order()

    def _update_order(self):
        if self._rand_var.get():
            self._order_var.set("")
            return
        names = []
        data = ed.fertility_data().fertilities
        for g in self._order:
            f = data.get(g)
            names.append(f.display_name if f else str(g))
        self._order_var.set(("Order: " + ", ".join(names)) if names else "No fertility ticked - the island will get none.")

    def _ok(self):
        fert = [] if self._rand_var.get() else list(self._order)
        if not self._rand_var.get() and not fert:
            from tkinter import messagebox
            if not messagebox.askyesno("No Fertilities",
                                       "No fertility is ticked. Leaving it like this keeps the island random.\n\n"
                                       "Continue?", parent=self):
                return
        self.result = {"fertilities": fert, "difficulty": self._diff_var.get(), "layer_mode": self._layer_var.get()}
        self.destroy()
