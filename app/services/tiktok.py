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
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
PUBLISH_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
PUBLISH_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

SCOPES = "video.publish,video.upload"
DEFAULT_PRIVACY = "SELF_ONLY"
DEFAULT_COVER_TIMESTAMP_MS = 1000
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
        or "http://127.0.0.1:8080/api/v1/tiktok/callback"
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


def _read_video_bytes(video_path: str) -> bytes:
    with open(video_path, "rb") as fp:
        return fp.read()


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

    video_bytes = _read_video_bytes(video_path)
    video_size = len(video_bytes)

    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
            "video_cover_timestamp_ms": cover_timestamp_ms,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
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

    logger.info(f"tiktok: uploading {video_size} bytes for publish_id={publish_id}")
    put_resp = requests.put(
        upload_url,
        data=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            "Content-Length": str(video_size),
        },
        timeout=600,
    )
    put_resp.raise_for_status()

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
