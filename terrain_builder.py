"""
Anno 117 Map Template Editor - .a7t / .a7te generation for arbitrary map sizes

The map size lives in four places, not one:

  * .a7tinfo  - Size / PlayableArea; this is what TAMPER has always written.
  * .a7te     - the editor level: Dimensions and a chunk grid.
  * .a7t      - the session: TerrainManager/WorldSize, two height maps sized
                2*S+1 square, an AreaIDs block grid, and its own PlayableArea.
  * assets.xml - each MapTemplate asset's HorizonIslands: the backdrop scenery,
                placed at absolute world coordinates (see scale_horizon_islands).

The exporter used to copy pre-baked .a7t/.a7te files, so a map larger than the
bundled 2048 (or 2688 "enlarged") template kept a 2048 world: islands were placed
outside it and the backdrop stayed where the smaller world ended.  This module
regenerates all of it for the requested size instead.

The .a7t is produced by editing the template's FileDB tree directly (filedb_io)
rather than round-tripping it through FileDBReader's XML, which is both far
faster and the only way to build maps beyond ~7000 tiles.

Everything except the size-dependent nodes is taken verbatim from the bundled
template of the same region, so region flavour (ambient, vegetation set, camera
bookmarks) is preserved.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import re
import struct
from typing import Callable, Optional, Tuple

import filedb_io
import rda_writer

_OPEN, _CLOSE, _ATTR = filedb_io.OPEN, filedb_io.CLOSE, filedb_io.ATTR

# .a7te splits the map into fixed 64x64 chunks, so the side length must divide by 64.
CHUNK_SIZE = 64

# AreaIDs is a grid of 16x16 blocks covering the whole world.
AREA_BLOCK = 16

# Below this the playable area leaves no room worth designing on.
MIN_SIZE = 512


def heightmap_dim(size: int) -> int:
    """Height map side length: two samples per world tile, plus the far edge."""
    return 2 * size + 1


class TerrainBuildError(RuntimeError):
    """Raised for a map size or a template that terrain cannot be built from."""


def terrain_size_for(map_size: int) -> int:
    """
    Round an .a7tinfo Size up to the .a7te chunk grid.

    The two need not be equal: the vanilla enlarged Latium a7tinfo carries a Size
    of 2040 and ships with a 2048 world, so rounding up matches what the game
    already expects.
    """
    return -(-map_size // CHUNK_SIZE) * CHUNK_SIZE


def validate_size(size: int) -> None:
    if size % CHUNK_SIZE:
        raise TerrainBuildError(
            f"Map size must be a multiple of {CHUNK_SIZE} (.a7te chunk grid); got {size}.")
    if size < MIN_SIZE:
        raise TerrainBuildError(
            f"Map size {size} is too small; {MIN_SIZE} is the practical minimum.")


# ─── .a7te ────────────────────────────────────────────────────────────────────

def build_a7te(size: int) -> str:
    """
    Return the editor level (.a7te) XML for a square map of *size* tiles.

    Plain XML, no FileDB involved.  The chunk list is column-major: one <Column>
    per x, holding every y for that column, each named "<x>x<y>".
    """
    validate_size(size)
    n = size // CHUNK_SIZE

    out = [
        "<AnnoEditorLevel>",
        "  <FileVersion>4</FileVersion>",
        "  <ScenarioGuid>0</ScenarioGuid>",
        "  <Dimensions>",
        f"    <X>{size}</X>",
        f"    <Z>{size}</Z>",
        "  </Dimensions>",
        "  <ChunkSize>",
        f"    <X>{CHUNK_SIZE}</X>",
        f"    <Z>{CHUNK_SIZE}</Z>",
        "  </ChunkSize>",
        "  <Chunks>",
    ]
    for col in range(n):
        out.append("    <Column>")
        out.extend(f"      <Chunk>{col}x{row}</Chunk>" for row in range(n))
        out.append("    </Column>")
    out += ["  </Chunks>", "</AnnoEditorLevel>"]
    return "\r\n".join(out)


# ─── .a7t ─────────────────────────────────────────────────────────────────────
#
# Built by editing the template's FileDB node tree directly (see filedb_io).
# The earlier route through FileDBReader's XML cost ~85% of export time, lost the
# distinction between AreaIDs block modes 1 and 2 (both serialise as "True"), and
# could not build past ~7000 tiles at all.

# Grids whose payload is sized off the map and, in a blank template, is all
# zeroes.  Parent tag -> (payload attribute, value for <x>/<y>, payload bytes).
#   Water / RiverGrid / FordGrid - one bit per world tile
#   EnvironmentGRid              - one byte per 4x4 tile block
_ZERO_GRIDS = {
    "Water":           ("bits", lambda s: s,      lambda s: s * s // 8),
    "RiverGrid":       ("bits", lambda s: s,      lambda s: s * s // 8),
    "FordGrid":        ("bits", lambda s: s,      lambda s: s * s // 8),
    "EnvironmentGRid": ("val",  lambda s: s // 4, lambda s: (s // 4) ** 2),
}

_HEIGHTMAP_PARENTS = ("HeightMap", "DisplacementHeightMap")

# AreaIDs block <mode>: 1 marks the leading block that carries the block
# dimensions, 2 an ordinary grid cell, 0 the terminator.
_MODE_HEADER, _MODE_CELL, _MODE_END = 1, 2, 0


def _build_area_ids(doc: filedb_io.FileDB, size: int) -> list:
    """
    Rebuild the AreaIDs element for *size*: a leading block carrying the block
    dimensions, then (size/16)^2 cells in row-major order, then a terminator.
    Coordinates equal to zero are omitted, exactly as the game writes them.
    """
    t_area, t_block = doc.tag_id("AreaIDs"), doc.tag_id("block")
    a_sparse = doc.attr_id("SparseEnabled")
    a_x, a_y = doc.attr_id("x"), doc.attr_id("y")
    a_mode, a_default = doc.attr_id("mode"), doc.attr_id("default")

    out = [(_OPEN, t_area, b""),
           (_ATTR, a_sparse, b"\x01"),
           (_ATTR, a_x, struct.pack("<I", size)),
           (_ATTR, a_y, struct.pack("<I", size))]

    def block(mode: int, x=None, y=None, default=None) -> None:
        out.append((_OPEN, t_block, b""))
        out.append((_ATTR, a_mode, struct.pack("<B", mode)))
        # A coordinate of zero is left out entirely, and so is a missing one.
        if x:
            out.append((_ATTR, a_x, struct.pack("<H", x)))
        if y:
            out.append((_ATTR, a_y, struct.pack("<H", y)))
        if default is not None:
            out.append((_ATTR, a_default, struct.pack("<H", default)))
        out.append((_CLOSE, 0, b""))

    block(_MODE_HEADER, AREA_BLOCK, AREA_BLOCK, 0)
    n = size // AREA_BLOCK
    for row in range(n):
        for col in range(n):
            block(_MODE_CELL, col * AREA_BLOCK, row * AREA_BLOCK, 1)
    block(_MODE_END)

    out.append((_CLOSE, 0, b""))
    return out


def _resize_document(doc: filedb_io.FileDB, size: int,
                     playable_area: Tuple[int, int, int, int]) -> None:
    """Rewrite every size-dependent node of *doc* in place for a square map."""
    dim = heightmap_dim(size)
    t_area = doc.tag_id("AreaIDs")
    seen = {"pa": 0, "world": 0, "area": 0, "hm": 0, "grid": 0}

    nodes, out, stack = doc.nodes, [], []
    i = 0
    while i < len(nodes):
        kind, node_id, payload = nodes[i]

        if kind == _OPEN and node_id == t_area:
            seen["area"] += 1
            out.extend(_build_area_ids(doc, size))
            i = doc.matching_close(i) + 1
            continue

        if kind == _OPEN:
            stack.append(doc.tags.get(node_id, ""))
        elif kind == _CLOSE:
            if stack:
                stack.pop()
        else:
            name = doc.attrs.get(node_id, "")
            parent = stack[-1] if stack else ""
            grid = _ZERO_GRIDS.get(parent)

            if name == "WorldSize":
                seen["world"] += 1
                payload = struct.pack("<II", size, size)
            elif name == "PlayableArea":
                seen["pa"] += 1
                payload = struct.pack("<IIII", *playable_area)
            elif parent in _HEIGHTMAP_PARENTS:
                if name in ("Width", "Height"):
                    payload = struct.pack("<I", dim)
                elif name == "HeightMap":
                    seen["hm"] += 1
                    payload = bytes(dim * dim * 2)
            elif grid:
                payload_attr, coord_of, cells_of = grid
                if name in ("x", "y"):
                    payload = struct.pack("<I", coord_of(size))
                elif name == payload_attr:
                    seen["grid"] += 1
                    payload = bytes(cells_of(size))

        out.append((kind, node_id, payload))
        i += 1

    expected = {"pa": 1, "world": 1, "area": 1, "hm": 2, "grid": len(_ZERO_GRIDS)}
    if seen != expected:
        raise TerrainBuildError(
            f"Terrain template did not have the expected shape: found {seen}, "
            f"expected {expected}. The bundled .a7t may have changed.")

    doc.nodes = out


# ─── assets.xml HorizonIslands ────────────────────────────────────────────────
#
# The mountains on the horizon are not terrain - the .a7t height maps are all
# zeroes.  They are HorizonIslands: models listed on each MapTemplate asset in
# assets.xml at absolute world coordinates, the same coordinate space islands use
# (origin at the map corner).  The bundled template inherits vanilla's placements,
# which sit in X[-1500, 5000] / Z[-2500, 5000] around a 2048 world.
#
# Leave them alone on a bigger map and the world grows out to meet them, so the
# backdrop ends up sitting on top of the play area.  Scaling every coordinate by
# size/2048 fixes that: scaling about the world origin also scales about the map
# centre (old centre S/2 maps to S*r/2, the new centre), so the whole backdrop
# keeps its arrangement relative to the map.  Scale is scaled by the same factor,
# so an island twice as far away is drawn twice as large and subtends the same
# angle - the view stays exactly as it looks in vanilla.
#
# Vanilla itself does not do this for its 2688 "enlarged" maps; it just adds three
# more horizon islands to the same placements. That is a much smaller jump than
# 4096, where the difference is plainly visible.

HORIZON_BASE_SIZE = 2048

_ASSET_RE = re.compile(r"<Asset>.*?</Asset>", re.S)
_POOL_STEM_RE = re.compile(r"<(Enlarged)?TemplateFilename>[^<]*?/pool/([^/<]+)/")
_POSITION_RE = re.compile(
    r"(<X>)(-?[\d.]+)(</X>\s*<Y>)(-?[\d.]+)(</Y>\s*<Z>)(-?[\d.]+)(</Z>)", re.S)
_SCALE_RE = re.compile(r"(<Scale>)([\d.]+)(</Scale>)")


def _scale_number(text: str, ratio: float) -> str:
    """Scale one numeric field, keeping vanilla's integer formatting."""
    return str(int(round(float(text) * ratio)))


