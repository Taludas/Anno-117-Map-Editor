"""
Anno 117 Map Template Editor - Aegyptus (DLC03) template model

The Aegyptus template is one fixed layout: 39 islands in four "complexes" (the quadrants of the Nile
delta) plus one ship spawn. Every element keeps its original XML node, so fields the editor does not
touch (TypePerConstructionArea, FertilitySetGUIDs, FertilitiesPerAreaIndex, MineSlotActivation, ...)
survive a save/export byte for byte. The editor changes only:

  • fertilities   FertilityGuids + RandomizeFertilities
  • difficulty    RandomIslandConfig/Difficulty (Hard = the "no gold" fertility sets)
  • layer         MapFilePath (full or _layer01 file); "auto" leaves the choice to the game's
                  ReduceSizeIslands, anything else removes the island from that list on export
  • complexes     position of all elements of a quadrant (moved together) or their removal
  • spawn         position
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import copy
import json
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import egypt_data as ed

LAYER_AUTO, LAYER_FULL, LAYER_REDUCED = "auto", "full", "reduced"
SIDECAR_SUFFIX = ".tamper.json"


class EgyptElement:
    """One TemplateElement of the Aegyptus template, backed by its XML node."""

    def __init__(self, node: ET.Element, eid: int):
        self.node = node
        self.eid = eid
        mf = node.find("Element/MapFilePath")
        self.is_spawn = mf is None
        self.base = ed.base_stem(ed.stem_of(mf.text)) if mf is not None else None
        if mf is not None and ed.stem_of(mf.text).endswith(ed.LAYER_SUFFIX):
            self.layer_mode = LAYER_REDUCED
        else:
            self.layer_mode = LAYER_AUTO if self.can_auto_reduce else LAYER_FULL

    # ── identity ─────────────────────────────────────────────────────────────

    @property
    def el(self) -> ET.Element:
        return self.node.find("Element")

    @property
    def short(self) -> str:
        return "spawn" if self.is_spawn else self.base.replace(ed.PREFIX, "")

    @property
    def stem(self) -> Optional[str]:
        """The island file this element currently places."""
        if self.is_spawn:
            return None
        return ed.layer_stem(self.base) if self.layer_mode == LAYER_REDUCED else self.base

    @property
    def info(self) -> Optional[ed.IslandFile]:
        return ed.islands().get(self.stem) if self.stem else None

    @property
    def base_info(self) -> Optional[ed.IslandFile]:
        return ed.islands().get(self.base) if self.base else None

    @property
    def quadrant(self) -> Optional[str]:
        bi = self.base_info
        return bi.quadrant if bi else None

    @property
    def kind(self) -> str:
        bi = self.base_info
        return bi.kind if bi else "Spawn"

    @property
    def is_fertile(self) -> bool:
        return self.kind in ("Large", "Medium", "Small")

    @property
    def can_auto_reduce(self) -> bool:
        return bool(self.base) and self.short in ed.AUTO_REDUCED

    @property
    def has_layer(self) -> bool:
        bi = self.base_info
        return bool(bi and bi.has_layer)

    # ── position ─────────────────────────────────────────────────────────────

    @property
    def position(self) -> Tuple[int, int]:
        x, y = self.el.find("Position").text.split()
        return int(x), int(y)

    @position.setter
    def position(self, pos: Tuple[int, int]) -> None:
        self.el.find("Position").text = f"{int(pos[0])} {int(pos[1])}"

    @property
    def rotation(self) -> int:
        return int((self.el.findtext("Rotation90") or "0").strip() or 0) % 4

    @rotation.setter
    def rotation(self, rot: int) -> None:
        r = self.el.find("Rotation90")
        if r is not None:
            r.text = str(rot % 4)

    def active_world_rect(self, dx: int = 0, dy: int = 0, rot: Optional[int] = None) -> Optional[Tuple[int, int, int, int]]:
        info = self.info
        if not info:
            return None
        x, y = self.position
        a = info.rotated_rect(self.rotation if rot is None else rot)
        return (x + dx + a[0], y + dy + a[1], x + dx + a[2], y + dy + a[3])

    def contains(self, gx: float, gy: float) -> bool:
        info = self.info
        if not info:
            return False
        x, y = self.position
        return info.contains(gx - x, gy - y, self.rotation)

    def world_cells(self, dx: int = 0, dy: int = 0, rot: Optional[int] = None) -> set:
        """Territory as a set of absolute 8-unit cells (positions are multiples of 8, so all grids align)."""
        info = self.info
        if not info:
            return set()
        x, y = self.position
        ox, oy = (x + dx) // info.cell, (y + dy) // info.cell
        return {(ox + cx, oy + cy) for cx, cy in _rotated_cells(info, self.rotation if rot is None else rot)}

    # ── game fields ──────────────────────────────────────────────────────────

    @property
    def type_id(self) -> str:
        return (self.el.findtext("RandomIslandConfig/value/Type/id") or "Normal").strip()

    @property
    def is_starter(self) -> bool:
        return self.type_id == "Starter"

    @property
    def difficulty(self) -> str:
        return (self.el.findtext("RandomIslandConfig/value/Difficulty/id") or "Normal").strip()

    @difficulty.setter
    def difficulty(self, value: str) -> None:
        d = self.el.find("RandomIslandConfig/value/Difficulty")
        if d is None:
            return
        idn = d.find("id")
        if idn is None:
            idn = ET.SubElement(d, "id")
        idn.text = value

    @property
    def fertility_guids(self) -> List[int]:
        text = self.el.findtext("FertilityGuids") or ""
        return [int(v) for v in text.split()]

    @property
    def randomize(self) -> bool:
        # The game randomises unless RandomizeFertilities is 0 AND a list is present; vanilla fertile islands omit the tag.
        return not self.fertility_guids

    def set_fertilities(self, guids: List[int]) -> None:
        """Empty list = let the game roll the island's FertilitySet."""
        el = self.el
        fg = el.find("FertilityGuids")
        if fg is None:
            fg = ET.Element("FertilityGuids")
            el.insert(list(el).index(el.find("Rotation90")) + 1, fg)
        rf = el.find("RandomizeFertilities")
        if guids:
            fg.text = " ".join(str(g) for g in guids)
            if rf is None:
                rf = ET.Element("RandomizeFertilities")
                anchor = el.find("FertilitiesPerAreaIndex")
                idx = list(el).index(anchor) + 1 if anchor is not None else list(el).index(fg) + 1
                el.insert(idx, rf)
            rf.text = "0"
        else:
            fg.text = "\n        "
            if rf is not None and self.is_fertile and not self._vanilla_had_randomize:
                el.remove(rf)

    _vanilla_had_randomize = False

    # ── layer ────────────────────────────────────────────────────────────────

    def set_layer_mode(self, mode: str) -> None:
        if self.is_spawn:
            return
        if mode == LAYER_REDUCED and not self.has_layer:
            mode = LAYER_FULL
        if mode == LAYER_AUTO and not self.can_auto_reduce:
            mode = LAYER_FULL
        self.layer_mode = mode
        info = self.info
        if info:
            self.el.find("MapFilePath").text = info.map_file


