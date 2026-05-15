"""
Anno 117 Map Template Editor - Map Template Import Dialog
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List, Callable

import config
import rda_handler


# Map template metadata parsed from filename
class TemplateEntry:
    def __init__(self, path: str):
        self.path = path
        self.basename = os.path.basename(path).replace(".a7tinfo", "")
        self.enlarged = False
        self.valid = False

        path_norm = path.replace("\\", "/").lower()
        if "/campaign/" in path_norm:
            self.category = "Campaign"
        elif "/events/" in path_norm:
            self.category = "Event"
        else:
            self.category = "Pool"

        # Templates located under a dlc01 folder are DLC-expanded by definition, regardless of whether the filename carries the _dlc01expanded suffix.
        # This covers cases like Rift enlarged templates that may omit the suffix.
        _in_dlc01_dir = "/dlc01/" in path_norm

        # Pattern 1: pool templates
        # roman_province_{type}_{num}_{difficulty}[_dlc01expanded]
        m = re.match(
            r"(roman|celtic)_province_(chain|corners|default|donut|rift)"
            r"_(\d+)_(easy|medium|hard)(_dlc01expanded)?",
            self.basename
        )
        if m:
            self.culture  = m.group(1)
            self.ptype    = m.group(2)
            self.num      = m.group(3)
            self.diff     = m.group(4)
            self.enlarged = (m.group(5) is not None) or _in_dlc01_dir
            self.region   = "Albion" if self.culture == "celtic" else "Latium"
            self.valid    = True
            return

        # Pattern 2: campaign/event/any non-pool templates - with optional _dlc01expanded suffix
        m2 = re.match(
            r"(roman|celtic)_province_(.+?)_(\d+)(_dlc01expanded)?$",
            self.basename
        )
        if m2:
            self.culture  = m2.group(1)
            self.ptype    = m2.group(2)   # e.g. "campaign", "gamescom25"
            self.num      = m2.group(3)
            self.diff     = "-"
            self.enlarged = (m2.group(4) is not None) or _in_dlc01_dir
            self.region   = "Albion" if self.culture == "celtic" else "Latium"
            self.valid    = True

    @property
    def display_name(self) -> str:
        suffix = " [DLC expanded]" if self.enlarged else ""
        return f"{self.ptype.capitalize()} {self.num}{suffix}"


class ImportDialog(tk.Toplevel):
    """
    Shows all available map templates grouped by type/difficulty.
    User picks one entry; both regions load automatically.
    """

    def __init__(self, parent, game_path: str, extracted_root: str, rda_exe: Optional[str], on_import: Callable[[str, bool], None], on_extracted: Optional[Callable] = None):
        super().__init__(parent)
        self.title("Import Map Template")
        self.configure(bg=config.BG_SECTION)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - 900) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 700) // 2
        self.geometry(f"900x700+{max(0, px)}+{max(0, py)}")

        self._game_path = game_path
        self._extracted_root = extracted_root
        self._rda_exe = rda_exe
        self._on_import = on_import  # callback(path: str, want_enlarged: bool)
        self._on_extracted = on_extracted  # optional callback fired after successful RDA extraction
        self._entries: List[TemplateEntry] = []

        self._build()
        self._scan_or_prompt()
        self.wait_window(self)

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self):
        # Title
        tk.Label(self, text="Select Map Template to Import", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Frame(self, height=1, bg=config.FG_SEPARATOR).pack(fill="x", padx=10, pady=4)

        # Filter bar
        fbar = tk.Frame(self, bg=config.BG_SECTION)
        fbar.pack(fill="x", padx=12, pady=(4, 0))

        tk.Label(fbar, text="Filter:", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL).pack(side="left")
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._populate())
        tk.Entry(fbar, textvariable=self._filter_var, bg=config.BG_HOVER, fg=config.FG_MAIN, insertbackground=config.FG_MAIN, relief=tk.FLAT, font=config.FONT_SMALL, width=20).pack(side="left", padx=6)

        # Region filter
        self._region_var = tk.StringVar(value="All")
        for label in ("All", "Latium", "Albion"):
            tk.Radiobutton(fbar, text=label, variable=self._region_var, value=label, command=self._populate, bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, font=config.FONT_SMALL, activebackground=config.BG_SECTION).pack(side="left", padx=4)

        tk.Label(fbar, text="|", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BODY).pack(side="left", padx=(8, 8))

        # Category / special filters
        self._cat_var = tk.StringVar(value="All")
        for label in ("All", "Pool", "Campaign", "DLC01"):
            tk.Radiobutton(fbar, text=label, variable=self._cat_var, value=label, command=self._populate, bg=config.BG_SECTION, fg=config.FG_MAIN, selectcolor=config.BG_HOVER, font=config.FONT_SMALL, activebackground=config.BG_SECTION).pack(side="left", padx=4)

        # Treeview
        tree_frame = tk.Frame(self, bg=config.BG_SECTION)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=8)

        cols = ("region", "category", "type", "difficulty", "enlarged")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("category", text="Category")
        self._tree.column("category", width=90, anchor="center")
        self._tree.heading("region", text="Region")
        self._tree.heading("type", text="Type")
        self._tree.heading("difficulty", text="Difficulty")
        self._tree.heading("enlarged", text="DLC Expanded")
        self._tree.column("region", width=90,  anchor="center")
        self._tree.column("type", width=120, anchor="center")
        self._tree.column("difficulty", width=100, anchor="center")
        self._tree.column("enlarged", width=110, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda e: self._do_import())

        # Status label
        self._status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status_var, bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=14)

        # Buttons
        btn_f = tk.Frame(self, bg=config.BG_SECTION)
        btn_f.pack(pady=(4, 12))

        self._extract_btn = tk.Button(btn_f, text="⟳  Extract from RDA (first time / after update)", command=self._start_extract, bg=config.BG_HOVER, fg=config.FG_MAIN, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_SMALL, padx=10, pady=4)
        self._extract_btn.pack(side="left", padx=6)

        tk.Button(btn_f, text="  Import Selected  ", command=self._do_import, bg=config.FG_GOLD, fg=config.BG_MAIN, relief=tk.FLAT, font=config.FONT_BOLD_SMALL, padx=10, pady=4).pack(side="left", padx=6)

        tk.Button(btn_f, text="Cancel", command=self.destroy, bg=config.BG_HOVER, fg=config.FG_DIM, relief=tk.FLAT, font=config.FONT_SMALL, padx=10, pady=4).pack(side="left", padx=6)

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _scan_or_prompt(self):
        files = rda_handler.scan_extracted_templates(self._extracted_root)
        if files:
            self._load_entries(files)
        else:
            # First time - show explanation and prompt
            self._status_var.set(
                "Game files not yet extracted. "
                "Click '⟳ Extract from RDA' to unpack map templates from the game archives.\n"
                "This only needs to be done once and takes about 30–60 seconds."
            )
            # Show a non-blocking info banner inside the dialog
            banner = tk.Frame(self, bg="#1a3050", padx=10, pady=8)
            banner.pack(fill="x", padx=12, pady=(0, 4))
            tk.Label(banner, text="! First-time setup required", bg="#1a3050", fg=config.FG_GOLD, font=config.FONT_BOLD_SMALL).pack(anchor="w")
            tk.Label(
                banner,
                text=(
                    "Map template files need to be extracted from the game's .rda archives once.\n"
                    "Make sure the game path and RdaConsole path are set in the Edit menu,\n"
                    "then click '⟳ Extract from RDA' below."
                ),
                bg="#1a3050", fg=config.FG_MAIN, font=config.FONT_XSMALL, justify="left").pack(anchor="w")

    def _load_entries(self, files: List[str]):
        self._entries = [e for f in files
                         for e in (TemplateEntry(f),)
                         if e.valid and e.category != "Event"]
        self._populate()
        self._status_var.set(f"{len(self._entries)} templates found.")

    def _populate(self, *_):
        self._tree.delete(*self._tree.get_children())
        flt    = self._filter_var.get().lower()
        region = self._region_var.get()
        cat = self._cat_var.get()

        for e in sorted(self._entries, key=lambda x: (x.ptype, x.diff, x.region)):
            if region != "All" and e.region != region:
                continue
            if flt and flt not in e.display_name.lower() and flt not in e.diff:
                continue
            if cat == "DLC01":
                if not e.enlarged:
                    continue
            elif cat != "All" and e.category != cat:
                continue
            self._tree.insert("", "end", iid=e.path, values=(
                e.region,
                e.category,
                e.ptype.capitalize(),
                e.diff.capitalize(),
                "Yes" if e.enlarged else "No",
            ))

    # ── Extraction ────────────────────────────────────────────────────────────

    def _start_extract(self):
        if not self._game_path or not os.path.isdir(self._game_path):
            messagebox.showerror("No Game Path", "Please set the game installation path first.", parent=self)
            return

        self._extract_btn.config(state="disabled")

        # Replace status label with a progress bar
        self._progress_var = tk.IntVar(value=0)
        self._progress_bar = ttk.Progressbar(
            self, mode="indeterminate", length=300
        )
        self._progress_bar.pack(pady=(2, 0))
        self._progress_bar.start(12)
        self._status_var.set("Extracting from RDA archives - please wait…")

        def _worker():
            try:
                files = rda_handler.extract_map_templates(
                    self._game_path, self._extracted_root,
                    self._rda_exe, force=True
                )
                self.after(0, lambda f=files: self._on_extract_done(f))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: self._on_extract_error(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_extract_done(self, files: List[str]):
        self._progress_bar.stop()
        self._progress_bar.destroy()
        self._extract_btn.config(state="normal")
        self._load_entries(files)
        self._status_var.set(f"Extraction complete - {len(self._entries)} templates found.")
        if self._on_extracted:
            self._on_extracted()

    def _on_extract_error(self, msg: str):
        self._progress_bar.stop()
        self._progress_bar.destroy()
        self._extract_btn.config(state="normal")
        self._status_var.set("Extraction failed.")
        messagebox.showerror("Extraction Failed", msg, parent=self)

    # ── Import ────────────────────────────────────────────────────────────────

    def _do_import(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a map template first.", parent=self)
            return
        path = sel[0]
        entry = next((e for e in self._entries if e.path == path), None)
        if entry is None:
            return

        want_enlarged = False
        if entry.region == "Albion":
            want_enlarged = messagebox.askyesno("Latium Counterpart",
                "Also import the enlarged (DLC) Latium template?\n\n"
                "Yes = enlarged (dlc01expanded)\nNo = standard",
                parent=self
            )

        self._on_import(path, want_enlarged)
        self.destroy()