"""Environment-based configuration."""

import os
from pathlib import Path


def get_installer_path() -> Path:
    """Root path where GOG installers live (dir with exe or .rar)."""
    raw = os.environ.get("GOG_INSTALLER_PATH", "")
    if not raw:
        raise ValueError("GOG_INSTALLER_PATH must be set")
    return Path(raw).resolve()


def get_metadata_path() -> Path:
    """Root path for metadata (game.json, screenshots, videos)."""
    raw = os.environ.get("GOG_METADATA_PATH", "")
    if not raw:
        raise ValueError("GOG_METADATA_PATH must be set")
    return Path(raw).resolve()


def get_scan_schedule() -> str:
    """Cron-like or 'daily' for auto scan. Empty = on-demand only."""
    return os.environ.get("GOG_SCAN_SCHEDULE", "").strip()


def get_discord_webhook_url() -> str:
    """Optional Discord webhook URL for events."""
    return os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