class EgyptTemplate:
    """The whole Aegyptus template: XML tree + element wrappers + removed complexes."""

    def __init__(self, tree: ET.ElementTree, source_path: Optional[str] = None):
        self.tree = tree
        self.source_path = source_path
        self.modified = False
        self._next_eid = 1
        self.elements: List[EgyptElement] = []
        # quadrant -> (removed element nodes in original order, their index in MapTemplate)
        self.removed: Dict[str, List[Tuple[int, ET.Element]]] = {}
        for te in self.mt.findall("TemplateElement"):
            e = EgyptElement(te, self._take_eid())
            e._vanilla_had_randomize = te.find("Element/RandomizeFertilities") is not None
            self.elements.append(e)

    def _take_eid(self) -> int:
        eid = self._next_eid
        self._next_eid += 1
        return eid

    # ── construction ─────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str) -> "EgyptTemplate":
        tree = ET.parse(path)
        if tree.getroot().find(".//MapTemplate") is None:
            raise ValueError("No <MapTemplate> element found in file.")
        t = cls(tree, source_path=path)
        if not t.looks_egyptian():
            raise ValueError("This is not an Aegyptus (DLC03) map template.")
        t._read_sidecar(path + SIDECAR_SUFFIX)
        return t

    @classmethod
    def vanilla(cls) -> "EgyptTemplate":
        t = cls.load(ed.VANILLA_TEMPLATE)
        t.source_path = None
        return t

    def looks_egyptian(self) -> bool:
        return any(e.base and e.base.startswith(ed.PREFIX) for e in self.elements)

    @property
    def mt(self) -> ET.Element:
        return self.tree.getroot().find(".//MapTemplate")

    @property
    def size(self) -> Tuple[int, int]:
        v = (self.mt.findtext("Size") or f"{ed.MAP_SIZE} {ed.MAP_SIZE}").split()
        return int(v[0]), int(v[1])

    @property
    def playable_area(self) -> Tuple[int, int, int, int]:
        v = (self.mt.findtext("PlayableArea") or "20 20 1890 1890").split()
        return int(v[0]), int(v[1]), int(v[2]), int(v[3])

    # ── queries ──────────────────────────────────────────────────────────────

    @property
    def islands(self) -> List[EgyptElement]:
        return [e for e in self.elements if not e.is_spawn]

    @property
    def spawns(self) -> List[EgyptElement]:
        return [e for e in self.elements if e.is_spawn]

    def by_eid(self, eid: int) -> Optional[EgyptElement]:
        return next((e for e in self.elements if e.eid == eid), None)

    def quadrant_elements(self, quadrant: str) -> List[EgyptElement]:
        return [e for e in self.elements if e.quadrant == quadrant]

    def present_quadrants(self) -> List[str]:
        return [q for q in ed.QUADRANTS if self.quadrant_elements(q)]

    def quadrant_offset(self, quadrant: str) -> Optional[Tuple[int, int]]:
        """How far a complex has been moved from its vanilla place, or None once its islands were
        moved or rotated one by one (they no longer share one offset)."""
        els = self.quadrant_elements(quadrant)
        if not els:
            return (0, 0)
        vanilla = _vanilla_positions()
        offsets = set()
        for e in els:
            vx, vy = vanilla.get(e.base, e.position)
            offsets.add((e.position[0] - vx, e.position[1] - vy))
        if len(offsets) != 1 or any(e.rotation for e in els):
            return None
        return offsets.pop()

    def quadrant_intact(self, quadrant: str) -> bool:
        return self.quadrant_offset(quadrant) is not None

    def quadrant_rect(self, quadrant: str) -> Tuple[int, int, int, int]:
        """The complex's extent: its vanilla 960 square while intact, else the box around its territories."""
        off = self.quadrant_offset(quadrant)
        if off is not None:
            ox, oy = ed.quadrant_origin(quadrant)
            return (ox + off[0], oy + off[1], ox + off[0] + ed.QUADRANT_SIZE, oy + off[1] + ed.QUADRANT_SIZE)
        rects = [r for r in (e.active_world_rect() for e in self.quadrant_elements(quadrant)) if r]
        return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))

    def element_at(self, gx: float, gy: float) -> Optional[EgyptElement]:
        # Small pieces first so a deco inside a larger territory's bounding box still wins.
        for e in sorted(self.islands, key=lambda i: _area(i.active_world_rect())):
            if e.contains(gx, gy):
                return e
        return None

    def quadrant_at(self, gx: float, gy: float) -> Optional[str]:
        for q in self.present_quadrants():
            x0, y0, x1, y1 = self.quadrant_rect(q)
            if x0 <= gx < x1 and y0 <= gy < y1:
                return q
        return None

    # ── complex editing ──────────────────────────────────────────────────────

    def move_quadrant(self, quadrant: str, dx: int, dy: int) -> None:
        for e in self.quadrant_elements(quadrant):
            x, y = e.position
            e.position = (x + dx, y + dy)
        self.modified = True

    def can_place_quadrant(self, quadrant: str, dx: int, dy: int) -> bool:
        x0, y0, x1, y1 = self.quadrant_rect(quadrant)
        x0, y0, x1, y1 = x0 + dx, y0 + dy, x1 + dx, y1 + dy
        w, h = self.size
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
            return False
        for q in self.present_quadrants():
            if q == quadrant:
                continue
            a0, b0, a1, b1 = self.quadrant_rect(q)
            if x0 < a1 and a0 < x1 and y0 < b1 and b0 < y1:
                return False
        return True

    # ── single-island editing ────────────────────────────────────────────────

    def can_place_element(self, e: EgyptElement, dx: int = 0, dy: int = 0, rot: Optional[int] = None) -> bool:
        """Inside the map and no territory cell shared with another island."""
        r = e.active_world_rect(dx, dy, rot)
        if r is None:
            return False
        w, h = self.size
        if r[0] < 0 or r[1] < 0 or r[2] > w or r[3] > h:
            return False
        cells = None
        for o in self.islands:
            if o is e:
                continue
            orr = o.active_world_rect()
            if not orr or orr[2] <= r[0] or r[2] <= orr[0] or orr[3] <= r[1] or r[3] <= orr[1]:
                continue
            if cells is None:
                cells = e.world_cells(dx, dy, rot)
            if cells & o.world_cells():
                return False
        return True

    def move_element(self, e: EgyptElement, dx: int, dy: int) -> None:
        x, y = e.position
        e.position = (x + dx, y + dy)
        self.modified = True

    def rotate_element(self, e: EgyptElement, turns: int) -> None:
        e.rotation = e.rotation + turns
        self.modified = True

    def remove_quadrant(self, quadrant: str) -> None:
        mt = self.mt
        nodes = list(mt)
        removed = []
        for e in self.quadrant_elements(quadrant):
            removed.append((nodes.index(e.node), e.node))
        for _i, node in removed:
            mt.remove(node)
        self.elements = [e for e in self.elements if e.quadrant != quadrant]
        self.removed[quadrant] = removed
        self._update_count()
        self.modified = True

    def restore_quadrant(self, quadrant: str) -> None:
        """Put a removed complex back at its vanilla place (with its edited fields)."""
        removed = self.removed.pop(quadrant, None)
        if not removed:
            return
        mt = self.mt
        vanilla = _vanilla_positions()
        for idx, node in sorted(removed, key=lambda t: t[0]):
            mt.insert(min(idx, len(mt)), node)
            e = EgyptElement(node, self._take_eid())
            e._vanilla_had_randomize = node.find("Element/RandomizeFertilities") is not None
            mf = node.find("Element/MapFilePath").text
            e.layer_mode = LAYER_REDUCED if ed.stem_of(mf).endswith(ed.LAYER_SUFFIX) else e.layer_mode
            if e.base in vanilla:
                e.position = vanilla[e.base]
            e.rotation = 0
            self.elements.append(e)
        order = {id(n): i for i, n in enumerate(mt)}
        self.elements.sort(key=lambda e: order.get(id(e.node), 0))
        self._update_count()
        self.modified = True

    def _update_count(self) -> None:
        cnt = self.mt.find("ElementCount")
        if cnt is not None:
            cnt.text = str(len(self.mt.findall("TemplateElement")))

    # ── export helpers ───────────────────────────────────────────────────────

    def reduce_size_exclusions(self) -> List[str]:
        """Island file names (full .a7m stems) that must leave ReduceSizeIslands: every fixed choice,
        and every island of a removed complex."""
        out = [e.base for e in self.islands if e.can_auto_reduce and e.layer_mode != LAYER_AUTO]
        for q, removed in self.removed.items():
            for _i, node in removed:
                out.append(ed.base_stem(ed.stem_of(node.find("Element/MapFilePath").text)))
        return out

    def warnings(self) -> List[str]:
        w = []
        # Vanilla land already spans 0..1920 around the 20..1890 playable area, so only a complex moved
        # beyond that frame puts islands where the game does not expect them.
        frame = 2 * ed.QUADRANT_SIZE
        for q in self.present_quadrants():
            x0, y0, x1, y1 = self.quadrant_rect(q)
            if x0 < 0 or y0 < 0 or x1 > frame or y1 > frame:
                w.append(f"The {ed.quadrant_label(q)} complex lies outside the vanilla land area "
                         f"(0-{frame}); parts of it are outside the playable area.")
        loose = [q for q in self.present_quadrants() if not self.quadrant_intact(q)]
        if loose:
            w.append("Islands were moved or rotated on their own in the "
                     + ", ".join(ed.quadrant_label(q) for q in loose)
                     + " complex(es): island borders cut through land, so expect straight coastlines and seams.")
        if not self.spawns:
            w.append("There is no ship spawn point.")
        starters = [e for e in self.islands if e.is_starter]
        if len(starters) < 4:
            w.append(f"Only {len(starters)} starter islands (the vanilla map has 4).")
        if self.removed:
            w.append("Removed complexes may take NPC islands (villages, trader, pirate) with them; "
                     "their preplaced participants then have no island.")
        return w

    # ── persistence ──────────────────────────────────────────────────────────

    def to_xml_string(self) -> str:
        root = copy.deepcopy(self.tree.getroot())
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode")

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_xml_string())
        self._write_sidecar(path + SIDECAR_SUFFIX)
        self.source_path = path
        self.modified = False

    def _write_sidecar(self, path: str) -> None:
        data = {"layer_modes": {e.base: e.layer_mode for e in self.islands},
                "removed": {q: [ET.tostring(n, encoding="unicode") for _i, n in r] for q, r in self.removed.items()},
                "removed_index": {q: [i for i, _n in r] for q, r in self.removed.items()}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)

    def _read_sidecar(self, path: str) -> None:
        if not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        for e in self.islands:
            mode = data.get("layer_modes", {}).get(e.base)
            if mode in (LAYER_AUTO, LAYER_FULL, LAYER_REDUCED):
                e.layer_mode = mode
        for q, nodes in data.get("removed", {}).items():
            idx = data.get("removed_index", {}).get(q, [len(self.elements)] * len(nodes))
            self.removed[q] = [(i, ET.fromstring(n)) for i, n in zip(idx, nodes)]

    # ── undo ─────────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {"xml": ET.tostring(self.tree.getroot(), encoding="unicode"),
                "modes": {e.base: e.layer_mode for e in self.islands},
                "removed": {q: [(i, ET.tostring(n, encoding="unicode")) for i, n in r] for q, r in self.removed.items()}}

    def restore(self, snap: dict) -> None:
        self.tree = ET.ElementTree(ET.fromstring(snap["xml"]))
        self.elements = []
        for te in self.mt.findall("TemplateElement"):
            e = EgyptElement(te, self._take_eid())
            e._vanilla_had_randomize = _vanilla_randomize().get(e.base, False)
            if e.base in snap["modes"]:
                e.layer_mode = snap["modes"][e.base]
            self.elements.append(e)
        self.removed = {q: [(i, ET.fromstring(n)) for i, n in r] for q, r in snap["removed"].items()}
        self.modified = True


