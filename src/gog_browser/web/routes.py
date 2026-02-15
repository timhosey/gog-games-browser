"""API routes for games list, detail, scan, override, and metadata assets."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gog_browser.config import get_installer_path, get_metadata_path
from gog_browser.metadata import (
    get_game_by_key_only,
    get_game_dir,
    get_product_id_override,
    get_search_name,
    merge_game_with_installer,
    save_override,
)
from gog_browser.scanner import scan_installers
from gog_browser.scan_flow import _installer_entry_to_dict, run_scan
from gog_browser.gog_client import resolve_and_save
import httpx

api_router = APIRouter()


@api_router.get("/games")
async def list_games():
    """List all games: current installers merged with metadata."""
    installer_path = get_installer_path()
    metadata_path = get_metadata_path()
    entries = scan_installers(installer_path)
    out = []
    for e in entries:
        entry_dict = _installer_entry_to_dict(e)
        out.append(merge_game_with_installer(metadata_path, e.key, entry_dict))
    return {"games": out, "total": len(out)}


@api_router.get("/games/{game_id}")
async def get_game(game_id: str):
    """Single game detail by key (id)."""
    metadata_path = get_metadata_path()
    game = get_game_by_key_only(metadata_path, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


class OverrideBody(BaseModel):
    gog_search_name: str | None = None
    product_id: int | None = None


@api_router.put("/games/{game_id}/override")
async def set_override(game_id: str, body: OverrideBody):
    """Set GOG search name and/or product_id override for a game."""
    metadata_path = get_metadata_path()
    game_dir = get_game_dir(metadata_path, game_id)
    game_dir.mkdir(parents=True, exist_ok=True)
    from gog_browser.metadata import load_override
    ov = load_override(metadata_path, game_id) or {}
    if body.gog_search_name is not None:
        ov["gog_search_name"] = (body.gog_search_name or "").strip() or None
    if body.product_id is not None:
        ov["product_id"] = body.product_id
    save_override(metadata_path, game_id, ov)
    return {"ok": True, "override": ov}


@api_router.post("/scan")
async def trigger_scan():
    """Run full scan (sync). Returns summary."""
    result = await run_scan()
    return result


@api_router.post("/games/{game_id}/refresh")
async def refresh_game(game_id: str):
    """Re-fetch GOG data for this game and save (uses override search name or product_id)."""
    metadata_path = get_metadata_path()
    game_dir = get_game_dir(metadata_path, game_id)
    search_name = get_search_name(metadata_path, game_id, "")
    product_id = get_product_id_override(metadata_path, game_id)
    if not search_name and product_id is None:
        raise HTTPException(
            status_code=400,
            detail="Set gog_search_name or product_id override first",
        )
    async with httpx.AsyncClient() as client:
        game = await resolve_and_save(
            client,
            search_name or " ",
            game_dir,
            product_id_override=product_id,
            download_assets=True,
        )
    if game is None:
        raise HTTPException(status_code=502, detail="GOG lookup failed")
    return {"ok": True, "title": game.get("title")}


def _safe_metadata_path(metadata_root: Path, game_id: str, subpath: str) -> Path | None:
    """Resolve game_id/subpath under metadata root; ensure no path escape."""
    base = get_game_dir(metadata_root, game_id)
    full = (base / subpath).resolve()
    try:
        full.relative_to(metadata_root.resolve())
    except ValueError:
        return None
    if not full.exists() or not full.is_file():
        return None
    return full


@api_router.get("/metadata/{game_id}/{path:path}")
async def serve_metadata_asset(game_id: str, path: str):
    """Serve a file from a game's metadata folder (e.g. screenshots, videos)."""
    metadata_path = get_metadata_path()
    safe = _safe_metadata_path(metadata_path, game_id, path)
    if safe is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(safe)
