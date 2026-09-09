"""
Anno 117 Map Template Editor - FileDBReader Integration

Wraps the FileDBReader CLI tool to decompress binary .a7tinfo files to plain
XML and to compress edited XML back to the binary format.

FileDBReader: https://github.com/anno-mods/FileDBReader
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))


import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional

import config


# ─── Discovery ───────────────────────────────────────────────────────────────

def find_filedb() -> Optional[str]:
    """Return the path to FileDBReader if discoverable, else None."""
    # Check candidates
    for candidate in config.FILEDB_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # Fall back to PATH
    name = "FileDBReader.exe" if config.IS_WINDOWS else "FileDBReader"
    found = shutil.which(name)
    return found


def find_anno_install() -> Optional[str]:
    """Return the first discovered Anno installation folder, or None."""
    for path in config.ANNO_INSTALL_CANDIDATES:
        if os.path.isdir(path):
            return path
    return None


# ─── Run helpers ─────────────────────────────────────────────────────────────

class FileDBError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int = 60,
         cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    _flags = subprocess.CREATE_NO_WINDOW if config.IS_WINDOWS else 0
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            creationflags=_flags,
        )
    except FileNotFoundError:
        raise FileDBError(
            f"FileDBReader not found at '{cmd[0]}'.\n"
            "Download it from https://github.com/anno-mods/FileDBReader/releases."
            "Use Edit › Set FileDBReader Path…  to configure it manually."
        )
    except subprocess.TimeoutExpired:
        raise FileDBError("FileDBReader timed out.")

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        raise FileDBError(f"FileDBReader failed (exit {result.returncode}):\n{msg}")

    return result


# FileDBReader catches its own exceptions, prints them, and still exits 0,
# leaving a zero-byte output behind.  Work built from that looks like it
# succeeded and is silently broken, so scan the output as well as the exit code.
_TOOL_ERROR_MARKERS = ("exception occured", "exception was thrown",
                       "outofmemory", "unhandled")


def _check_tool_output(result: subprocess.CompletedProcess, what: str) -> None:
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    lowered = text.lower()
    for marker in _TOOL_ERROR_MARKERS:
        if marker in lowered:
            detail = next((ln.strip() for ln in text.splitlines()
                           if marker in ln.lower()), marker)
            raise FileDBError(
                f"FileDBReader reported an error while {what} "
                f"(it exits 0 even on failure):\n{detail}")


# ─── Public API ───────────────────────────────────────────────────────────────

def decompress(
    a7tinfo_path: str,
    filedb_path: Optional[str] = None,
    interpreter_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Decompress a binary .a7tinfo file to a plain XML file.

    Returns the path to the output XML file.
    Raises FileDBError on failure.
    """
    filedb = filedb_path or find_filedb()
    if not filedb:
        raise FileDBError(
            "FileDBReader not found. Use Edit › Set FileDBReader Path…  to configure it manually."
        )

    interp = interpreter_path or config.INTERPRETER_PATH
    if not os.path.isfile(interp):
        raise FileDBError(
            f"Interpreter file not found:\n{interp}\n"
            "Make sure data/interpreter/a7tinfo.xml is present."
        )

    # FileDBReader writes output next to the input file with .xml extension.
    # We copy the source to a temp dir first so the .xml lands there too, keeping the original untouched.
    tmp_dir = tempfile.mkdtemp(prefix="anno117_")
    stem = Path(a7tinfo_path).stem
    tmp_input = os.path.join(tmp_dir, Path(a7tinfo_path).name)
    import shutil as _shutil
    _shutil.copy2(a7tinfo_path, tmp_input)

    expected_xml = os.path.join(tmp_dir, f"{stem}.xml")

    cmd = [
        filedb,
        "decompress",
        "-f", tmp_input,
        "-i", interp,
    ]

    _check_tool_output(_run(cmd, cwd=tmp_dir), "decompressing")

    if os.path.isfile(expected_xml):
        if output_path and output_path != expected_xml:
            _shutil.move(expected_xml, output_path)
            return output_path
        return expected_xml

    # Fallback: scan for any .xml produced in the temp dir (excluding our input copy)
    xmls = [
        f for f in os.listdir(tmp_dir)
        if f.endswith(".xml") and os.path.join(tmp_dir, f) != tmp_input
    ]
    if xmls:
        found = os.path.join(tmp_dir, xmls[0])
        if output_path:
            _shutil.move(found, output_path)
            return output_path
        return found

    raise FileDBError(
        f"FileDBReader ran but no XML output found in:\n{tmp_dir}"
    )


def compress(
    xml_path: str,
    output_path: str,
    filedb_path: Optional[str] = None,
    interpreter_path: Optional[str] = None,
) -> str:
    """
    Compress a plain XML file back to a binary .a7tinfo file.

    Returns the path to the output .a7tinfo file.
    Raises FileDBError on failure.
    """
    filedb = filedb_path or find_filedb()
    if not filedb:
        raise FileDBError(
            "FileDBReader not found. Use Edit › Set FileDBReader Path…  to configure it manually."
        )

    interp = interpreter_path or config.INTERPRETER_PATH
    if not os.path.isfile(interp):
        raise FileDBError(
            f"Interpreter file not found:\n{interp}"
        )

    import shutil as _shutil
    tmp_dir = tempfile.mkdtemp(prefix="anno117_")

    # Use a short name in tmp_dir so path length stays safe.
    # FileDBReader 2.x writes its output next to the input, using the
    # extension given by -o.  -c sets the compression version (2 = post-GU12).
    tmp_input  = os.path.join(tmp_dir, "input.xml")
    tmp_output = os.path.join(tmp_dir, "input.a7tinfo")
    _shutil.copy2(xml_path, tmp_input)

    cmd = [
        filedb,
        "compress",
        "-f", tmp_input,
        "-c", "2",
        "-i", interp,
        "-o", "a7tinfo",          # output file extension, not a path
    ]

    _check_tool_output(_run(cmd, cwd=tmp_dir), "compressing")

    if os.path.isfile(tmp_output):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        _shutil.move(tmp_output, output_path)
        return output_path

    raise FileDBError(
        f"FileDBReader ran but produced no output.\n"
        f"Temp dir contents: {os.listdir(tmp_dir)}"
    )


def decompress_from_game(
    game_path: str,
    relative_a7tinfo_path: str,
    filedb_path: Optional[str] = None,
) -> str:
    """
    Convenience: given a game installation folder and a relative path to a .a7tinfo inside it, decompress and return the path to the XML.
    """
    abs_path = os.path.join(game_path, relative_a7tinfo_path)
    if not os.path.isfile(abs_path):
        raise FileDBError(f"Map template not found:\n{abs_path}")
    return decompress(abs_path, filedb_path=filedb_path)