"""
Anno 117 Map Template Editor — Mod Exporter

Packages the current map templates (Latium and/or Albion) into a complete,
playable mod zip file following the [Map] $ModName (TAMPER) folder structure.

Usage:
    dlg = ModExportDialog(parent_window, app_window)
    parent.wait_window(dlg)
    # dlg._result is (slug, description, start_guid, zip_path) or None
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import re
import shutil
import tempfile
import webbrowser
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox
from copy import deepcopy
from typing import Callable, List, Optional, Tuple

import config
import filedb_handler as _fdb
import settings as _settings
import terrain_builder
from fertility_set_registry import FertilitySetRegistry

# ─── Personal GUID range ─────────────────────────────────────────────────────
# Safe range reserved for personal/testing use only; never claim a block from
# a published range when exporting in personal mode.
_PERSONAL_GUID_MIN = 2001001000
_PERSONAL_GUID_MAX = 2001009999
_PERSONAL_GUID_STEP = 7   # six consecutive GUIDs claimed per export + 1 gap


# ─── Template folder paths ────────────────────────────────────────────────────

# Standard (non-enlarged) template folder
_TEMPLATE_DIR = config.resource_path("[Map] $ModName (TAMPER)")
# Enlarged (DLC01) template folder
_TEMPLATE_DIR_ENL = config.resource_path("[Map] $ModName Enlarged (TAMPER)")

# Province/suffix per region
_REGION_INFO = {
    "Latium": {"province": "roman",  "suffix": "latium"},
    "Albion": {"province": "celtic", "suffix": "albion"},
}


def _a7t_src(template_dir: str, region: str, suffix: str) -> str:
    prov = _REGION_INFO[region]["province"]
    name = f"$ModName_{suffix}_easy"
    return os.path.join(template_dir, "data", "tamper", "provinces", prov, "templates", "pool", name, name + ".a7t")


_LOCALE_FILES = [
    "texts_brazilian.xml",
    "texts_english.xml",
    "texts_french.xml",
    "texts_german.xml",
    "texts_italian.xml",
    "texts_japanese.xml",
    "texts_korean.xml",
    "texts_polish.xml",
    "texts_russian.xml",
    "texts_simplified_chinese.xml",
    "texts_spanish.xml",
    "texts_traditional_chinese.xml",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """
    Create a file/ID-safe slug from a mod name. Lowercased; spaces become hyphens; only alphanumerics, underscores, and hyphens are kept.
    """
    slug = name.strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^\w\-]", "", slug)
    slug = slug.replace("_", "-")  # underscores not permitted in mod names
    return slug


def _to_display_name(slug: str) -> str:
    """
    Convert a slug to a human-readable display name.
    Underscores and hyphens become spaces; result is title-cased.
    Used for the mod folder name, zip filename, and all GUI text fields.
    """
    return re.sub(r"[_\-]+", " ", slug).strip().title()


def _substitute(text: str, slug: str, display_name: str, description: str, start_guid: int) -> str:
    """
    Perform all template variable substitutions in a file's text content.

    Substitution order matters:
      1. "$ModName_" → "{slug}_" (file-path prefix)
      2. "tamper-enlargedmap-$ModName"→ "tamper-enlargedmap-{slug}" (enlarged ModID)
      3. "tamper-map-$ModName" → "tamper-map-{slug}" (standard ModID)
      4. "$ModName" → display_name (display contexts)
      5. "$Description" → description
      6. "Start_GUID+N" → str(start_guid + N) (highest N first)
      7. "Start_GUID" → str(start_guid)
    """
    text = text.replace("$ModName_", slug + "_")
    text = text.replace("tamper-enlargedmap-$ModName", f"tamper-enlargedmap-{slug}")
    text = text.replace("tamper-map-$ModName", f"tamper-map-{slug}")
    text = text.replace("$ModName", display_name)
    text = text.replace("$Description", description)
    for i in range(6, 0, -1):
        text = text.replace(f"Start_GUID+{i}", str(start_guid + i))
    text = text.replace("Start_GUID", str(start_guid))
    return text


class _TerrainCache:
    """
    Supplies the .a7t / .a7te that go next to each .a7tinfo.

    Both files encode the map size themselves, so they cannot simply be copied
    from the bundled template once a map deviates from its 2048 / 2688 size -
    doing that leaves the world (and with it the backdrop) at the template's
    size while islands are placed beyond it.  They are generated per size here.

    A .a7t is identical for all three difficulties, so results are cached per
    (region, size, playable area) for the duration of one export.
    """

    def __init__(self, template_dir: str,
                 progress: Optional[Callable[[str], None]] = None):
        self._template_dir = template_dir
        self._progress = progress
        self._cache: dict = {}
        # Pool folder stem -> terrain size, for scaling assets.xml HorizonIslands.
        self.size_by_stem: dict = {}

    def write(self, dst_dir: str, stem: str, region: str, suffix: str,
              size: int, playable_area: Tuple[int, int, int, int]) -> None:
        terrain_size = terrain_builder.terrain_size_for(size)
        self.size_by_stem[stem] = terrain_size
        key = (region, terrain_size, tuple(playable_area))

        if key not in self._cache:
            if self._progress:
                self._progress(f"Building {region} terrain ({terrain_size}x{terrain_size})...")
            self._cache[key] = (
                terrain_builder.build_a7t(
                    _a7t_src(self._template_dir, region, suffix),
                    terrain_size, tuple(playable_area),
                    progress=self._progress),
                terrain_builder.build_a7te(terrain_size),
            )
        a7t, a7te = self._cache[key]

        with open(os.path.join(dst_dir, stem + ".a7t"), "wb") as f:
            f.write(a7t)
        with open(os.path.join(dst_dir, stem + ".a7te"), "w",
                  encoding="utf-8", newline="") as f:
            f.write(a7te)


def _make_initial_copy(tmpl):
    """
    Return the base-game (non-DLC) copy of an enlarged MapTemplate.

    Locked=True marks base-game content; Locked=False marks DLC additions.
    The regular (non-_enlarged) a7tinfo contains only locked elements, uses computed_initial_pa as its playable boundary (derived fresh from playable_area and ENL_PA_EXPANSION — never the stored initial_playable_area field which may be stale), and has is_enlarged=False.
    The _enlarged a7tinfo is a straight deepcopy (all elements, full PlayableArea).
    """
    copy = deepcopy(tmpl)
    ipa = tmpl.computed_initial_pa # (x1, y1, x2, y2) — always derived fresh
    copy.playable_area = ipa
    copy.is_enlarged   = False
    # Include locked islands (base-game content) AND spawn points.
    # Spawn points are not tagged Locked but must appear in the non-enlarged file.
    copy.elements = [e for e in tmpl.elements if e.locked or e.is_ship_spawn]

    # Size for the non-enlarged file: span each axis from 0 to the far PA edge, symmetric around the map centre → far edge + near border. Use the larger of x/y for each side so the result is a square.
    raw_s = max(ipa[2], ipa[3]) + max(ipa[0], ipa[1])
    # Round up to the next multiple of 8 (game requirement)
    new_s = raw_s if raw_s % 8 == 0 else (raw_s // 8 + 1) * 8
    copy.size = (new_s, new_s)

    return copy


# ─── Difficulty derivation ────────────────────────────────────────────────────

def _apply_conversion(islands, from_diff: str, to_diff: str) -> None:
    """
    In-place size conversion for a list of random (non-fixed, non-spawn) islands.

    Normal islands follow the full scaling ladder.
    Starter islands follow the same "all XL/L" rules but never drop below Large
    (L is the minimum valid Starter size; M/S Starters do not exist).

    Easy  → Medium : Normal: XL unchanged · every 2nd L→M · every 4th M→S · S unchanged
                     Starter: no change (XL stays XL; L is the minimum)
    Medium → Hard  : Normal: all XL→L · every 2nd L→M · every 2nd M→S · S unchanged
                     Starter: XL→L (minimum reached, L stays L)
    Hard  → Medium : Normal: all L→XL · every 2nd M→L · every 2nd S→M · rest unchanged
                     Starter: L→XL (all; no M/S Starters exist)
    Medium → Easy  : Normal: every 2nd M→L · every 4th S→M · rest unchanged
                     Starter: no change (no M/S Starters; L/XL kept as-is)
    """
    normal   = [e for e in islands if e.island_type == "Normal"]
    starters = [e for e in islands if e.island_type == "Starter"]

    if from_diff == "easy" and to_diff == "medium":
        # Normal: every 2nd L→M, every 4th M→S
        l_n = m_n = 0
        for e in normal:
            if e.size == "Large":
                l_n += 1
                if l_n % 2 == 0:
                    e.size = "Medium"
            elif e.size == "Medium":
                m_n += 1
                if m_n % 4 == 0:
                    e.size = "Small"
        # Starters: no change

    elif from_diff == "medium" and to_diff == "hard":
        # Normal: all XL→L, then every 2nd L→M, every 2nd M→S
        for e in normal:
            if e.size == "ExtraLarge":
                e.size = "Large"
        l_n = m_n = 0
        for e in normal:
            if e.size == "Large":
                l_n += 1
                if l_n % 2 == 0:
                    e.size = "Medium"
            elif e.size == "Medium":
                m_n += 1
                if m_n % 2 == 0:
                    e.size = "Small"
        # Starters: XL→L (minimum); L stays L
        for e in starters:
            if e.size == "ExtraLarge":
                e.size = "Large"

    elif from_diff == "hard" and to_diff == "medium":
        # Normal: all L→XL, then every 2nd M→L, every 2nd S→M
        for e in normal:
            if e.size == "Large":
                e.size = "ExtraLarge"
        m_n = s_n = 0
        for e in normal:
            if e.size == "Medium":
                m_n += 1
                if m_n % 2 == 0:
                    e.size = "Large"
            elif e.size == "Small":
                s_n += 1
                if s_n % 2 == 0:
                    e.size = "Medium"
        # Starters: L→XL (all; no M/S Starters exist)
        for e in starters:
            if e.size == "Large":
                e.size = "ExtraLarge"

    elif from_diff == "medium" and to_diff == "easy":
        # Normal: every 2nd M→L, every 4th S→M
        m_n = s_n = 0
        for e in normal:
            if e.size == "Medium":
                m_n += 1
                if m_n % 2 == 0:
                    e.size = "Large"
            elif e.size == "Small":
                s_n += 1
                if s_n % 4 == 0:
                    e.size = "Medium"
        # Starters: no change (no M/S Starters; L/XL kept as-is)


def _derive_template(source_tmpl, source_diff: str, target_diff: str):
    """
    Return a deep copy of *source_tmpl* whose Normal and Starter random island sizes have been adjusted to match *target_diff*. Easy↔Hard is a two-step chain via Medium.
    """
    _CHAIN: dict = {
        ("easy",   "medium"): [("easy",   "medium")],
        ("medium", "hard"):   [("medium", "hard")],
        ("hard",   "medium"): [("hard",   "medium")],
        ("medium", "easy"):   [("medium", "easy")],
        ("easy",   "hard"):   [("easy",   "medium"), ("medium", "hard")],
        ("hard",   "easy"):   [("hard",   "medium"), ("medium", "easy")],
    }
    steps = _CHAIN.get((source_diff, target_diff), [])
    result = deepcopy(source_tmpl)
    islands = [e for e in result.elements if not e.is_fixed and not e.is_ship_spawn]
    for frm, to in steps:
        _apply_conversion(islands, frm, to)
    result.difficulty = target_diff
    result.difficulty_asked = True
    return result


# ─── Build ────────────────────────────────────────────────────────────────────

def build_mod_zip(
    templates,                           # list[MapTemplate]  (Latium and/or Albion)
    slug: str,                           # file/ID-safe internal name (lowercase, _/-)
    display_name: str,                   # human-readable name (spaces, title-case)
    description: str,
    start_guid: int,
    zip_path: str,
    app,                                 # AppWindow — used for _resolve_and_save_xml
    install_path: Optional[str] = None,  # if set, also copy mod to this folder
    debug_xml: bool = False,             # if True, save pre-compression XMLs next to the zip
    auto_derive: bool = False,           # if True, derive Medium/Hard from the source difficulty
    progress: Optional[Callable[[str], None]] = None,   # status message sink
) -> None:
    """
    Build a complete mod zip file from the given templates.

    For every loaded region (Latium / Albion) three difficulty variants (easy, medium, hard) are generated, giving up to 6 .a7tinfo files total.
    The .a7t / .a7te next to each .a7tinfo are generated for that file's map size
    (see terrain_builder), because both encode the size themselves.
    All metadata files (modinfo.json, assets.xml, locale text XMLs) are written with variable substitution applied.

    If *install_path* is provided the finished mod folder is also copied there (replacing any existing folder with the same name).

    Raises:
        _fdb.FileDBError   if FileDBReader fails to compress any a7tinfo
        OSError / IOError  on file-system problems
    """
    FertilitySetRegistry.instance().load()

    # Detect whether any loaded template uses the enlarged (DLC01) layout.
    # Enlarged export produces two a7tinfo files per Latium difficulty:
    #   {stem}.a7tinfo — InitialPlayableArea content (non-DLC sessions)
    #   {stem}_enlarged.a7tinfo — full PlayableArea content (DLC01 sessions)
    # Albion never has an enlarged variant.
    is_enlarged_export = any(t.is_enlarged for t in templates)
    tmpl_dir = _TEMPLATE_DIR_ENL if is_enlarged_export else _TEMPLATE_DIR
    terrain  = _TerrainCache(tmpl_dir, progress)

    # Debug XML folder: {zip_stem}_debug_xml/ next to the zip
    debug_dir: Optional[str] = None
    if debug_xml:
        zip_stem = os.path.splitext(zip_path)[0]
        debug_dir = zip_stem + "_debug_xml"
        os.makedirs(debug_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="anno117_mod_")
    try:
        mod_folder_name = f"[Map] {display_name} (TAMPER)"
        mod_root = os.path.join(tmp_dir, mod_folder_name)

        # ── a7tinfo + a7t/a7te per region × difficulty ────────────────────
        for tmpl in templates:
            ri  = _REGION_INFO[tmpl.region]
            # Only enlarged Latium templates get the dual-file treatment
            do_enlarged = is_enlarged_export and tmpl.is_enlarged and tmpl.region == "Latium"

            src_diff = tmpl.difficulty if tmpl.difficulty in config.DIFFICULTY_KEYS else "easy"

            for diff_key in config.DIFFICULTY_KEYS:
                file_stem = f"{slug}_{ri['suffix']}_{diff_key}"
                pool_dir  = os.path.join(mod_root, "data", "tamper", "provinces", ri["province"], "templates", "pool", file_stem)
                os.makedirs(pool_dir, exist_ok=True)

                if progress:
                    progress(f"{tmpl.region} - {diff_key}...")

                # Build the working template for this difficulty variant.
                # When auto_derive is on, derive the other two from the source; otherwise all three difficulties use identical island layouts.
                if auto_derive and diff_key != src_diff:
                    working = _derive_template(tmpl, src_diff, diff_key)
                else:
                    working = deepcopy(tmpl)
                working.difficulty       = diff_key
                working.difficulty_asked = True

                # Generate the regular a7tinfo. For enlarged Latium this uses InitialPlayableArea (non-DLC content only).
                base_copy = _make_initial_copy(working) if do_enlarged else working

                # The terrain must match the a7tinfo this file actually carries:
                # for an enlarged export that is the shrunken InitialPlayableArea
                # copy, not the full template.
                terrain.write(pool_dir, file_stem, tmpl.region, ri["suffix"],
                              base_copy.size[0], base_copy.playable_area)

                tmp_xml_fd, tmp_xml = tempfile.mkstemp(suffix=".xml")
                os.close(tmp_xml_fd)
                try:
                    app._resolve_and_save_xml(base_copy, tmp_xml)
                    if debug_dir:
                        shutil.copy2(tmp_xml, os.path.join(debug_dir, file_stem + ".xml"))
                    _fdb.compress(
                        tmp_xml,
                        os.path.join(pool_dir, file_stem + ".a7tinfo"),
                        interpreter_path=config.INTERPRETER_PATH,
                    )
                finally:
                    try:
                        os.unlink(tmp_xml)
                    except OSError:
                        pass

                # For enlarged Latium: also produce the _enlarged a7tinfo
                if do_enlarged:
                    enl_stem = file_stem + "_enlarged"
                    enl_dir  = os.path.join(mod_root, "data", "tamper", "provinces", ri["province"], "templates", "pool", enl_stem)
                    os.makedirs(enl_dir, exist_ok=True)

                    terrain.write(enl_dir, enl_stem, tmpl.region, ri["suffix"],
                                  working.size[0], working.playable_area)

                    # The enlarged file uses the full working template (all islands,
                    # full PlayableArea) — already derived above.
                    tmp_xml_fd, tmp_xml = tempfile.mkstemp(suffix=".xml")
                    os.close(tmp_xml_fd)
                    try:
                        app._resolve_and_save_xml(working, tmp_xml)
                        if debug_dir:
                            shutil.copy2(tmp_xml, os.path.join(debug_dir, enl_stem + ".xml"))
                        _fdb.compress(tmp_xml, os.path.join(enl_dir, enl_stem + ".a7tinfo"), interpreter_path=config.INTERPRETER_PATH)
                    finally:
                        try:
                            os.unlink(tmp_xml)
                        except OSError:
                            pass

        # ── assets.xml ────────────────────────────────────────────────────
        assets_xml_src = os.path.join(
            tmpl_dir, "data", "base", "config", "export", "assets.xml")
        with open(assets_xml_src, "r", encoding="utf-8") as fh:
            assets_text = _substitute(fh.read(), slug, display_name, description, start_guid)

        # The backdrop lives here, at absolute world coordinates authored for a
        # 2048 map - it has to follow the map size like the terrain does.
        # Substitution runs first so the stems in TemplateFilename match.
        assets_text = terrain_builder.scale_horizon_islands(
            assets_text, terrain.size_by_stem)

        assets_dir = os.path.join(mod_root, "data", "base", "config", "export")
        os.makedirs(assets_dir, exist_ok=True)
        with open(os.path.join(assets_dir, "assets.xml"), "w", encoding="utf-8") as fh:
            fh.write(assets_text)

        # ── modinfo.json ──────────────────────────────────────────────────
        modinfo_src = os.path.join(tmpl_dir, "modinfo.json")
        with open(modinfo_src, "r", encoding="utf-8") as fh:
            modinfo_text = _substitute(fh.read(), slug, display_name, description, start_guid)
        with open(os.path.join(mod_root, "modinfo.json"), "w", encoding="utf-8") as fh:
            fh.write(modinfo_text)

        # ── locale text XMLs (all locales use the same content) ───────────
        text_xml_src = os.path.join(
            tmpl_dir, "data", "base", "config", "gui", "texts_english.xml")
        with open(text_xml_src, "r", encoding="utf-8") as fh:
            text_template = fh.read()
        texts_dir = os.path.join(mod_root, "data", "base", "config", "gui")
        os.makedirs(texts_dir, exist_ok=True)
        for locale_file in _LOCALE_FILES:
            loc_text = _substitute(text_template, slug, display_name, description, start_guid)
            with open(os.path.join(texts_dir, locale_file), "w", encoding="utf-8") as fh:
                fh.write(loc_text)

        # ── Direct install (optional) ─────────────────────────────────────
        if install_path:
            os.makedirs(install_path, exist_ok=True)
            dst = os.path.join(install_path, mod_folder_name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(mod_root, dst)

        # ── Zip everything ────────────────────────────────────────────────
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, files in os.walk(mod_root):
                for fname in files:
                    fpath = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(fpath, tmp_dir)
                    zf.write(fpath, arcname)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── Dialog ───────────────────────────────────────────────────────────────────

class ModExportDialog(tk.Toplevel):
    """
    Collect mod metadata from the user and trigger the mod zip build.

    After wait_window(), check ``dialog._result``:
      (slug, description, start_guid, zip_path)  — proceed
      None                                       — user cancelled
    """

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent)
        self._app    = app
        # result: (slug, display_name, description, start_guid, zip_path, install_path_or_None, debug_xml)
        self._result: Optional[Tuple[str, str, str, int, str, Optional[str], bool]] = None

        self.title("Export as Playable Mod")
        self.configure(bg=config.BG_SECTION)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self.update_idletasks()
        # Centre on parent
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - self.winfo_width())  // 2
        y = py + (ph - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        px = 18  # horizontal padding used throughout

        # Determine whether direct-install is available
        game_path = self._app._game_path_var.get().strip()
        self._game_mods_dir = os.path.join(game_path, "mods") if game_path else ""

        # ── Title ─────────────────────────────────────────────────────────
        tk.Label(self, text="Export as Playable Mod", bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_HEADER).pack(padx=px, pady=(18, 2))

        tk.Label(
            self,
            text=(
                "Packages the current map templates into a playable Anno 117 mod.\n"
                "Installs it manually, or generates a .zip file for mod manager installation or uploading to mod.io when using a custom GUID range."
            ),
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_SMALL, justify="left").pack(padx=px, pady=(0, 6))

        tk.Frame(self, bg=config.FG_SEPARATOR, height=1).pack(fill="x", padx=px, pady=4)

        # ── Mod Name ──────────────────────────────────────────────────────
        tk.Label(self, text="Mod Name", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL,).pack(anchor="w", padx=px, pady=(10, 0))
        tk.Label(
            self,
            text="Lowercase letters, digits, underscores, hyphens — no spaces.\n"
                 "Capitals are converted automatically.",
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left").pack(anchor="w", padx=px)

        self._name_var = tk.StringVar()
        tk.Entry(self, textvariable=self._name_var, width=44, bg=config.BG_MAIN, fg=config.FG_MAIN, insertbackground=config.FG_MAIN, font=config.FONT_SMALL).pack(anchor="w", padx=px, pady=(3, 2))

        # Live preview of the display name (what appears in-game and in zip)
        self._preview_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._preview_var, bg=config.BG_SECTION, fg=config.FG_GOLD, font=config.FONT_XSMALL, justify="left").pack(anchor="w", padx=px, pady=(0, 6))

        # Auto-lowercase, space→hyphen, underscores removed, and live preview update
        def _on_name_change(*_):
            raw = self._name_var.get()
            cleaned = raw.lower().replace(" ", "-").replace("_", "-")
            if raw != cleaned:
                self._name_var.set(cleaned)
                return  # trace will fire again with cleaned value
            slug = _slugify(cleaned)
            if slug:
                dn = _to_display_name(slug)
                self._preview_var.set(f'In-game / zip name:  "{dn}"')
            else:
                self._preview_var.set("")

        self._name_var.trace_add("write", _on_name_change)

        # ── Description ───────────────────────────────────────────────────
        tk.Label(self, text="Description", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=px, pady=(4, 0))
        tk.Label(self, text="English description shown in the mod manager (optional).", bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=px)
        self._desc_var = tk.StringVar()
        tk.Entry(self, textvariable=self._desc_var, width=44, bg=config.BG_MAIN, fg=config.FG_MAIN, insertbackground=config.FG_MAIN, font=config.FONT_SMALL).pack(anchor="w", padx=px, pady=(3, 6))

        # Replace double-quotes with single-quotes on input — they would break JSON formatting
        def _on_desc_change(*_):
            raw = self._desc_var.get()
            cleaned = raw.replace('"', "'")
            if raw != cleaned:
                self._desc_var.set(cleaned)
        self._desc_var.trace_add("write", _on_desc_change)

        # ── Start GUID ────────────────────────────────────────────────────
        # Header row: label + "use own range" checkbox + claim-range button
        guid_hdr = tk.Frame(self, bg=config.BG_SECTION)
        guid_hdr.pack(fill="x", padx=px, pady=(4, 0))
        tk.Label(guid_hdr, text="Start GUID", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(side="left")
        tk.Button(
            guid_hdr, text="Claim a Range ↗",
            command=lambda: webbrowser.open("https://github.com/anno-mods/GuidRanges"),
            bg=config.BG_HOVER, fg=config.FG_DIM, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_XSMALL, padx=6, pady=2, cursor="hand2").pack(side="right")
        self._own_guid_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            guid_hdr, text="Use my own reserved range",
            variable=self._own_guid_var,
            command=self._on_guid_mode_change,
            bg=config.BG_SECTION, fg=config.FG_DIM, activebackground=config.BG_SECTION, activeforeground=config.FG_GOLD, selectcolor=config.BG_MAIN, font=config.FONT_XSMALL).pack(side="right", padx=(0, 8))

        tk.Label(
            self,
            text="Seven consecutive GUIDs will be reserved (Start_GUID … Start_GUID+6).\n"
                 "Unchecked: uses the personal range (local testing only, installs directly).",
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left").pack(anchor="w", padx=px)

        next_personal = _settings.get("next_personal_guid", _PERSONAL_GUID_MIN)
        if not isinstance(next_personal, int) or not (_PERSONAL_GUID_MIN <= next_personal <= _PERSONAL_GUID_MAX):
            next_personal = _PERSONAL_GUID_MIN
        self._next_personal_guid = next_personal

        self._guid_var = tk.StringVar(value=str(next_personal))
        self._guid_entry = tk.Entry(self, textvariable=self._guid_var, width=22, bg=config.BG_MAIN, fg=config.FG_MAIN, insertbackground=config.FG_MAIN, font=config.FONT_SMALL)
        self._guid_entry.pack(anchor="w", padx=px, pady=(3, 6))
        self._guid_var.trace_add("write", lambda *_: self._on_guid_changed())

        tk.Frame(self, bg=config.FG_SEPARATOR, height=1).pack(fill="x", padx=px, pady=(6, 4))

        # ── Direct install option ─────────────────────────────────────────
        self._install_var = tk.BooleanVar(value=True)
        self._install_chk: Optional[tk.Checkbutton] = None
        install_available = bool(self._game_mods_dir)
        if install_available:
            self._install_chk = tk.Checkbutton(
                self, text="Install directly to game mods folder",
                variable=self._install_var, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_SECTION, activeforeground=config.FG_GOLD, selectcolor=config.BG_MAIN, font=config.FONT_SMALL)
            self._install_chk.pack(anchor="w", padx=px, pady=(4, 0))
            tk.Label(self, text=self._game_mods_dir, bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=px + 4, pady=(0, 6))
        else:
            tk.Label(
                self,
                text="(Set Game Path in the main window to enable direct install.)",
                bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=px, pady=(4, 6))

        # Apply initial state (personal mode by default)
        self._update_install_state()

        tk.Frame(self, bg=config.FG_SEPARATOR, height=1).pack(fill="x", padx=px, pady=(6, 4))

        # ── Difficulty derivation ─────────────────────────────────────────
        tk.Label(self, text="Difficulty Variants", bg=config.BG_SECTION, fg=config.FG_MAIN, font=config.FONT_BOLD_SMALL).pack(anchor="w", padx=px, pady=(4, 0))

        # Show which difficulty each loaded region template is set to
        diff_lines = []
        for region in ("Latium", "Albion"):
            tab = getattr(self._app, "region_tabs", {}).get(region)
            tmpl = tab.get_template() if tab else None
            if tmpl is not None:
                lbl = config.DIFFICULTY_LABELS.get(tmpl.difficulty, tmpl.difficulty.title())
                diff_lines.append(f"{region}: {lbl}")
        tk.Label(
            self,
            text="  ·  ".join(diff_lines) if diff_lines else "No templates loaded",
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL).pack(anchor="w", padx=px)

        self._auto_derive_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self,
            text="Auto-derive other difficulty variants from this map",
            variable=self._auto_derive_var, bg=config.BG_SECTION, fg=config.FG_MAIN, activebackground=config.BG_SECTION, activeforeground=config.FG_GOLD, selectcolor=config.BG_MAIN, font=config.FONT_SMALL).pack(anchor="w", padx=px, pady=(3, 0))
        tk.Label(
            self,
            text="When on: Medium and Hard are generated by scaling Normal island sizes.\n"
                 "When off: all three difficulties use the same island layout.",
            bg=config.BG_SECTION, fg=config.FG_DIM, font=config.FONT_XSMALL, justify="left").pack(anchor="w", padx=px + 4, pady=(0, 4))

        # ── Debug XML (hidden — uncomment checkbox to re-enable) ──────────
        self._debug_xml_var = tk.BooleanVar(value=False)
        # tk.Checkbutton(
        #     self,
        #     text="Save debug XML files (pre-compression copies alongside the zip)",
        #     variable=self._debug_xml_var,
        #     bg=config.BG_SECTION, fg=config.FG_DIM,
        #     activebackground=config.BG_SECTION,
        #     activeforeground=config.FG_GOLD,
        #     selectcolor=config.BG_MAIN,
        #     font=config.FONT_XSMALL,
        # ).pack(anchor="w", padx=px, pady=(4, 2))

        # ── Buttons ───────────────────────────────────────────────────────
        tk.Frame(self, bg=config.FG_SEPARATOR, height=1).pack(fill="x", padx=px, pady=(4, 0))

        btn_frame = tk.Frame(self, bg=config.BG_SECTION)
        btn_frame.pack(pady=(10, 18))

        tk.Button(btn_frame, text="Cancel", command=self.destroy, bg=config.BG_HOVER, fg=config.FG_MAIN, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_SMALL, padx=14, pady=5, cursor="hand2").pack(side="left", padx=8)

        tk.Button(btn_frame, text="Export…", command=self._on_export, bg=config.BG_HOVER, fg=config.FG_GOLD, activebackground=config.BG_MAIN, activeforeground=config.FG_GOLD, relief=tk.FLAT, font=config.FONT_UI_BOLD, padx=14, pady=5, cursor="hand2").pack(side="left", padx=8)

    # ── GUID mode helpers ─────────────────────────────────────────────────

    def _is_personal_guid(self, guid_int: int) -> bool:
        return _PERSONAL_GUID_MIN <= guid_int <= _PERSONAL_GUID_MAX

    def _on_guid_mode_change(self):
        if not self._own_guid_var.get():
            # Switching back to personal range: restore default personal GUID
            self._guid_var.set(str(self._next_personal_guid))
        else:
            # Switching to own range: clear field so user types their GUID
            self._guid_var.set("")
        self._update_install_state()

    def _on_guid_changed(self):
        self._update_install_state()

    def _update_install_state(self):
        """Force install ON (and disable checkbox) unless using a non-personal GUID."""
        if not self._install_chk:
            return
        own_mode = self._own_guid_var.get()
        if own_mode:
            try:
                g = int(self._guid_var.get().strip())
                in_personal = self._is_personal_guid(g)
            except ValueError:
                in_personal = True  # invalid → treat as personal until corrected
        else:
            in_personal = True  # personal mode always forces install
        if in_personal:
            self._install_var.set(True)
            self._install_chk.config(state="disabled")
        else:
            self._install_chk.config(state="normal")

    # ── Validation & export trigger ───────────────────────────────────────

    def _on_export(self):
        # ── Mod name ──────────────────────────────────────────────────────
        raw_name = self._name_var.get().strip()
        if not raw_name:
            messagebox.showerror("Missing Input", "Please enter a Mod Name.", parent=self)
            return
        slug = _slugify(raw_name)
        if not slug:
            messagebox.showerror("Invalid Mod Name", "Mod Name must contain at least one letter or digit.", parent=self)
            return
        display_name = _to_display_name(slug)

        # ── Description (optional) ────────────────────────────────────────
        description = self._desc_var.get().strip()

        # ── Start GUID ────────────────────────────────────────────────────
        guid_str = self._guid_var.get().strip()
        try:
            start_guid = int(guid_str)
            if start_guid <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid GUID", "Start GUID must be a positive integer (e.g. 1234567890).", parent=self)
            return

        own_mode = self._own_guid_var.get()
        personal_mode = not own_mode or self._is_personal_guid(start_guid)
        self._personal_mode = personal_mode

        # ── Output path ───────────────────────────────────────────────────
        if personal_mode:
            # Personal-range export: install directly, no permanent zip needed.
            if not self._game_mods_dir:
                messagebox.showerror(
                    "No Game Path",
                    "Set the Game Path in the main window first to use the\n"
                    "personal GUID range for direct mod installation.",
                    parent=self,
                )
                return
            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="anno117_tmp_")
            os.close(zip_fd)
        else:
            zip_path = filedialog.asksaveasfilename(
                parent=self,
                title="Save Mod Zip As…",
                defaultextension=".zip",
                initialfile=f"[Map] {display_name} (TAMPER).zip",
                filetypes=[("Zip archive", "*.zip"), ("All files", "*.*")],
            )
            if not zip_path:
                return  # user cancelled — stay in dialog

        # ── Install path ──────────────────────────────────────────────────
        install_path = self._game_mods_dir if self._install_var.get() else None

        # ── Advance personal GUID counter ─────────────────────────────────
        if personal_mode:
            next_guid = start_guid + _PERSONAL_GUID_STEP
            if next_guid > _PERSONAL_GUID_MAX:
                messagebox.showwarning(
                    "Personal GUID Range Full",
                    f"The personal GUID range (up to {_PERSONAL_GUID_MAX}) has been\n"
                    f"exhausted. The counter has been reset to {_PERSONAL_GUID_MIN}.\n\n"
                    "Consider claiming your own range at https://github.com/anno-mods/GuidRanges.",
                    parent=self,
                )
                next_guid = _PERSONAL_GUID_MIN
            _settings.set("next_personal_guid", next_guid)

        self._result = (slug, display_name, description, start_guid, zip_path, install_path, self._debug_xml_var.get(), self._auto_derive_var.get())
        self.destroy()
