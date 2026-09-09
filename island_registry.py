"""
Anno 117 Map Template Editor - Island Registry

Parses the extracted assets.xml to build a list of all placeable islands,
their regions, types, file paths, and matching UI images.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, List, Dict

import config

# ─── Island type mapping ─────────────────────────────────────────────────────

# Maps assets.xml IslandType → our internal island_type string
ASSET_TYPE_MAP = {
    "Normal":        "Normal",
    "Starter":       "Starter",
    "ThirdParty":    "ThirdParty",
    "PirateIsland":  "Pirate",
    "VolcanicIsland":"Vulcan",
    "Decoration":    None,   # excluded
}

# Maps IslandRegion → our region tab name
ASSET_REGION_MAP = {
    "Roman":  "Latium",
    "Celtic": "Albion",
}


@dataclass
class IslandAsset:
    """One placeable island from assets.xml."""
    guid:        int
    name:        str           # e.g. "roman_island_small_01"
    file_path:   str           # e.g. "data/base/provinces/roman/islands/pool/.../roman_island_small_01.a7m"
    size:        str           # Small / Medium / Large / ExtraLarge / Continental
    island_type: str           # Normal / Starter / ThirdParty / Pirate / Vulcan
    region:      str           # Latium / Albion
    image_path:  Optional[str] = field(default=None)   # resolved UI image path

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def a7m_name(self) -> str:
        """Just the .a7m filename without extension."""
        return os.path.basename(self.file_path).replace(".a7m", "")


# ─── Size detection ──────────────────────────────────────────────────────────


def _size_from_filepath(fp: str) -> str:
    fp = fp.lower()
    if "continental" in fp:
        return "Continental"
    if "extralarge" in fp or "/xl/" in fp:
        return "ExtraLarge"
    if "large" in fp and "extra" not in fp:
        return "Large"
    if "medium" in fp:
        return "Medium"
    if "small" in fp:
        return "Small"
    # Pirate islands are Medium; everything else (incl. 3rd party/trader) is Small
    if "pirate" in fp:
        return "Medium"
    return "Small"


# ─── Image path resolution ───────────────────────────────────────────────────

def _resolve_image(a7m_name: str, region: str = "") -> Optional[str]:
    """
    Map an island .a7m name to a UI image path.

    Naming convention examples:
      roman_island_small_01        → data/ui/islands/roman/small_01.jpg
      roman_dlc01_island_medium_02 → data/ui/islands/roman/dlc01_medium_02.jpg
      celtic_island_large_05       → data/ui/islands/celtic/large_05.jpg
      roman_island_trader_01       → data/ui/islands/roman/trader_01.jpg
      roman_island_pirate_01       → data/ui/islands/roman/pirate_01.jpg
    """
    ui_base = config.UI_ISLANDS_DIR
    n = a7m_name.lower()

    if "celtic" in n:
        cultures = ["celtic", "roman"]
    elif "roman" in n:
        cultures = ["roman", "celtic"]
    elif region == "Albion":
        cultures = ["celtic", "roman"]
    else:
        cultures = ["roman", "celtic"]

    for culture in cultures:
        if culture == "roman" and n.startswith("celtic"):
            continue
        if culture == "celtic" and n.startswith("roman"):
            continue

        stem = n
        for pfx in (f"{culture}_island_", f"{culture}_dlc01_island_",
                    f"{culture}_dlc_01_island_", f"{culture}_"):
            if n.startswith(pfx):
                stem = n[len(pfx):]  # e.g. "small_01" / "dlc01_medium_02"
                if "dlc01" in pfx or "dlc_01" in pfx:
                    stem = "dlc01_" + stem
                break

        # Strip 3rdparty_ segment so e.g. "3rdparty_trader_01" → "trader_01"
        if stem.startswith("3rdparty_"):
            stem = stem[len("3rdparty_"):]

        # Try jpg first, then png
        for ext in (".jpg", ".png"):
            path = os.path.join(ui_base, culture, stem + ext)
            if os.path.isfile(path):
                return path

    return None


def _placeholder_for(size: str, island_type: str) -> Optional[str]:
    """Return the placeholder image path for a given size/type."""
    ui_base = config.PLACEHOLDERS_DIR
    mapping = {
        ("ExtraLarge", "Normal"):  "xL_island.png",
        ("Continental", "Vulcan"): "continental_island.png",
        ("Large",  "Normal"):      "L_island.png",
        ("Medium", "Normal"):      "m_island.png",
        ("Small",  "Normal"):      "s_island.png",
        ("Medium", "Pirate"):      "pirate_island.png",
        ("Small",  "Pirate"):      "pirate_island.png",
        ("Medium", "ThirdParty"):  "3rd_island.png",
        ("Small",  "ThirdParty"):  "3rd_island.png",
    }
    fname = mapping.get((size, island_type))
    if not fname:
        # Generic fallback by size
        size_map = {
            "ExtraLarge": "xL_island.png",
            "Continental":"continental_island.png",
            "Large":      "L_island.png",
            "Medium":     "m_island.png",
            "Small":      "s_island.png",
        }
        fname = size_map.get(size, "m_island.png")
    path = os.path.join(ui_base, fname)
    return path if os.path.isfile(path) else None


# ─── Registry ────────────────────────────────────────────────────────────────

class IslandRegistry:
    """
    Loads all RandomIsland assets from assets.xml and provides lookup methods.
    Singleton - call IslandRegistry.instance() to get the shared instance.
    """

    _instance: Optional["IslandRegistry"] = None

    def __init__(self):
        self._islands: List[IslandAsset] = []
        self._by_guid: Dict[int, IslandAsset] = {}
        self._by_name: Dict[str, IslandAsset] = {}
        self._loaded = False

    @classmethod
    def instance(cls) -> "IslandRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, force: bool = False) -> bool:
        """
        Parse assets.xml and build the registry.
        Returns True on success, False if assets.xml not found.
        """
        if self._loaded and not force:
            return True

        assets_path = config.ASSETS_XML
        if not os.path.isfile(assets_path):
            print(f"[registry] assets.xml not found at {assets_path}")
            return False

        print(f"[registry] Loading islands from {assets_path}…")
        try:
            tree = ET.parse(assets_path)
            root = tree.getroot()
        except Exception as e:
            print(f"[registry] Failed to parse assets.xml: {e}")
            return False

        count = 0
        for asset in root.iter("Asset"):
            template_el = asset.find("Template")
            if template_el is None or template_el.text != "RandomIsland":
                continue

            values = asset.find("Values")
            if values is None:
                continue

            ri = values.find("RandomIsland")
            if ri is None:
                continue

            # IslandType - assets.xml may use semicolon-separated values like "Normal;Starter"
            type_el = ri.find("IslandType")
            raw_type = type_el.text.strip() if type_el is not None and type_el.text else "Normal"
            mapped_type = None
            for part in raw_type.split(";"):
                candidate = ASSET_TYPE_MAP.get(part.strip())
                if candidate is not None:
                    mapped_type = candidate
                    break
            if mapped_type is None:
                continue   # skip Decoration and unknown types

            # IslandRegion
            region_el = ri.find("IslandRegion")
            raw_region = region_el.text.strip() if region_el is not None and region_el.text else "Roman"
            region = ASSET_REGION_MAP.get(raw_region, "Latium")

            # FilePath
            fp_el = ri.find("FilePath")
            if fp_el is None or not fp_el.text:
                continue
            file_path = fp_el.text.strip().replace("\\", "/")

            # GUID
            guid_el = asset.find("Values/Standard/GUID")
            guid = int(guid_el.text.strip()) if guid_el is not None and guid_el.text else 0

            # Name
            name_el = asset.find("Values/Standard/Name")
            name = name_el.text.strip() if name_el is not None and name_el.text else \
                   os.path.basename(file_path).replace(".a7m", "")

            # Size from file path
            size = _size_from_filepath(file_path)
            # Override with IslandSize if present
            isz_el = ri.find("IslandSize")
            if isz_el is not None and isz_el.text:
                sz_map = {
                    "Small": "Small", "Medium": "Medium",
                    "Large": "Large", "ExtraLarge": "ExtraLarge",
                    "Continental": "Continental",
                }
                size = sz_map.get(isz_el.text.strip(), size)

            # Resolve image
            a7m_name = os.path.basename(file_path).replace(".a7m", "")
            image = _resolve_image(a7m_name, region)

            isl = IslandAsset(
                guid=guid,
                name=name,
                file_path=file_path,
                size=size,
                island_type=mapped_type,
                region=region,
                image_path=image,
            )
            self._islands.append(isl)
            self._by_guid[guid] = isl
            self._by_name[a7m_name.lower()] = isl
            count += 1

        # ── Continental islands (Template=Island, no RandomIsland container) ───
        # These fixed islands are skipped by the main loop because they lack a <RandomIsland> block. All data is hardcoded from known assets.xml entries.
        # .a7m files are not extracted to disk, so no file-existence check is needed.
        _continental = [
            IslandAsset(
                guid=145426,
                name="roman_dlc01_island_continental_01",
                file_path=(
                    "data/dlc01/provinces/roman/islands/pool/"
                    "roman_dlc01_island_continental_01/"
                    "roman_dlc01_island_continental_01.a7m"
                ),
                size="Continental",
                island_type="Vulcan",
                region="Latium",
                image_path=(
                    _resolve_image("roman_dlc01_island_continental_01", "Latium")
                    or _placeholder_for("Continental", "Vulcan")
                ),
            ),
        ]
        for isl in _continental:
            if isl.guid in self._by_guid:
                continue
            a7m_key = os.path.basename(isl.file_path).replace(".a7m", "").lower()
            self._islands.append(isl)
            self._by_guid[isl.guid] = isl
            self._by_name[a7m_key] = isl
            count += 1
            print(f"[registry] Added continental island: {isl.name} (GUID {isl.guid})")

        self._loaded = True
        print(f"[registry] Loaded {count} islands.")
        return True

    # ── Lookup ───────────────────────────────────────────────────────────────

    def all_islands(self) -> List[IslandAsset]:
        return list(self._islands)

    def for_region(self, region: str,
                   include_other_regions: bool = True) -> List[IslandAsset]:
        if region in ("Both", "all", "All"):
            return list(self._islands)
        if not include_other_regions:
            return [i for i in self._islands if i.region == region]
        # Both regions show all islands, with native-region islands listed first
        native = [i for i in self._islands if i.region == region]
        other  = [i for i in self._islands if i.region != region]
        return native + other

    def for_region_size_type(self, region: str, size: str,
                              island_type: str) -> List[IslandAsset]:
        return [i for i in self.for_region(region)
                if i.size == size and i.island_type == island_type]

    def find_by_name(self, a7m_name: str) -> Optional[IslandAsset]:
        """Match a .a7m filename (without extension) to a registry entry."""
        key = os.path.basename(a7m_name).replace(".a7m", "").lower()
        return self._by_name.get(key)

    def find_by_guid(self, guid: int) -> Optional[IslandAsset]:
        return self._by_guid.get(guid)

    @property
    def is_loaded(self) -> bool:
        return self._loaded


# ─── Pool image assignment ────────────────────────────────────────────────────

class PoolImageAssigner:
    """
    For random islands, assigns UI images from the pool, cycling if needed.
    One assigner per canvas redraw cycle.
    """

    def __init__(self):
        self._counters: Dict[str, int] = {}

    def get_image(self, region: str, size: str, island_type: str) -> Optional[str]:
        key = f"{region}_{size}_{island_type}"
        pool = IslandRegistry.instance().for_region_size_type(region, size, island_type)

        # Filter to ones with images
        pool_with_img = [i for i in pool if i.image_path]

        # L/XL Starter islands are stored as Normal in the registry (assets.xml uses "Normal;Starter" and we take the first part).
        # Fall back to the Normal pool so Starter-typed islands get real images.
        if not pool_with_img and island_type == "Starter":
            fallback_pool = IslandRegistry.instance().for_region_size_type(
                region, size, "Normal"
            )
            pool_with_img = [i for i in fallback_pool if i.image_path]

        # ThirdParty/Pirate islands only exist at certain sizes in the registry.
        # Try all sizes so a trader or pirate island always gets its image.
        if not pool_with_img and island_type in ("ThirdParty", "Pirate"):
            for fallback_size in ("Medium", "Small", "Large", "ExtraLarge"):
                if fallback_size == size:
                    continue
                fb = IslandRegistry.instance().for_region_size_type(
                    region, fallback_size, island_type
                )
                pool_with_img = [i for i in fb if i.image_path]
                if pool_with_img:
                    break

        if not pool_with_img:
            # Fall back to placeholder
            return _placeholder_for(size, island_type)

        idx = self._counters.get(key, 0) % len(pool_with_img)
        self._counters[key] = idx + 1
        return pool_with_img[idx].image_path