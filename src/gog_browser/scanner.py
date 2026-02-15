"""Discover GOG installers: setup_*.exe on disk or inside .rar archives."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

try:
    import rarfile
except ImportError:
    rarfile = None  # type: ignore

SETUP_PATTERN = re.compile(r"^setup_.*\.exe$", re.IGNORECASE)
RAR_EXT = ".rar"
PART_RAR_PATTERN = re.compile(r"\.part\d+\.rar$", re.IGNORECASE)


@dataclass
class InstallerEntry:
    """A single discovered installer (file or inside RAR)."""

    key: str  # Stable identity for metadata folder
    path_type: str  # "file" | "rar"
    fs_path: Path  # Path to .exe file or .rar archive
    internal_path: str | None  # If rar, name of exe inside archive
    display_name: str  # Derived name for GOG search (e.g. parent folder or rar basename)


def _sanitize_key(relative_path: str, internal: str | None = None) -> str:
    """Build a filesystem-safe key from path (and optional internal path)."""
    # Replace path separators and invalid chars with underscore
    key = relative_path.replace("\\", "_").replace("/", "_")
    for c in ':*?"<>|':
        key = key.replace(c, "_")
    if internal:
        key = key + "_" + internal.replace("\\", "_").replace("/", "_")
    return key.strip("_") or "unknown"


def _display_name_from_path(fs_path: Path, internal_path: str | None) -> str:
    """Derive a display name for GOG search."""
    if internal_path:
        # Use RAR stem (e.g. "Game_Name" from "Game_Name.part01.rar")
        stem = fs_path.stem
        if PART_RAR_PATTERN.search(fs_path.name):
            stem = re.sub(r"\.part\d+$", "", stem, flags=re.IGNORECASE)
        return stem.replace("_", " ").strip() or fs_path.name
    # Direct exe: use parent folder name
    parent = fs_path.parent
    if parent.name:
        return parent.name.replace("_", " ").strip()
    return fs_path.stem.replace("_", " ").strip() or "Unknown"


def _scan_direct(root: Path) -> Iterator[InstallerEntry]:
    """Find setup_*.exe files directly on the filesystem."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if SETUP_PATTERN.match(path.name):
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            key = _sanitize_key(str(rel), None)
            yield InstallerEntry(
                key=key,
                path_type="file",
                fs_path=path,
                internal_path=None,
                display_name=_display_name_from_path(path, None),
            )


def _is_first_rar_part(path: Path) -> bool:
    """True if this is a multi-part RAR we should open (e.g. .rar or .part01.rar)."""
    if path.suffix.lower() == RAR_EXT and path.name.lower().endswith(RAR_EXT):
        if PART_RAR_PATTERN.search(path.name):
            # part01.rar, part1.rar etc - only process part 1
            m = re.search(r"\.part(\d+)\.rar$", path.name, re.IGNORECASE)
            return m is not None and int(m.group(1)) == 1
        return True  # single .rar
    return False


def _scan_rar(root: Path, rar_path: Path) -> Iterator[InstallerEntry]:
    """List RAR contents and yield entries for setup_*.exe inside."""
    if rarfile is None:
        return
    try:
        rf = rarfile.RarFile(rar_path)
    except (rarfile.BadRarFile, rarfile.Error, OSError):
        return
    try:
        names = rf.namelist()
    except Exception:
        return
    for name in names:
        base = name.replace("\\", "/").split("/")[-1]
        if not SETUP_PATTERN.match(base):
            continue
        try:
            rel = rar_path.relative_to(root)
        except ValueError:
            continue
        key = _sanitize_key(str(rel), name)
        yield InstallerEntry(
            key=key,
            path_type="rar",
            fs_path=rar_path,
            internal_path=name,
            display_name=_display_name_from_path(rar_path, name),
        )


def _scan_rar_files(root: Path) -> Iterator[InstallerEntry]:
    """Find .rar (and first part) and list setup_*.exe inside."""
    seen_bases: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != RAR_EXT:
            continue
        if not _is_first_rar_part(path):
            continue
        # Avoid processing same logical archive twice (e.g. game.rar and game.part01.rar)
        base = path.stem
        if PART_RAR_PATTERN.search(path.name):
            base = re.sub(r"\.part\d+$", "", base, flags=re.IGNORECASE)
        if base in seen_bases:
            continue
        seen_bases.add(base)
        yield from _scan_rar(root, path)


def scan_installers(installer_root: Path) -> list[InstallerEntry]:
    """
    Recursively discover all GOG installers under installer_root.
    Returns list of InstallerEntry (direct setup_*.exe and setup_*.exe inside .rar).
    """
    installer_root = installer_root.resolve()
    if not installer_root.is_dir():
        return []
    entries: list[InstallerEntry] = []
    seen_keys: set[str] = set()
    for entry in _scan_direct(installer_root):
        if entry.key not in seen_keys:
            seen_keys.add(entry.key)
            entries.append(entry)
    for entry in _scan_rar_files(installer_root):
        if entry.key not in seen_keys:
            seen_keys.add(entry.key)
            entries.append(entry)
    return entries
