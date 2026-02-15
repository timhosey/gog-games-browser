"""GOG API client: search (embed) and product details (api.gog.com) + asset download."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx

EMBED_SEARCH_URL = "https://embed.gog.com/games/ajax/filtered"
PRODUCT_URL = "https://api.gog.com/products/{id}"
USER_AGENT = "GOG-Games-Browser/0.1 (https://github.com/gog-games-browser)"
REQUEST_DELAY = 0.8  # Between product fetches to avoid 429


async def search_game(client: httpx.AsyncClient, query: str) -> dict | None:
    """
    Search GOG by name. Returns first result dict with id/slug/title or None.
    """
    if not query or not query.strip():
        return None
    try:
        r = await client.get(
            EMBED_SEARCH_URL,
            params={"mediaType": "game", "search": query.strip(), "limit": 5},
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.gog.com/"},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        products = data.get("products") or []
        if not products:
            return None
        first = products[0]
        return {
            "id": first.get("id"),
            "slug": first.get("slug"),
            "title": first.get("title"),
        }
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return None


async def get_product(
    client: httpx.AsyncClient,
    product_id: int,
    expand: str = "screenshots,videos,description",
) -> dict | None:
    """
    Fetch product details from api.gog.com. Returns full JSON or None.
    """
    url = PRODUCT_URL.format(id=product_id)
    try:
        r = await client.get(
            url,
            params={"locale": "en_US", "expand": expand},
            headers={"User-Agent": USER_AGENT},
            timeout=20.0,
        )
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "10")
            try:
                await asyncio.sleep(float(retry_after))
            except ValueError:
                await asyncio.sleep(10.0)
            return await get_product(client, product_id, expand)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


def _normalize_game_json(raw: dict) -> dict:
    """Build a normalized game.json for storage and API."""
    links = raw.get("links") or {}
    images = raw.get("images") or {}
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "slug": raw.get("slug"),
        "description": raw.get("description", ""),
        "release_date": raw.get("release_date"),
        "links": {
            "product_card": links.get("product_card"),
            "support": links.get("support"),
            "forum": links.get("forum"),
        },
        "images": {
            "background": images.get("background"),
            "logo": images.get("logo"),
            "icon": images.get("icon"),
        },
        "content_system_compatibility": raw.get("content_system_compatibility") or {},
        "screenshots": raw.get("screenshots") or [],
        "videos": raw.get("videos") or [],
        "game_type": raw.get("game_type"),
    }


def _ensure_https(url: str) -> str:
    if not url:
        return ""
    return url if url.startswith("http") else "https:" + url


async def download_asset(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    """Download a single asset to dest. Returns True on success."""
    url = _ensure_https(url)
    if not url:
        return False
    try:
        r = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except (httpx.HTTPError, OSError):
        return False


def _screenshot_urls(api_screenshots: list, limit: int = 10) -> list[str]:
    """Extract download URLs from API screenshots (e.g. ggvgm or first formatted)."""
    urls = []
    for s in api_screenshots[:limit]:
        formatted = s.get("formatted_images") or []
        for f in formatted:
            if f.get("formatter_name") == "ggvgm" and f.get("image_url"):
                urls.append(_ensure_https(f["image_url"]))
                break
        else:
            if formatted and formatted[0].get("image_url"):
                urls.append(_ensure_https(formatted[0]["image_url"]))
    return urls


def _video_urls(api_videos: list, limit: int = 3) -> list[tuple[str, str]]:
    """Extract (thumbnail_url, video_id or label) for download. Prefer thumbnail."""
    out = []
    for v in api_videos[:limit]:
        thumb = (v.get("thumbnail") or v.get("thumbnail_url") or "").strip()
        if isinstance(thumb, dict):
            thumb = thumb.get("url") or ""
        if thumb:
            out.append((_ensure_https(thumb), v.get("video_id") or v.get("id") or ""))
    return out


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-_.]", "_", name)
    return name[:200] or "file"


async def download_screenshots(
    client: httpx.AsyncClient,
    api_screenshots: list,
    base_dir: Path,
    limit: int = 10,
) -> list[str]:
    """Download up to limit screenshots into base_dir/screenshots/. Return relative paths."""
    urls = _screenshot_urls(api_screenshots, limit)
    rel_paths = []
    screenshots_dir = base_dir / "screenshots"
    for i, url in enumerate(urls):
        ext = ".jpg" if ".jpg" in url.split("?")[0] else ".png"
        dest = screenshots_dir / f"{i:02d}{ext}"
        if await download_asset(client, url, dest):
            rel_paths.append(f"screenshots/{dest.name}")
        await asyncio.sleep(0.2)
    return rel_paths


async def download_videos(
    client: httpx.AsyncClient,
    api_videos: list,
    base_dir: Path,
    limit: int = 3,
) -> list[str]:
    """Download video thumbnails into base_dir/videos/. Return relative paths."""
    pairs = _video_urls(api_videos, limit)
    rel_paths = []
    videos_dir = base_dir / "videos"
    for i, (url, vid_id) in enumerate(pairs):
        ext = ".jpg" if ".jpg" in url.split("?")[0] else ".png"
        name = _safe_filename(vid_id) or f"thumb_{i}"
        dest = videos_dir / f"{name}{ext}"
        if await download_asset(client, url, dest):
            rel_paths.append(f"videos/{dest.name}")
        await asyncio.sleep(0.2)
    return rel_paths


async def fetch_and_save_game(
    client: httpx.AsyncClient,
    product_id: int,
    metadata_dir: Path,
    *,
    download_assets: bool = True,
    screenshot_limit: int = 10,
    video_limit: int = 3,
) -> dict | None:
    """
    Fetch product from API, normalize to game.json, optionally download assets.
    Writes metadata_dir/game.json and metadata_dir/screenshots|videos.
    Returns normalized game dict or None.
    """
    raw = await get_product(client, product_id)
    if not raw:
        return None
    await asyncio.sleep(REQUEST_DELAY)
    game = _normalize_game_json(raw)
    metadata_dir = Path(metadata_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    if download_assets:
        game["screenshots_local"] = await download_screenshots(
            client, game.get("screenshots") or [], metadata_dir, limit=screenshot_limit
        )
        game["videos_local"] = await download_videos(
            client, game.get("videos") or [], metadata_dir, limit=video_limit
        )
    else:
        game["screenshots_local"] = []
        game["videos_local"] = []
    game_path = metadata_dir / "game.json"
    with open(game_path, "w", encoding="utf-8") as f:
        json.dump(game, f, indent=2, ensure_ascii=False)
    return game


async def resolve_and_save(
    client: httpx.AsyncClient,
    search_name: str,
    metadata_dir: Path,
    *,
    product_id_override: int | None = None,
    download_assets: bool = True,
) -> dict | None:
    """
    Resolve game by search name (or product_id_override), then fetch and save.
    If product_id_override is set, skip search and fetch that product.
    Returns normalized game dict or None.
    """
    if product_id_override is not None:
        return await fetch_and_save_game(client, product_id_override, metadata_dir, download_assets=download_assets)
    hit = await search_game(client, search_name)
    if not hit or hit.get("id") is None:
        return None
    return await fetch_and_save_game(
        client, hit["id"], metadata_dir, download_assets=download_assets
    )
