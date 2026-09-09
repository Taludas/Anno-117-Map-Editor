"""
Anno 117 Map Template Editor - RDA 2.2 container reader/writer

A .a7t is an RDA archive holding a single file, "gamedata.data".  RdaConsole can
extract those but its `pack` command writes the payload uncompressed (70 MB
instead of 340 KB for a 2048 map), so map building uses this module instead.

Layout of an RDA 2.2 archive::

    [0   :18 ]  b"Resource File V2.2"
    [18  :784]  zero padding
    [784 :792]  int64  offset of the first block header
    [792 :...]  file payloads, back to back (zlib-compressed if the block says so)
    [...      ]  file directory: one 560-byte entry per file, zlib-compressed as a whole
    [off :+32 ]  block header: flags u32, fileCount u32,
                 dirSizeCompressed u64, dirSizeUncompressed u64, nextBlock u64

Directory entry (560 bytes)::

    [0  :520]  file name, UTF-16LE, zero padded
    [520:560]  int64 x5: payloadOffset, sizeCompressed, sizeUncompressed, mtime, flags

Only the single-block, single-file shape that Anno uses for .a7t is written here;
`read_rda` is deliberately a bit more permissive so it can verify what we wrote.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import struct
import zlib
from typing import Dict, List

MAGIC = b"Resource File V2.2"
HEADER_SIZE = 784           # magic + padding, before the first-block pointer
ENTRY_SIZE = 560
NAME_SIZE = 520
BLOCK_HEADER_SIZE = 32

FLAG_COMPRESSED = 1

_ZLIB_LEVEL = 9

# The shipped .a7t files start their zlib streams with "78 01" (FLEVEL=0,
# "fastest") yet are compressed far better than level 1 produces - RDAExplorer
# uses SharpZipLib, which reports that level regardless of the real setting.
# FLEVEL is advisory and ignored by every decompressor, so we compress at level 9
# and rewrite the two header bytes to match what the game normally sees.
# 0x78 0x01 is a valid header: (0x7801) % 31 == 0.
_ZLIB_HEADER = b"\x78\x01"


def _deflate(data: bytes) -> bytes:
    out = zlib.compress(data, _ZLIB_LEVEL)
    return _ZLIB_HEADER + out[2:]


class RdaError(RuntimeError):
    """Raised for a malformed archive or one that cannot be written."""


def _pack_entry(name: str, offset: int, size_c: int, size_u: int) -> bytes:
    raw = name.encode("utf-16-le")
    if len(raw) > NAME_SIZE:
        raise RdaError(f"File name too long for an RDA entry: {name!r}")
    return raw.ljust(NAME_SIZE, b"\0") + struct.pack("<QQQQQ", offset, size_c, size_u, 0, 0)


def write_rda(files: Dict[str, bytes], compress: bool = True) -> bytes:
    """
    Build a single-block RDA 2.2 archive from *files* ({archive name: content}).

    Names are stored verbatim, so use forward slashes for nested paths and a bare
    file name for archive-root entries.
    """
    if not files:
        raise RdaError("Refusing to write an RDA archive with no files.")

    out = bytearray(MAGIC.ljust(HEADER_SIZE, b"\0"))
    out += bytes(8)  # first-block pointer, backpatched once the offset is known

    entries: List[bytes] = []
    for name, content in files.items():
        payload = _deflate(content) if compress else content
        entries.append(_pack_entry(name, len(out), len(payload), len(content)))
        out += payload

    directory = b"".join(entries)
    stored_dir = _deflate(directory) if compress else directory

    block_offset = len(out) + len(stored_dir)
    out += stored_dir
    out += struct.pack(
        "<IIQQQ",
        FLAG_COMPRESSED if compress else 0,
        len(files),
        len(stored_dir),
        len(directory),
        block_offset + BLOCK_HEADER_SIZE,   # nextBlock == EOF marks the last block
    )
    struct.pack_into("<Q", out, HEADER_SIZE, block_offset)
    return bytes(out)


def read_rda(data: bytes) -> Dict[str, bytes]:
    """Return {archive name: decompressed content} for every file in *data*."""
    if not data.startswith(MAGIC):
        raise RdaError("Not an RDA 2.2 archive (magic mismatch).")

    files: Dict[str, bytes] = {}
    offset = struct.unpack_from("<Q", data, HEADER_SIZE)[0]
    seen: set = set()

    while 0 < offset < len(data) and offset not in seen:
        seen.add(offset)
        flags, count, size_c, size_u, nxt = struct.unpack_from(
            "<IIQQQ", data, offset)
        compressed = bool(flags & FLAG_COMPRESSED)

        raw = data[offset - size_c:offset]
        directory = zlib.decompress(raw) if compressed else raw
        if len(directory) != size_u:
            raise RdaError(
                f"Directory size mismatch: expected {size_u}, got {len(directory)}.")

        for i in range(count):
            base = i * ENTRY_SIZE
            name = directory[base:base + NAME_SIZE].decode("utf-16-le").rstrip("\0")
            f_off, f_c, f_u, _mtime, _fl = struct.unpack_from(
                "<QQQQQ", directory, base + NAME_SIZE)
            payload = data[f_off:f_off + f_c]
            files[name] = zlib.decompress(payload) if compressed else payload

        if nxt >= len(data):
            break
        offset = nxt

    return files


def write_a7t(gamedata: bytes) -> bytes:
    """Wrap raw FileDB *gamedata* bytes into the .a7t container shape Anno expects."""
    return write_rda({"gamedata.data": gamedata})


def read_a7t(data: bytes) -> bytes:
    """Return the "gamedata.data" payload of an .a7t archive."""
    files = read_rda(data)
    try:
        return files["gamedata.data"]
    except KeyError:
        raise RdaError(
            f"No gamedata.data in archive (found: {sorted(files)})") from None
