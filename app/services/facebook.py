"""Facebook Graph API integration for posting videos to a Facebook Page.

Page Access Tokens are cached in ``storage/facebook_token.json`` (never in
config.toml). The token can be saved via ``POST /api/v1/facebook/set-token``
or by setting ``page_access_token`` in the ``[facebook]`` config section
(it is read once and moved to the token store).

Flow:
    1. Obtain a Page Access Token from developers.facebook.com (Graph API
       Explorer → "Get Page Access Token" or via the ``/me/accounts`` endpoint).
    2. POST ``/api/v1/facebook/set-token`` with ``{ page_id, page_access_token }``.
    3. POST ``/api/v1/facebook/publish`` with ``{ task_id, description, ... }``.
"""

import json
import os
import time
from typing import Optional

import requests
from loguru import logger

from app.config import config
from app.utils import utils


GRAPH_API_VERSION = "v19.0"
GRAPH_VIDEO_BASE = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"


class FacebookError(Exception):
    """Raised when the Facebook Graph API returns an error or is misconfigured."""


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #
def _cfg_page_id() -> str:
    return str(config.facebook.get("page_id") or "").strip()


def _cfg_page_access_token() -> str:
    return str(config.facebook.get("page_access_token") or "").strip()


def is_configured() -> bool:
    cache = load_token_cache()
    return bool(cache.get("page_id") and cache.get("page_access_token"))


# --------------------------------------------------------------------------- #
# Token cache (storage/facebook_token.json)
# --------------------------------------------------------------------------- #
def _token_path() -> str:
    return os.path.join(utils.storage_dir(create=True), "facebook_token.json")


def load_token_cache() -> dict:
    path = _token_path()
    if not os.path.isfile(path):
        # Fall back to config values if available.
        if _cfg_page_id() and _cfg_page_access_token():
            return {
                "page_id": _cfg_page_id(),
                "page_access_token": _cfg_page_access_token(),
                "saved_at": 0.0,
            }
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError) as exc:
        logger.warning(f"failed to read facebook token cache: {exc}")
        return {}


def save_token_cache(page_id: str, page_access_token: str) -> dict:
    data = {
        "page_id": page_id.strip(),
        "page_access_token": page_access_token.strip(),
        "saved_at": time.time(),
    }
    path = _token_path()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
    return data


def get_valid_access_token() -> tuple[str, str]:
    """Return ``(page_id, page_access_token)`` from the token cache.

    Raises ``FacebookError`` if not configured.
    """
    cache = load_token_cache()
    page_id = cache.get("page_id", "").strip()
    token = cache.get("page_access_token", "").strip()
    if not page_id or not token:
        raise FacebookError(
            "Facebook page not connected; save a Page Access Token via "
            "POST /api/v1/facebook/set-token"
        )
    return page_id, token


# --------------------------------------------------------------------------- #
# Graph API helpers
# --------------------------------------------------------------------------- #
def _check_response(resp: requests.Response) -> dict:
    """Raise ``FacebookError`` on API errors; return the parsed JSON body."""
    try:
        payload = resp.json()
    except ValueError:
        resp.raise_for_status()
        return {}
    if "error" in payload:
        err = payload["error"]
        raise FacebookError(
            f"facebook api error {err.get('code')}: {err.get('message', '')} "
            f"(type={err.get('type', '')}, fbtrace_id={err.get('fbtrace_id', '')})"
        )
    resp.raise_for_status()
    return payload


