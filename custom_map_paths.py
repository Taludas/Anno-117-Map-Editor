"""Discovery and export helpers for user supplied Anno 117 islands."""
from __future__ import annotations
import os, re, shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable
import settings

CUSTOM_ISLANDS_KEY = "custom_islands_paths"
ISLAND_PACKAGES_KEY = "island_packages_paths"
LEGACY_CUSTOM_KEY = "custom_islands_path"
LEGACY_PACKAGES_KEY = "island_packages_path"

@dataclass(frozen=True)
class CustomIslandRecord:
    name: str
    file_path: str
    source_dir: str | None
    image_path: str | None
    region: str
    package_island: bool = False
    placeholder_size: str | None = None

def _path_list(value) -> list[str]:
    values = value if isinstance(value, list) else ([value] if isinstance(value, str) and value.strip() else [])
    result = []
    for path in values:
        normalized = os.path.normpath(str(path).strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result

def configured_paths() -> tuple[list[str], list[str]]:
    custom = settings.get(CUSTOM_ISLANDS_KEY, None)
    packages = settings.get(ISLAND_PACKAGES_KEY, None)
    if custom is None: custom = settings.get(LEGACY_CUSTOM_KEY, "")
    if packages is None: packages = settings.get(LEGACY_PACKAGES_KEY, "")
    return _path_list(custom), _path_list(packages)

def save_paths(custom_islands: list[str], island_packages: list[str]) -> None:
    settings.set(CUSTOM_ISLANDS_KEY, _path_list(custom_islands))
    settings.set(ISLAND_PACKAGES_KEY, _path_list(island_packages))

def _region_from_text(text: str) -> str:
    low = text.replace("\\", "/").lower()
    return "Albion" if any(x in low for x in ("albion", "celtic")) else "Latium"

def discover_custom_islands(root: str) -> list[CustomIslandRecord]:
    records = []
    if not root or not os.path.isdir(root): return records
    for dirpath, _, files in os.walk(root):
        a7ms = sorted(f for f in files if f.lower().endswith(".a7m"))
        if not a7ms: continue
        folder = os.path.basename(dirpath)
        preview = os.path.join(dirpath, "_gamedata", folder, "activemapimage.png")
        image = preview if os.path.isfile(preview) else None
        region = _region_from_text(os.path.relpath(dirpath, root))
        province = "celtic" if region == "Albion" else "roman"
        for filename in a7ms:
            records.append(CustomIslandRecord(os.path.splitext(filename)[0], f"data/custom/{province}/{folder}/{filename}", dirpath, image, region))
    return records

def _assets_from_file(path: str):
    try:
        return list(ET.parse(path).getroot().iter("Asset"))
    except (OSError, ET.ParseError):
        # Also handle concatenated ModOps snippets, as used by some packages.
        try: text = open(path, "r", encoding="utf-8-sig").read()
        except OSError: return []
        assets = []
        for block in re.findall(r"<Asset\b.*?</Asset>", text, flags=re.DOTALL | re.IGNORECASE):
            try: assets.append(ET.fromstring(block))
            except ET.ParseError: pass
        return assets

def _resolve_package_root(selected_root: str, assets_path: str, game_path: str) -> str:
    current = os.path.dirname(os.path.abspath(assets_path))
    selected = os.path.abspath(selected_root)
    while True:
        if os.path.isfile(os.path.join(current, *game_path.split("/"))): return current
        if current == selected or os.path.dirname(current) == current: break
        current = os.path.dirname(current)
    return selected

def discover_package_islands(root: str) -> list[CustomIslandRecord]:
    records = []
    if not root or not os.path.isdir(root): return records
    for assets_path in _files_named(root, "assets.xml"):
        for asset in _assets_from_file(assets_path):
            if (asset.findtext("Template") or "").strip() != "RandomIsland": continue
            random_island = asset.find("./Values/RandomIsland")
            legacy = asset.find("./Values/RandomIslandConfig")
            values = random_island if random_island is not None else legacy
            if values is None: continue
            game_path = (values.findtext("FilePath") or "").strip().replace("\\", "/")
            if not game_path: continue
            region_text = (values.findtext("IslandRegion") or game_path).strip()
            placeholder_size = (values.findtext("IslandPlaceholderSize") or "").strip() or None
            package_root = _resolve_package_root(root, assets_path, game_path)
            local_dir = os.path.dirname(os.path.join(package_root, *game_path.split("/")))
            island_name = os.path.splitext(os.path.basename(game_path))[0]
            candidates = [os.path.join(local_dir, "_gamedata", island_name, "activemapimage.png"), os.path.join(local_dir, "activemapimage.png")]
            image = next((p for p in candidates if os.path.isfile(p)), None)
            records.append(CustomIslandRecord(island_name, game_path, None, image, _region_from_text(region_text), True, placeholder_size))
    return records

def all_records() -> list[CustomIslandRecord]:
    custom_roots, package_roots = configured_paths()
    records = [r for root in custom_roots for r in discover_custom_islands(root)] + [r for root in package_roots for r in discover_package_islands(root)]
    return list({r.file_path.lower(): r for r in records}.values())

def copy_used_custom_islands(mod_root: str, map_file_paths: Iterable[str]) -> None:
    wanted = {p.replace("\\", "/").lower() for p in map_file_paths if p}
    custom_roots, _ = configured_paths()
    for root in custom_roots:
        for record in discover_custom_islands(root):
            if record.file_path.lower() in wanted and record.source_dir:
                destination = os.path.join(mod_root, *os.path.dirname(record.file_path).split("/"))
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copytree(record.source_dir, destination, dirs_exist_ok=True)

def _files_named(root: str, name: str):
    for dirpath, _, files in os.walk(root):
        for filename in files:
            if filename.lower() == name.lower(): yield os.path.join(dirpath, filename)
