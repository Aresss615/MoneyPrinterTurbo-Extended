"""TikTok Content Posting API (Direct Post) integration.

Synchronous ``requests`` client mirroring the style of ``voice.py`` / ``llm.py``.
OAuth tokens are cached in ``storage/tiktok_token.json`` (never in config.toml,
since ``config.save_config`` only rewrites known tables).

Flow for posting a finished video:
    creator authorizes once (browser) -> ``exchange_code_for_token``
    -> ``publish_video`` runs init -> chunked PUT upload -> status poll.

Unaudited TikTok apps may only post privately (``SELF_ONLY``); flip the
``privacy_level`` config to ``PUBLIC_TO_EVERYONE`` after TikTok audits the app.
"""

import json
import os
import time
from typing import Optional, Sequence
from urllib.parse import urlencode

import requests
from loguru import logger

from app.config import config
from app.utils import utils


AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
PUBLISH_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
PUBLISH_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# user.info.basic identifies the connected account; video.publish is Direct Post;
# video.upload sends a draft to the creator's TikTok inbox to finish in-app.
SCOPES = "user.info.basic,video.publish,video.upload"
USER_INFO_FIELDS = "open_id,union_id,avatar_url,display_name"
DEFAULT_PRIVACY = "SELF_ONLY"
DEFAULT_COVER_TIMESTAMP_MS = 1000
MIN_CHUNK_SIZE = 5 * 1024 * 1024
MAX_CHUNK_SIZE = 64 * 1024 * 1024
MAX_TOTAL_CHUNKS = 1000
OAUTH_STATE_TTL_SECONDS = 600
# Terminal states reported by the publish status endpoint.
_TERMINAL_STATES = {"PUBLISH_COMPLETE", "FAILED"}


class TikTokError(Exception):
    """Raised when the TikTok API returns an error or is misconfigured."""


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #
def _client_key() -> str:
    return (config.tiktok.get("client_key") or "").strip()


def _client_secret() -> str:
    return (config.tiktok.get("client_secret") or "").strip()


def _redirect_uri() -> str:
    return (
        config.tiktok.get("redirect_uri")
        or "https://your-cloudflare-tunnel.example.com/api/v1/tiktok/callback"
    ).strip()


def is_configured() -> bool:
    return bool(_client_key() and _client_secret())


# --------------------------------------------------------------------------- #
# Token cache (storage/tiktok_token.json)
# --------------------------------------------------------------------------- #
def _token_path() -> str:
    return os.path.join(utils.storage_dir(create=True), "tiktok_token.json")


def load_token_cache() -> dict:
    path = _token_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError) as exc:
        logger.warning(f"failed to read tiktok token cache: {exc}")
        return {}


def save_token_cache(data: dict) -> None:
    path = _token_path()
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)


def _store_token_response(payload: dict) -> dict:
    """Normalize an OAuth token response into the cache and persist it."""
    now = time.time()
    cache = {
        "access_token": payload.get("access_token", ""),
        "refresh_token": payload.get("refresh_token", ""),
        "open_id": payload.get("open_id", ""),
        "scope": payload.get("scope", ""),
        "expires_at": now + int(payload.get("expires_in", 0) or 0),
        "refresh_expires_at": now + int(payload.get("refresh_expires_in", 0) or 0),
    }
    save_token_cache(cache)
    return cache


def _state_path() -> str:
    return os.path.join(utils.storage_dir(create=True), "tiktok_oauth_state.json")


def _load_oauth_states() -> list[dict]:
    path = _state_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (ValueError, OSError) as exc:
        logger.warning(f"failed to read tiktok oauth state cache: {exc}")
        return []
    if isinstance(payload, dict) and isinstance(payload.get("states"), list):
        return payload["states"]
    return []


def _save_oauth_states(states: list[dict]) -> None:
    with open(_state_path(), "w", encoding="utf-8") as fp:
        json.dump({"states": states}, fp, indent=2)


def save_oauth_state(state: str) -> None:
    now = time.time()
    expires_at = now + OAUTH_STATE_TTL_SECONDS
    states = [
        item
        for item in _load_oauth_states()
        if float(item.get("expires_at", 0) or 0) > now
    ]
    states.append({"state": state, "expires_at": expires_at})
    _save_oauth_states(states)


