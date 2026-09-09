"""
Anno 117 Map Template Editor - native FileDB reader/writer

FileDBReader is fine for the small .a7tinfo files, but the gamedata inside a
.a7t is a different scale: building one through it means handing it a
multi-hundred-MB XML document, which dominates export time and fails outright
past ~7000 map tiles (the XML exceeds .NET's maximum string length and it dies
with an OutOfMemoryException - while still exiting 0).  Terrain generation
therefore works on the binary directly.

Format (both versions the game uses)::

    node        <size:u32><id:u32>[payload]   payload padded to a multiple of 8
                size == 0, id != 0   open tag
                size == 0, id == 0   close tag
                id & 0x8000          attribute, otherwise a tag
    dictionary  <count:u32><count x id:u16><count x name NUL>, padded to 8
    trailer     v-2: <tagDictOff><attrDictOff><8><-2>                    16 bytes
                v-3: <namedNodes+1><tagDictOff><attrDictOff><8><-3>      20 bytes

The padding in front of the trailer is chosen so the file ends on a multiple of
8, so it depends on which trailer the version uses.  `namedNodes` counts every
attribute and every opening tag, plus one for the implicit root.

.a7tinfo files are v-2, .a7t gamedata is v-3; parse() and build() round-trip
both byte-for-byte.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import struct
from typing import Dict, List, Tuple

OPEN = "open"
CLOSE = "close"
ATTR = "attr"

SUPPORTED_VERSIONS = (-2, -3)

# Offsets and node sizes are u32, so a document cannot exceed 4 GB.
MAX_DOCUMENT_SIZE = 2 ** 32

# (kind, id, payload) - payload is always b"" for open and close nodes.
Node = Tuple[str, int, bytes]


class FileDBFormatError(RuntimeError):
    """Raised for malformed input or output that cannot be represented."""


def _pad8(n: int) -> int:
    return (-n) % 8


class FileDB:
    """A parsed FileDB document: a flat node list plus its two name tables."""

    def __init__(self, nodes: List[Node], tags: Dict[int, str],
                 attrs: Dict[int, str], version: int):
        self.nodes = nodes
        self.tags = tags
        self.attrs = attrs
        self.version = version

    def tag_id(self, name: str) -> int:
        """Numeric id of the tag called *name*."""
        for node_id, known in self.tags.items():
            if known == name:
                return node_id
        raise FileDBFormatError(f"No tag named {name!r} in this document.")

    def attr_id(self, name: str) -> int:
        """Numeric id of the attribute called *name*."""
        for node_id, known in self.attrs.items():
            if known == name:
                return node_id
        raise FileDBFormatError(f"No attribute named {name!r} in this document.")

    def matching_close(self, start: int) -> int:
        """Index of the close node that ends the element opened at *start*."""
        depth = 0
        for i in range(start, len(self.nodes)):
            kind = self.nodes[i][0]
            if kind == OPEN:
                depth += 1
            elif kind == CLOSE:
                depth -= 1
                if depth == 0:
                    return i
        raise FileDBFormatError(f"Element opened at node {start} is never closed.")


def parse(data: bytes) -> FileDB:
    """Parse a FileDB document."""
    if len(data) < 16:
        raise FileDBFormatError("Too short to be a FileDB document.")

    version = struct.unpack_from("<i", data, len(data) - 4)[0]
    if version not in SUPPORTED_VERSIONS:
        raise FileDBFormatError(
            f"Unsupported FileDB version {version} "
            f"(known: {', '.join(str(v) for v in SUPPORTED_VERSIONS)}).")

    # Both layouts put the two dictionary offsets in the same place: the extra
    # v-3 count sits in front of them, not between them and the end of the file.
    tag_off, attr_off = struct.unpack_from("<II", data, len(data) - 16)

    def read_dict(off: int) -> Dict[int, str]:
        count = struct.unpack_from("<I", data, off)[0]
        ids = struct.unpack_from(f"<{count}H", data, off + 4)
        pos = off + 4 + 2 * count
        names: Dict[int, str] = {}
        for node_id in ids:
            end = data.index(b"\0", pos)
            names[node_id] = data[pos:end].decode("utf-8")
            pos = end + 1
        return names

    tags, attrs = read_dict(tag_off), read_dict(attr_off)

    nodes: List[Node] = []
    pos = 0
    while pos < tag_off:
        size, node_id = struct.unpack_from("<II", data, pos)
        pos += 8
        if size == 0:
            nodes.append((CLOSE if node_id == 0 else OPEN, node_id, b""))
        else:
            nodes.append((ATTR, node_id, data[pos:pos + size]))
            pos += size + _pad8(size)

    return FileDB(nodes, tags, attrs, version)


def build(doc: FileDB) -> bytes:
    """Serialise a document back to bytes."""
    out = bytearray()
    for kind, node_id, payload in doc.nodes:
        if kind == ATTR:
            out += struct.pack("<II", len(payload), node_id)
            out += payload
            out += bytes(_pad8(len(payload)))
        else:
            out += struct.pack("<II", 0, 0 if kind == CLOSE else node_id)

    # The dictionaries are addressed by u32 offsets, so the node stream that
    # precedes them has to fit.  Two height maps of (2*S+1)^2 int16 samples
    # reach the limit just under a map size of 16384.
    if len(out) >= MAX_DOCUMENT_SIZE:
        raise FileDBFormatError(
            f"Document is {len(out) / 2 ** 30:.2f} GB; the FileDB format "
            f"addresses at most 4 GB (offsets are 32-bit). Use a smaller map size.")

    def write_dict(table: Dict[int, str]) -> int:
        off = len(out)
        out.extend(struct.pack("<I", len(table)))
        for node_id in table:
            out.extend(struct.pack("<H", node_id))
        for name in table.values():
            out.extend(name.encode("utf-8") + b"\0")
        out.extend(bytes(_pad8(len(out))))
        return off

    tag_off = write_dict(doc.tags)
    attr_off = write_dict(doc.attrs)

    trailer_size = 20 if doc.version == -3 else 16
    out += bytes(_pad8(len(out) + trailer_size))
    if doc.version == -3:
        named = sum(1 for kind, _, _ in doc.nodes if kind != CLOSE)
        out += struct.pack("<I", named + 1)
    out += struct.pack("<IIIi", tag_off, attr_off, 8, doc.version)
    return bytes(out)
