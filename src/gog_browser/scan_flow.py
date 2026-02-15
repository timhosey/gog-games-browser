"""Full scan flow: discover installers, diff with state, fetch GOG, save metadata, notify Discord."""

import asyncio
import logging
from pathlib import Path

import httpx

from gog_browser.config import get_discord_webhook_url, get_installer_path, get_metadata_path
from gog_browser.discord_notify import (
    notify_error,
    notify_new_games,
    notify_scan_finished,
    notify_scan_started,
    notify_games_removed,
)
from gog_browser.gog_client import resolve_and_save
from gog_browser.metadata import (
    get_game_dir,
    get_product_id_override,
    get_search_name,
    load_override,
    load_scan_state,
    save_override,
    save_scan_state,
)
from gog_browser.scanner import scan_installers, InstallerEntry

logger = logging.getLogger(__name__)


def _installer_entry_to_dict(e: InstallerEntry) -> dict:
    return {
        "key": e.key,
        "path_type": e.path_type,
        "fs_path": str(e.fs_path),
        "internal_path": e.internal_path,
        "display_name": e.display_name,
    }


async def run_scan(
    *,
    installer_path: Path | None = None,
    metadata_path: Path | None = None,
    discord_url: str | None = None,
) -> dict:
    """
    Run full scan: discover installers, diff with last state, fetch GOG for new/changed,
    save metadata, update state, send Discord notifications.
    Returns summary: added, removed, changed, total, errors.
    """
    installer_path = installer_path or get_installer_path()
    metadata_path = metadata_path or get_metadata_path()
    discord_url = discord_url or get_discord_webhook_url()

    notify_scan_started(discord_url)

    metadata_path = Path(metadata_path)
    metadata_path.mkdir(parents=True, exist_ok=True)

    entries = scan_installers(installer_path)
    current_keys = {e.key for e in entries}
    prev = load_scan_state(metadata_path)
    prev_keys = set(prev.get("installer_keys") or [])

    added_keys = current_keys - prev_keys
    removed_keys = prev_keys - current_keys
    # "Changed" = still present; we could detect content change later. For now treat as 0 or "updated" count after fetch.
    entry_by_key = {e.key: e for e in entries}

    new_game_names: list[str] = []
    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        for key in added_keys:
            entry = entry_by_key.get(key)
            if not entry:
                continue
            game_dir = get_game_dir(metadata_path, key)
            search_name = get_search_name(metadata_path, key, entry.display_name)
            product_id = get_product_id_override(metadata_path, key)
            override_data = {
                "gog_search_name": search_name,
                "installer_path": str(entry.fs_path),
                "path_type": entry.path_type,
                "internal_path": entry.internal_path,
                "display_name": entry.display_name,
            }
            try:
                game = await resolve_and_save(
                    client,
                    search_name,
                    game_dir,
                    product_id_override=product_id,
                    download_assets=True,
                )
                if game:
                    new_game_names.append(game.get("title") or entry.display_name)
                else:
                    errors.append(f"No GOG match: {key} ({search_name})")
                save_override(metadata_path, key, override_data)
            except Exception as e:
                logger.exception("Failed to fetch game %s", key)
                errors.append(f"{key}: {e}")
                save_override(metadata_path, key, override_data)

    if new_game_names:
        notify_new_games(discord_url, new_game_names)
    if removed_keys:
        notify_games_removed(discord_url, list(removed_keys))
    if errors:
        notify_error(discord_url, "Scan had errors", "\n".join(errors[:5]))

    # Keep installer path in override for all current entries (for detail API)
    for key in current_keys:
        entry = entry_by_key.get(key)
        if entry:
            ov = load_override(metadata_path, key) or {}
            ov["installer_path"] = str(entry.fs_path)
            ov["path_type"] = entry.path_type
            ov["internal_path"] = entry.internal_path
            ov["display_name"] = entry.display_name
            if "gog_search_name" not in ov:
                ov["gog_search_name"] = get_search_name(metadata_path, key, entry.display_name)
            save_override(metadata_path, key, ov)

    save_scan_state(metadata_path, list(current_keys))
    notify_scan_finished(
        discord_url,
        added=len(added_keys),
        removed=len(removed_keys),
        changed=0,
        total=len(current_keys),
    )

    return {
        "added": len(added_keys),
        "removed": len(removed_keys),
        "total": len(current_keys),
        "errors": errors,
    }