def consume_oauth_state(state: str) -> bool:
    now = time.time()
    matched = False
    remaining = []
    for item in _load_oauth_states():
        item_state = str(item.get("state", ""))
        expires_at = float(item.get("expires_at", 0) or 0)
        if item_state == state and expires_at > now:
            matched = True
            continue
        if expires_at > now:
            remaining.append(item)
    _save_oauth_states(remaining)
    return matched


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #
def build_authorize_url(state: str) -> str:
    if not _client_key():
        raise TikTokError("tiktok client_key is not configured")
    params = {
        "client_key": _client_key(),
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    if not is_configured():
        raise TikTokError("tiktok client_key/client_secret are not configured")
    resp = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_key": _client_key(),
            "client_secret": _client_secret(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": _redirect_uri(),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    payload = resp.json()
    if payload.get("error") and payload.get("error") not in ("", None):
        # token endpoint returns error/error_description (not the data envelope)
        raise TikTokError(
            f"token exchange failed: {payload.get('error')}: "
            f"{payload.get('error_description', '')}"
        )
    if not payload.get("access_token"):
        raise TikTokError(f"token exchange returned no access_token: {payload}")
    return _store_token_response(payload)


def _refresh_token(refresh_token: str) -> dict:
    resp = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_key": _client_key(),
            "client_secret": _client_secret(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    payload = resp.json()
    if not payload.get("access_token"):
        raise TikTokError(f"token refresh failed: {payload}")
    return _store_token_response(payload)


def get_valid_access_token() -> str:
    cache = load_token_cache()
    if not cache.get("access_token"):
        raise TikTokError(
            "no TikTok token found; authorize first via /api/v1/tiktok/auth-url"
        )
    # 60s safety margin so a token doesn't expire mid-upload.
    if time.time() < float(cache.get("expires_at", 0)) - 60:
        return cache["access_token"]

    refresh = cache.get("refresh_token")
    if not refresh:
        raise TikTokError("TikTok token expired and no refresh_token is available")
    return _refresh_token(refresh)["access_token"]


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
def _check_envelope(resp) -> dict:
    """Validate the standard ``{data, error}`` envelope and return ``data``."""
    payload = resp.json()
    error = payload.get("error") or {}
    code = error.get("code")
    if code and code != "ok":
        raise TikTokError(
            f"tiktok api error: {code}: {error.get('message', '')} "
            f"(log_id={error.get('log_id', '')})"
        )
    return payload.get("data") or {}


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def assemble_title(description: str, hashtags: Optional[Sequence[str]]) -> str:
    """Combine the caption and inline hashtags into TikTok's ``title`` field."""
    parts = []
    caption = " ".join((description or "").split())
    if caption:
        parts.append(caption)
    for tag in hashtags or []:
        tag = "".join(str(tag).split()).lstrip("#")
        if tag:
            parts.append(f"#{tag}")
    return " ".join(parts)


def query_creator_info(token: Optional[str] = None) -> dict:
    token = token or get_valid_access_token()
    resp = requests.post(CREATOR_INFO_URL, headers=_auth_headers(token), timeout=30)
    return _check_envelope(resp)


def query_user_info(token: Optional[str] = None) -> dict:
    """Fetch the connected creator's basic profile (user.info.basic scope)."""
    token = token or get_valid_access_token()
    resp = requests.get(
        USER_INFO_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": USER_INFO_FIELDS},
        timeout=30,
    )
    return _check_envelope(resp).get("user") or {}


def build_upload_plan(video_size: int) -> dict:
    if video_size <= 0:
        raise TikTokError("video is empty")
    if video_size <= MAX_CHUNK_SIZE:
        chunk_size = video_size
        total_chunk_count = 1
    elif video_size < MAX_CHUNK_SIZE * 2:
        chunk_size = max(MIN_CHUNK_SIZE, video_size // 2)
        total_chunk_count = video_size // chunk_size
    else:
        chunk_size = MAX_CHUNK_SIZE
        total_chunk_count = video_size // chunk_size
    if total_chunk_count < 1 or total_chunk_count > MAX_TOTAL_CHUNKS:
        raise TikTokError(
            f"unsupported video size for TikTok chunk upload: {video_size} bytes"
        )
    return {
        "video_size": video_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunk_count,
    }


def _iter_video_chunks(
    video_path: str, video_size: int, chunk_size: int, total_chunk_count: int
):
    with open(video_path, "rb") as fp:
        for index in range(total_chunk_count):
            start = index * chunk_size
            if index == total_chunk_count - 1:
                length = video_size - start
            else:
                length = chunk_size
            chunk = fp.read(length)
            if len(chunk) != length:
                raise TikTokError(
                    f"failed to read video chunk {index + 1}/{total_chunk_count}"
                )
            yield start, start + len(chunk) - 1, chunk


def publish_video(
    video_path: str,
    title: Optional[str] = None,
    *,
    description: str = "",
    hashtags: Optional[Sequence[str]] = None,
    privacy: Optional[str] = None,
    cover_timestamp_ms: Optional[int] = None,
    disable_comment: Optional[bool] = None,
    disable_duet: Optional[bool] = None,
    disable_stitch: Optional[bool] = None,
    brand_content_toggle: Optional[bool] = None,
    brand_organic_toggle: Optional[bool] = None,
    is_aigc: Optional[bool] = None,
    access_token: Optional[str] = None,
    poll: bool = True,
    poll_interval: float = 3.0,
    poll_timeout: float = 300.0,
) -> dict:
    """Direct-post a local mp4 to TikTok via the FILE_UPLOAD source.

    Returns the terminal status payload (``status`` + ``publish_id``).
    """
    if not os.path.isfile(video_path):
        raise TikTokError(f"video not found: {video_path}")

    token = access_token or get_valid_access_token()
    if title is None:
        title = assemble_title(description, hashtags)

    privacy = privacy or config.tiktok.get("privacy_level") or DEFAULT_PRIVACY
    if cover_timestamp_ms is None:
        cover_timestamp_ms = int(
            config.tiktok.get("cover_timestamp_ms", DEFAULT_COVER_TIMESTAMP_MS)
        )
    if disable_comment is None:
        disable_comment = bool(config.tiktok.get("disable_comment", False))
    if disable_duet is None:
        disable_duet = bool(config.tiktok.get("disable_duet", False))
    if disable_stitch is None:
        disable_stitch = bool(config.tiktok.get("disable_stitch", False))
    if brand_content_toggle is None:
        brand_content_toggle = bool(config.tiktok.get("brand_content_toggle", False))
    if brand_organic_toggle is None:
        brand_organic_toggle = bool(config.tiktok.get("brand_organic_toggle", False))
    if is_aigc is None:
        is_aigc = bool(config.tiktok.get("is_aigc", False))

    video_size = os.path.getsize(video_path)
    upload_plan = build_upload_plan(video_size)

    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
            "video_cover_timestamp_ms": cover_timestamp_ms,
            "brand_content_toggle": brand_content_toggle,
            "brand_organic_toggle": brand_organic_toggle,
            "is_aigc": is_aigc,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            **upload_plan,
        },
    }

    logger.info(f"tiktok: init publish for {video_path} ({video_size} bytes)")
    init_resp = requests.post(
        PUBLISH_INIT_URL, headers=_auth_headers(token), json=init_body, timeout=60
    )
    data = _check_envelope(init_resp)
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokError(f"init response missing publish_id/upload_url: {data}")

    _put_video_chunks(video_path, video_size, upload_plan, upload_url, publish_id)

    if not poll:
        return {"status": "PROCESSING_UPLOAD", "publish_id": publish_id}

    return _poll_status(publish_id, token, poll_interval, poll_timeout)


def _put_video_chunks(
    video_path: str, video_size: int, upload_plan: dict, upload_url: str, publish_id: str
) -> None:
    """Stream the local video to ``upload_url`` as sequential byte-range chunks."""
    logger.info(
        f"tiktok: uploading {video_size} bytes in "
        f"{upload_plan['total_chunk_count']} chunk(s) for publish_id={publish_id}"
    )
    chunks = _iter_video_chunks(
        video_path,
        video_size,
        upload_plan["chunk_size"],
        upload_plan["total_chunk_count"],
    )
    for start, end, chunk in chunks:
        put_resp = requests.put(
            upload_url,
            data=chunk,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start}-{end}/{video_size}",
                "Content-Length": str(len(chunk)),
            },
            timeout=600,
        )
        put_resp.raise_for_status()


