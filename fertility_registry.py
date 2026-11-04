"""
Anno 117 Map Template Editor - Fertility Registry

Parses the extracted assets.xml to build the list of all placeable
fertility / deposit assets, their icons, and their region restrictions.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

import config

# GUIDs that should never appear in the picker
BLACKLISTED_GUIDS = {145337, 4050, 2204, 2203, 32456, 2201}  # 32456=Clay, 2201=Sardines

def _resolve_icon(icon_rel: str) -> str:
    """Convert a relative IconFilename from assets.xml to an absolute disk path."""
    # icon_rel starts with "data/…" - resource_path() prepends the app root
    return config.resource_path(icon_rel)


@dataclass
class FertilityAsset:
    guid: int
    name: str           # full name from assets.xml, e.g. "Fertility Roman Olives"
    icon_path: str      # absolute path to the PNG on disk
    region: str         # "Latium", "Albion", or "Both"

    @property
    def display_name(self) -> str:
        """Short name stripped of region/category prefix for UI display."""
        for prefix in (
            "Fertility Roman ", "Fertility Celtic ", "Fertility Egyptian ", "Fertility ",
            "Deposit Roman ", "Deposit Celtic ", "Deposit Egyptian ", "Deposit ",
        ):
            if self.name.startswith(prefix):
                return self.name[len(prefix):]
        return self.name

    @property
    def category(self) -> str:
        """'Fertility' or 'Deposit'."""
        return "Deposit" if self.name.startswith("Deposit") else "Fertility"


class FertilityRegistry:
    """Singleton - call FertilityRegistry.instance() to get the shared instance."""

    _instance: Optional["FertilityRegistry"] = None

    def __init__(self):
        self._assets: List[FertilityAsset] = []
        self._loaded = False

    @classmethod
    def instance(cls) -> "FertilityRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, force: bool = False) -> bool:
        if self._loaded and not force:
            return True
        assets_path = config.ASSETS_XML
        if not os.path.isfile(assets_path):
            return False
        try:
            tree = ET.parse(assets_path)
            root = tree.getroot()
            result: List[FertilityAsset] = []
            for asset in root.iter("Asset"):
                if asset.findtext("Template") != "Fertility":
                    continue
                guid_text = (asset.findtext("Values/Standard/GUID") or "").strip()
                if not guid_text:
                    continue
                guid = int(guid_text)
                if guid in BLACKLISTED_GUIDS:
                    continue
                name = (asset.findtext("Values/Standard/Name") or "").strip()
                icon_rel = (asset.findtext("Values/Standard/IconFilename") or "").strip()

                # Region rule: Roman → Latium only, Celtic → Albion only, Egyptian → Aegyptus only, else Both
                if "Roman" in name:
                    region = "Latium"
                elif "Celtic" in name:
                    region = "Albion"
                elif "Egyptian" in name:
                    region = "Aegyptus"
                else:
                    region = "Both"

                result.append(FertilityAsset(
                    guid=guid,
                    name=name,
                    icon_path=_resolve_icon(icon_rel),
                    region=region,
                ))
            self._assets = result
            self._loaded = True
            return True
        except Exception as exc:
            print(f"[fertility] Load failed: {exc}")
            return False

    def for_region(self, region: str) -> List[FertilityAsset]:
        """Return all fertilities valid for the given region (Latium / Albion)."""
        return [f for f in self._assets if f.region in (region, "Both")]

    def find_by_guid(self, guid: int) -> Optional[FertilityAsset]:
        for f in self._assets:
            if f.guid == guid:
                return f
        return None