_ROT_CELLS: Dict[Tuple[str, int], list] = {}


def _rotated_cells(info: ed.IslandFile, rot: int) -> list:
    key = (info.stem, rot % 4)
    if key not in _ROT_CELLS:
        _ROT_CELLS[key] = info.rotated_cells(rot)
    return _ROT_CELLS[key]


def _area(rect) -> int:
    if not rect:
        return 1 << 30
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


_VANILLA_POS: Optional[Dict[str, Tuple[int, int]]] = None
_VANILLA_RAND: Optional[Dict[str, bool]] = None


def _vanilla_positions() -> Dict[str, Tuple[int, int]]:
    global _VANILLA_POS, _VANILLA_RAND
    if _VANILLA_POS is None:
        _VANILLA_POS, _VANILLA_RAND = {}, {}
        if os.path.isfile(ed.VANILLA_TEMPLATE):
            root = ET.parse(ed.VANILLA_TEMPLATE).getroot()
            for te in root.iter("TemplateElement"):
                mf = te.find("Element/MapFilePath")
                if mf is None:
                    continue
                b = ed.base_stem(ed.stem_of(mf.text))
                x, y = te.find("Element/Position").text.split()
                _VANILLA_POS[b] = (int(x), int(y))
                _VANILLA_RAND[b] = te.find("Element/RandomizeFertilities") is not None
    return _VANILLA_POS


def _vanilla_randomize() -> Dict[str, bool]:
    _vanilla_positions()
    return _VANILLA_RAND or {}