def upload_video_to_inbox(
    video_path: str,
    *,
    access_token: Optional[str] = None,
    poll: bool = True,
    poll_interval: float = 3.0,
    poll_timeout: float = 300.0,
) -> dict:
    """Upload a local mp4 to the creator's TikTok inbox as a draft (video.upload).

    Unlike Direct Post, no ``post_info`` is sent — the creator finishes the
    caption, privacy, and interaction settings inside the TikTok app. Returns
    the terminal status payload (``status`` + ``publish_id``).
    """
    if not os.path.isfile(video_path):
        raise TikTokError(f"video not found: {video_path}")

    token = access_token or get_valid_access_token()
    video_size = os.path.getsize(video_path)
    upload_plan = build_upload_plan(video_size)

    init_body = {"source_info": {"source": "FILE_UPLOAD", **upload_plan}}
    logger.info(f"tiktok: init inbox upload for {video_path} ({video_size} bytes)")
    init_resp = requests.post(
        INBOX_INIT_URL, headers=_auth_headers(token), json=init_body, timeout=60
    )
    data = _check_envelope(init_resp)
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokError(f"inbox init response missing publish_id/upload_url: {data}")

    _put_video_chunks(video_path, video_size, upload_plan, upload_url, publish_id)

    if not poll:
        return {"status": "PROCESSING_UPLOAD", "publish_id": publish_id}

    return _poll_status(publish_id, token, poll_interval, poll_timeout)


def fetch_status(publish_id: str, token: Optional[str] = None) -> dict:
    token = token or get_valid_access_token()
    resp = requests.post(
        PUBLISH_STATUS_URL,
        headers=_auth_headers(token),
        json={"publish_id": publish_id},
        timeout=30,
    )
    return _check_envelope(resp)


def _poll_status(
    publish_id: str, token: str, interval: float, timeout: float
) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = fetch_status(publish_id, token)
        status = last.get("status")
        if status in _TERMINAL_STATES:
            if status == "FAILED":
                raise TikTokError(f"tiktok publish failed: {last}")
            return last
        if interval > 0:
            time.sleep(interval)
        else:
            break
    # Non-terminal (still processing) or interval==0 single-shot in tests.
    return last or {"status": "PROCESSING", "publish_id": publish_id}
