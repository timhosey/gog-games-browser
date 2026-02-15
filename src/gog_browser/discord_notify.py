"""Discord webhook notifications for scan events."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "GOG-Games-Browser/0.1"


def _post_sync(url: str, payload: dict) -> None:
    """Fire-and-forget POST; log on failure."""
    try:
        r = httpx.post(
            url,
            json=payload,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=10.0,
        )
        if r.status_code >= 400:
            logger.warning("Discord webhook failed: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Discord webhook error: %s", e)


def notify_scan_started(webhook_url: str) -> None:
    if not webhook_url:
        return
    _post_sync(
        webhook_url,
        {"content": "GOG Games Browser: Scan started."},
    )


def notify_scan_finished(
    webhook_url: str,
    added: int = 0,
    removed: int = 0,
    changed: int = 0,
    total: int = 0,
) -> None:
    if not webhook_url:
        return
    desc = f"Total: {total} | Added: {added} | Removed: {removed} | Updated: {changed}"
    _post_sync(
        webhook_url,
        {
            "embeds": [
                {
                    "title": "Scan finished",
                    "description": desc,
                    "color": 0x00FF00,
                }
            ]
        },
    )


def notify_new_games(webhook_url: str, game_names: list[str], limit: int = 10) -> None:
    if not webhook_url or not game_names:
        return
    names = game_names[:limit]
    extra = f" and {len(game_names) - limit} more" if len(game_names) > limit else ""
    _post_sync(
        webhook_url,
        {
            "embeds": [
                {
                    "title": "New games detected",
                    "description": "\n".join(f"• {n}" for n in names) + extra,
                    "color": 0x3498DB,
                }
            ]
        },
    )


def notify_games_removed(webhook_url: str, game_keys: list[str], limit: int = 10) -> None:
    if not webhook_url or not game_keys:
        return
    keys = game_keys[:limit]
    extra = f" and {len(game_keys) - limit} more" if len(game_keys) > limit else ""
    _post_sync(
        webhook_url,
        {
            "embeds": [
                {
                    "title": "Games removed (installer no longer found)",
                    "description": "\n".join(f"• {k}" for k in keys) + extra,
                    "color": 0xE74C3C,
                }
            ]
        },
    )


def notify_error(webhook_url: str, message: str, detail: str = "") -> None:
    if not webhook_url:
        return
    _post_sync(
        webhook_url,
        {
            "embeds": [
                {
                    "title": "GOG Browser error",
                    "description": message + (f"\n{detail}" if detail else ""),
                    "color": 0xFF0000,
                }
            ]
        },
    )
