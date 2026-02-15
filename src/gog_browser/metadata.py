"""Metadata store: per-game folders, scan state, and merge for API."""

import json
from pathlib import Path
from typing import Any

SCAN_STATE_FILE = "_scan_state.json"
GAME_JSON = "game.json"
OVERRIDE_JSON = "override.json"


def get_game_dir(metadata_root: Path, game_key: str) -> Path:
    """Path to a game's metadata folder (may not exist yet)."""
    safe_key = "".join(c if c.isalnum() or c in "._-" else "_" for c in game_key)
    return metadata_root / safe_key


def load_game_json(metadata_root: Path, game_key: str) -> dict | None:
    """Load game.json for a game. Returns None if missing."""
    path = get_game_dir(metadata_root, game_key) / GAME_JSON
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_override(metadata_root: Path, game_key: str) -> dict | None:
    """Load override.json (gog_search_name, product_id, etc.). Returns None if missing."""
    path = get_game_dir(metadata_root, game_key) / OVERRIDE_JSON
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_override(metadata_root: Path, game_key: str, data: dict) -> None:
    """Write override.json for a game."""
    dir_path = get_game_dir(metadata_root, game_key)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / OVERRIDE_JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_search_name(metadata_root: Path, game_key: str, default: str) -> str:
    """Search name for GOG: override if set, else default (e.g. from scanner)."""
    ov = load_override(metadata_root, game_key)
    if ov and ov.get("gog_search_name"):
        return ov["gog_search_name"].strip()
    return default


def get_product_id_override(metadata_root: Path, game_key: str) -> int | None:
    """Optional fixed GOG product id for this game."""
    ov = load_override(metadata_root, game_key)
    if ov and ov.get("product_id") is not None:
        try:
            return int(ov["product_id"])
        except (TypeError, ValueError):
            pass
    return None


def list_game_keys(metadata_root: Path) -> list[str]:
    """List all game keys that have a metadata folder (game.json or override)."""
    root = Path(metadata_root)
    if not root.is_dir():
        return []
    keys = []
    for d in root.iterdir():
        if d.is_dir() and not d.name.startswith("_"):
            if (d / GAME_JSON).exists() or (d / OVERRIDE_JSON).exists():
                keys.append(d.name)
    return sorted(keys)


def load_scan_state(metadata_root: Path) -> dict:
    """Load _scan_state.json. Returns dict with keys set, last_scan, etc."""
    path = Path(metadata_root) / SCAN_STATE_FILE
    if not path.exists():
        return {"installer_keys": [], "last_scan": None}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"installer_keys": [], "last_scan": None}


def save_scan_state(metadata_root: Path, installer_keys: list[str]) -> None:
    """Persist current installer keys and timestamp."""
    import time
    path = Path(metadata_root) / SCAN_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"installer_keys": installer_keys, "last_scan": time.time()},
            f,
            indent=2,
        )


def merge_game_with_installer(
    metadata_root: Path,
    game_key: str,
    installer_entry: dict,
) -> dict:
    """
    Build API-ready game dict: installer info + game.json + overrides.
    installer_entry: dict with key, path_type, fs_path (str), internal_path, display_name.
    """
    out: dict[str, Any] = {
        "id": game_key,
        "key": game_key,
        "path_type": installer_entry.get("path_type", "file"),
        "installer_path": installer_entry.get("fs_path", ""),
        "internal_path": installer_entry.get("internal_path"),
        "display_name": installer_entry.get("display_name", game_key),
        "gog_title": None,
        "gog_slug": None,
        "gog_link": None,
        "thumbnail": None,
        "screenshots_local": [],
        "videos_local": [],
        "gog_search_name_override": None,
    }
    ov = load_override(metadata_root, game_key)
    if ov and ov.get("gog_search_name"):
        out["gog_search_name_override"] = ov["gog_search_name"]
    game = load_game_json(metadata_root, game_key)
    if game:
        out["gog_title"] = game.get("title")
        out["gog_slug"] = game.get("slug")
        links = game.get("links") or {}
        out["gog_link"] = links.get("product_card")
        if out["gog_link"] and not out["gog_link"].startswith("http"):
            out["gog_link"] = "https://www.gog.com" + out["gog_link"]
        images = game.get("images") or {}
        thumb = images.get("logo") or images.get("background") or images.get("icon")
        if thumb:
            out["thumbnail"] = thumb if thumb.startswith("http") else "https:" + thumb
        out["screenshots_local"] = game.get("screenshots_local") or []
        out["videos_local"] = game.get("videos_local") or []
        out["description"] = game.get("description", "")
        out["release_date"] = game.get("release_date")
    return out


def get_game_by_key_only(metadata_root: Path, game_key: str) -> dict | None:
    """
    Build API-ready game dict from metadata only (no scanner).
    Used for GET /api/games/{id}. Returns None if no metadata folder.
    """
    ov = load_override(metadata_root, game_key)
    game = load_game_json(metadata_root, game_key)
    if not ov and not game:
        return None
    synthetic_entry = {
        "key": game_key,
        "path_type": (ov or {}).get("path_type", "file"),
        "fs_path": (ov or {}).get("installer_path", ""),
        "internal_path": (ov or {}).get("internal_path"),
        "display_name": (ov or {}).get("display_name", game_key),
    }
    return merge_game_with_installer(metadata_root, game_key, synthetic_entry)