def get_page_info(
    page_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Fetch basic info for the configured page (name, category, id)."""
    if not page_id or not access_token:
        page_id, access_token = get_valid_access_token()
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}",
        params={
            "access_token": access_token,
            "fields": "id,name,category,fan_count",
        },
        timeout=15,
    )
    return _check_response(resp)


# --------------------------------------------------------------------------- #
# Video publishing
# --------------------------------------------------------------------------- #
SIMPLE_UPLOAD_LIMIT = 100 * 1024 * 1024   # 100 MB — use resumable above this
RESUMABLE_CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB chunks


def post_video(
    video_path: str,
    *,
    description: str = "",
    title: str = "",
    published: bool = True,
    page_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Upload a local mp4 to a Facebook Page.

    Automatically selects the upload strategy:
    - ≤ 100 MB  → single multipart POST (fast, one shot)
    - > 100 MB  → resumable chunked upload (required by Facebook for large files)

    Returns the Graph API response dict with ``"id"`` (Facebook video ID).
    """
    if not os.path.isfile(video_path):
        raise FacebookError(f"video not found: {video_path}")

    if not page_id or not access_token:
        page_id, access_token = get_valid_access_token()

    video_size = os.path.getsize(video_path)
    logger.info(
        f"facebook: uploading {video_path} ({video_size} bytes) "
        f"to page {page_id}, published={published}"
    )

    if video_size <= SIMPLE_UPLOAD_LIMIT:
        return _post_video_simple(
            video_path, video_size, page_id, access_token,
            description=description, title=title, published=published,
        )
    return _post_video_resumable(
        video_path, video_size, page_id, access_token,
        description=description, title=title, published=published,
    )


def _post_video_simple(
    video_path: str,
    video_size: int,
    page_id: str,
    access_token: str,
    *,
    description: str,
    title: str,
    published: bool,
) -> dict:
    url = f"{GRAPH_VIDEO_BASE}/{page_id}/videos"
    data: dict = {"access_token": access_token, "published": str(published).lower()}
    if description:
        data["description"] = description
    if title:
        data["title"] = title

    with open(video_path, "rb") as fp:
        resp = requests.post(
            url,
            data=data,
            files={"source": (os.path.basename(video_path), fp, "video/mp4")},
            timeout=600,
        )
    result = _check_response(resp)
    logger.info(f"facebook: video posted (simple), id={result.get('id')}")
    return result


def _post_video_resumable(
    video_path: str,
    video_size: int,
    page_id: str,
    access_token: str,
    *,
    description: str,
    title: str,
    published: bool,
) -> dict:
    """Three-phase resumable upload: start → transfer chunks → finish."""
    url = f"{GRAPH_VIDEO_BASE}/{page_id}/videos"

    # Phase 1 — start
    start_resp = requests.post(
        url,
        data={
            "upload_phase": "start",
            "file_size": str(video_size),
            "access_token": access_token,
        },
        timeout=30,
    )
    start_data = _check_response(start_resp)
    session_id = start_data.get("upload_session_id")
    video_id = start_data.get("video_id")
    start_offset = int(start_data.get("start_offset", 0))
    end_offset = int(start_data.get("end_offset", RESUMABLE_CHUNK_SIZE))
    logger.info(f"facebook: resumable upload started, session={session_id}")

    # Phase 2 — transfer
    with open(video_path, "rb") as fp:
        chunk_num = 0
        while start_offset < video_size:
            chunk_size = end_offset - start_offset
            fp.seek(start_offset)
            chunk = fp.read(chunk_size)
            transfer_resp = requests.post(
                url,
                data={
                    "upload_phase": "transfer",
                    "upload_session_id": session_id,
                    "start_offset": str(start_offset),
                    "access_token": access_token,
                },
                files={"video_file_chunk": (os.path.basename(video_path), chunk, "video/mp4")},
                timeout=300,
            )
            transfer_data = _check_response(transfer_resp)
            new_start = int(transfer_data.get("start_offset", end_offset))
            new_end = int(transfer_data.get("end_offset", new_start))
            chunk_num += 1
            logger.info(
                f"facebook: chunk {chunk_num} uploaded "
                f"({start_offset}–{end_offset} / {video_size})"
            )
            if new_start == new_end:
                break
            start_offset, end_offset = new_start, new_end

    # Phase 3 — finish
    finish_data: dict = {
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "published": str(published).lower(),
        "access_token": access_token,
    }
    if description:
        finish_data["description"] = description
    if title:
        finish_data["title"] = title

    finish_resp = requests.post(url, data=finish_data, timeout=60)
    result = _check_response(finish_resp)
    result.setdefault("id", video_id)
    logger.info(f"facebook: video posted (resumable), id={result.get('id')}")
    return result
