"""
Anno 117 Map Template Editor - RDA extraction wrapper
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import subprocess
import shutil
import glob
from typing import Optional, List

import config

_RDA_EXE = "RdaConsole.exe" if config.IS_WINDOWS else "RdaConsole"

# RDA_CANDIDATES = [
#     os.path.join(config.TOOLS_INSTALL_DIR, _RDA_EXE),
#     os.path.join(config.DATA_DIR, "..", "tools", _RDA_EXE),
#     os.path.join(".", "tools", _RDA_EXE),
# ]

# Only extract from these archives
RELEVANT_RDA_PATTERNS = [
    "provinces_celtic.rda",
    "provinces_roman.rda",
    "dlc01_provinces.rda",
    "config.rda"
]
# Also match any rda starting with "dlc01" (for future DLC content)
RELEVANT_RDA_PREFIX = ["dlc01"]

# Exit code 3762504530 (0xE0434352) = .NET unhandled exception on Console.Clear()
# This happens AFTER successful extraction when RdaConsole has no real console - safe to ignore
_NET_CONSOLE_EXIT_CODE = 3762504530

# Filters for what to extract
TEMPLATE_FILTER = r"\.a7tinfo"
CONFIG_FILTER   = r"data/base/config/export/.*\.xml"


def find_rda_console() -> Optional[str]:

    # Check candidates
    for candidate in config.RDACONSOLE_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # for c in RDA_CANDIDATES:
    #     if os.path.isfile(c):
    #         return c
    return shutil.which("RdaConsole.exe" if config.IS_WINDOWS else "RdaConsole")


def _is_relevant_rda(path: str) -> bool:
    name = os.path.basename(path).lower()
    if name in RELEVANT_RDA_PATTERNS:
        return True
    if any(name.startswith(p) for p in RELEVANT_RDA_PREFIX):
        return True
    return False


def _run_rda(cmd: list) -> None:
    """
    Run RdaConsole with its console window hidden.
    The exit code 3762504530 (.NET ConsolePal crash after extraction) is accepted as success.
    """
    quoted = " ".join(f'"{a}"' for a in cmd)
    print(f"[rda] Running: {quoted}")

    _kwargs: dict = {}
    if config.IS_WINDOWS:
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0  # SW_HIDE — console allocated but never shown
        _kwargs["startupinfo"] = _si

    result = subprocess.run(
        quoted,
        shell=True,
        stdin=None,
        stdout=None,
        stderr=None,
        timeout=300,
        **_kwargs,
    )
    print(f"[rda] Exit code: {result.returncode}")

    if result.returncode not in (0, _NET_CONSOLE_EXIT_CODE):
        raise RuntimeError(
            f"RdaConsole failed with exit code {result.returncode}.\n"
            f"Command: {quoted}"
        )


def extract_map_templates(game_path: str, output_path: str, rda_exe: Optional[str] = None, force: bool = False) -> List[str]:
    """
    Extract map template .a7tinfo files from the game's .rda archives.
    Uses a permanent cache - only re-extracts if force=True or cache is empty.
    Returns list of extracted .a7tinfo file paths.
    """
    exe = rda_exe or find_rda_console()
    if not exe:
        raise RuntimeError(
            "RdaConsole not found.\n"
            "Download from https://github.com/anno-mods/RdaConsole/releases. Use Edit › Set RDAConsole Path…  to configure it manually."
        )

    # Return cached results if available and not forcing re-extraction
    if not force:
        existing = scan_extracted_templates(output_path)
        if existing:
            print(f"[rda] Using {len(existing)} cached templates from {output_path}")
            return existing

    all_rdas = glob.glob(os.path.join(game_path, "**", "*.rda"), recursive=True)
    rda_files = [f for f in sorted(all_rdas) if _is_relevant_rda(f)]

    if not rda_files:
        raise RuntimeError(
            f"No relevant .rda files found in:\n{game_path}\n\n"
            f"Expected: provinces_celtic.rda, provinces_roman.rda, dlc01_*.rda"
        )

    print(f"[rda] Found {len(rda_files)} relevant archives: {[os.path.basename(f) for f in rda_files]}")

    os.makedirs(output_path, exist_ok=True)

    for rda_file in rda_files:
        for filt in (TEMPLATE_FILTER, CONFIG_FILTER):
            cmd = [exe, "extract",
                   "-f", rda_file,
                   "-o", output_path,
                   "-y",
                   "--filter", filt]
            try:
                _run_rda(cmd)
            except RuntimeError as e:
                print(f"[rda] Warning on {os.path.basename(rda_file)} (filter={filt}): {e}")

            found = glob.glob(
                os.path.join(output_path, "**", "*.a7tinfo"), recursive=True
            )
            print(f"[rda] After {os.path.basename(rda_file)}: {len(found)} .a7tinfo files in output")

    results = sorted(glob.glob(
        os.path.join(output_path, "**", "*.a7tinfo"), recursive=True
    ))

    if not results:
        raise RuntimeError(
            "Extraction completed but no .a7tinfo files were found.\n"
            f"Output folder: {output_path}"
        )

    print(f"[rda] Extraction complete - {len(results)} templates found.")
    return results


def scan_extracted_templates(extracted_root: str) -> List[str]:
    """Scan an already-extracted folder for .a7tinfo map templates."""
    return sorted(glob.glob(
        os.path.join(extracted_root, "**", "*.a7tinfo"), recursive=True
    ))