def _scale_block(block: str, ratio: float) -> str:
    def pos(m):
        return (m.group(1) + _scale_number(m.group(2), ratio) +
                m.group(3) + _scale_number(m.group(4), ratio) +
                m.group(5) + _scale_number(m.group(6), ratio) + m.group(7))

    def scale(m):
        # Never let an island collapse to nothing on a shrunken map.
        return m.group(1) + str(max(1, int(round(float(m.group(2)) * ratio)))) + m.group(3)

    return _SCALE_RE.sub(scale, _POSITION_RE.sub(pos, block))


def _scale_named_list(asset: str, tag: str, ratio: float) -> str:
    open_tag, close_tag = f"<{tag}>", f"</{tag}>"
    start = asset.find(open_tag)
    if start < 0:
        return asset
    end = asset.find(close_tag, start)
    if end < 0:
        return asset
    inner_start = start + len(open_tag)
    return (asset[:inner_start]
            + _scale_block(asset[inner_start:end], ratio)
            + asset[end:])


def scale_horizon_islands(assets_text: str, size_by_stem: dict) -> str:
    """
    Rewrite the HorizonIslands of every MapTemplate asset in *assets_text* for
    the map size that asset's template was actually built at.

    *size_by_stem* maps a pool folder stem (``mymod_latium_easy``, and the
    ``..._enlarged`` variants) to its terrain size.  Assets whose stem is not in
    the mapping are left untouched.
    """
    def fix(match):
        asset = match.group(0)

        # EnlargedHorizonIslands belongs to EnlargedTemplateFilename, which is a
        # different map size than the asset's base template.
        for enlarged, stem in _POOL_STEM_RE.findall(asset):
            size = size_by_stem.get(stem)
            if not size:
                continue
            ratio = size / HORIZON_BASE_SIZE
            if abs(ratio - 1.0) < 1e-9:
                continue
            asset = _scale_named_list(
                asset,
                "EnlargedHorizonIslands" if enlarged else "HorizonIslands",
                ratio)
        return asset

    return _ASSET_RE.sub(fix, assets_text)


def build_a7t(template_a7t_path: str, size: int,
              playable_area: Tuple[int, int, int, int],
              progress: Optional[Callable[[str], None]] = None) -> bytes:
    """
    Build a .a7t for a square map of *size* with the given PlayableArea, taking
    everything that does not depend on the size from *template_a7t_path* (the
    bundled template of the same region).

    Returns the finished .a7t bytes.
    """
    validate_size(size)

    def step(msg: str) -> None:
        if progress:
            progress(msg)

    step(f"Reading {size}x{size} terrain template...")
    with open(template_a7t_path, "rb") as f:
        doc = filedb_io.parse(rda_writer.read_a7t(f.read()))

    step(f"Generating {size}x{size} terrain ({heightmap_dim(size)}^2 height samples)...")
    _resize_document(doc, size, tuple(playable_area))

    step(f"Packing {size}x{size} terrain...")
    return rda_writer.write_a7t(filedb_io.build(doc))
