import json
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from loguru import logger
from pydantic import BaseModel

from app.controllers import base
from app.controllers.v1.base import new_router
from app.models.exception import HttpException
from app.services import creator_console, tiktok
from app.utils import utils


router = new_router()

TIKTOK_VERIFICATION_FILES = {
    "tiktokWLly7x9cmPv0wlZyHy99pbIPzg458GTc.txt",
    "tiktoklxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU.txt",
    "tiktokmrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H.txt",
}


def _load_story_metadata(task_id: str) -> dict:
    story_path = os.path.join(utils.task_dir(task_id), "story.json")
    if not os.path.isfile(story_path):
        return {}
    try:
        with open(story_path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError):
        return {}


class InboxUploadRequest(BaseModel):
    task_id: str
    poll: bool = True


class PublishRequest(BaseModel):
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[list[str]] = None
    privacy: Optional[str] = None
    cover_timestamp_ms: Optional[int] = None
    disable_comment: Optional[bool] = None
    disable_duet: Optional[bool] = None
    disable_stitch: Optional[bool] = None
    brand_content_toggle: Optional[bool] = None
    brand_organic_toggle: Optional[bool] = None
    is_aigc: Optional[bool] = None
    poll: bool = True


def _final_video_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "final-1.mp4")


def _load_markdown_doc(filename: str) -> str:
    path = os.path.join(utils.root_dir(), "docs", filename)
    with open(path, "r", encoding="utf-8") as fp:
        return fp.read()


def _serve_verification_file(verification_filename: str):
    if verification_filename not in TIKTOK_VERIFICATION_FILES:
        return PlainTextResponse("not found", status_code=404)
    path = os.path.join(utils.resource_dir("public/assets"), verification_filename)
    if not os.path.isfile(path):
        return PlainTextResponse("not found", status_code=404)
    with open(path, "r", encoding="utf-8") as fp:
        return PlainTextResponse(fp.read())


@router.get("/tiktok/status", summary="Report TikTok connection status")
def tiktok_status(request: Request):
    configured = tiktok.is_configured()
    locked = base.creator_access_key_required() and not base.has_creator_access(
        request
    )
    if locked:
        return utils.get_response(
            200,
            {
                "configured": configured,
                "connected": False,
                "locked": True,
                "requires_access_key": True,
                "nickname": "",
                "privacy_level": tiktok.config.tiktok.get(
                    "privacy_level", tiktok.DEFAULT_PRIVACY
                ),
                "creator_info": {},
                "user_info": {},
            },
        )

    cache = tiktok.load_token_cache()
    connected = bool(cache.get("access_token"))
    nickname = ""
    creator_info = {}
    user_info = {}
    if connected:
        try:  # user.info.basic — identifies the connected account on the pill
            user_info = tiktok.query_user_info()
            nickname = user_info.get("display_name", "")
        except Exception as exc:  # network/token issues shouldn't 500 the pill
            logger.warning(f"tiktok user_info failed: {exc}")
        try:
            creator_info = tiktok.query_creator_info()
            if not nickname:
                nickname = creator_info.get("creator_nickname", "")
        except Exception as exc:
            logger.warning(f"tiktok creator_info failed: {exc}")
    return utils.get_response(
        200,
        {
            "configured": configured,
            "connected": connected,
            "locked": False,
            "requires_access_key": base.creator_access_key_required(),
            "nickname": nickname,
            "privacy_level": tiktok.config.tiktok.get(
                "privacy_level", tiktok.DEFAULT_PRIVACY
            ),
            "creator_info": creator_info,
            "user_info": user_info,
        },
    )


@router.get("/tiktok/auth-url", summary="Get the TikTok authorization URL")
def tiktok_auth_url(request: Request):
    request_id = base.get_task_id(request)
    base.require_creator_access(request, task_id=request_id)
    try:
        state = utils.get_uuid()
        url = tiktok.build_authorize_url(state=state)
        tiktok.save_oauth_state(state)
    except tiktok.TikTokError as exc:
        raise HttpException(task_id=request_id, status_code=400, message=str(exc))
    return utils.get_response(200, {"auth_url": url})


@router.get("/callback", summary="TikTok OAuth redirect callback")
@router.get("/tiktok/callback", summary="TikTok OAuth redirect callback")
def tiktok_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(
            f"<h2>TikTok authorization failed</h2><p>{error}</p>", status_code=400
        )
    if not code:
        return HTMLResponse(
            "<h2>TikTok authorization failed</h2><p>missing code</p>", status_code=400
        )
    if not state or not tiktok.consume_oauth_state(state):
        return HTMLResponse(
            "<h2>TikTok authorization failed</h2><p>invalid OAuth state</p>",
            status_code=400,
        )
    try:
        cache = tiktok.exchange_code_for_token(code)
    except tiktok.TikTokError as exc:
        return HTMLResponse(
            f"<h2>TikTok authorization failed</h2><p>{exc}</p>", status_code=400
        )
    open_id = cache.get("open_id", "")
    return HTMLResponse(
        "<h2>TikTok connected</h2>"
        f"<p>open_id: {open_id}</p>"
        "<p>You can close this tab and return to the creator console.</p>"
    )


@router.get("/callback/{verification_filename}")
@router.get("/tiktok/callback/{verification_filename}")
def tiktok_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)


@router.get("/tiktok/terms", summary="TikTok app Terms of Service page")
def tiktok_terms(request: Request):
    return PlainTextResponse(_load_markdown_doc("tiktok-terms.md"))


@router.get("/tiktok/terms/{verification_filename}")
def tiktok_terms_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)


@router.get("/tiktok/privacy", summary="TikTok app Privacy Policy page")
def tiktok_privacy(request: Request):
    return PlainTextResponse(_load_markdown_doc("tiktok-privacy.md"))


@router.get("/tiktok/privacy/{verification_filename}")
def tiktok_privacy_verification_file(request: Request, verification_filename: str):
    return _serve_verification_file(verification_filename)


@router.post("/tiktok/publish", summary="Publish a finished video to TikTok")
def tiktok_publish(request: Request, body: PublishRequest):
    request_id = base.get_task_id(request)
    base.require_creator_access(request, task_id=request_id)
    video_path = _final_video_path(body.task_id)
    if not os.path.isfile(video_path):
        raise HttpException(
            task_id=body.task_id,
            status_code=404,
            message=f"finished video not found for task {body.task_id}",
        )

    # Fall back to the story metadata persisted at submission time.
    metadata = _load_story_metadata(body.task_id)
    description = body.description
    if description is None:
        description = metadata.get("suggested_description") or metadata.get(
            "comment_card_title", ""
        )
    hashtags = body.hashtags
    if hashtags is None:
        hashtags = metadata.get("suggested_hashtags") or []

    try:
        result = tiktok.publish_video(
            video_path,
            title=body.title,
            description=description,
            hashtags=hashtags,
            privacy=body.privacy,
            cover_timestamp_ms=body.cover_timestamp_ms,
            disable_comment=body.disable_comment,
            disable_duet=body.disable_duet,
            disable_stitch=body.disable_stitch,
            brand_content_toggle=body.brand_content_toggle,
            brand_organic_toggle=body.brand_organic_toggle,
            is_aigc=body.is_aigc,
            poll=body.poll,
        )
        creator_console.record_publish(body.task_id, "direct", result)
    except tiktok.TikTokError as exc:
        raise HttpException(
            task_id=body.task_id, status_code=400, message=str(exc)
        )
    return utils.get_response(200, result)


@router.post("/tiktok/upload-inbox", summary="Upload a finished video to the TikTok inbox")
def tiktok_upload_inbox(request: Request, body: InboxUploadRequest):
    """Send the finished video to the creator's TikTok inbox as a draft.

    Uses the video.upload scope; the creator finishes the caption/privacy and
    posts from within the TikTok app.
    """
    base.require_creator_access(request, task_id=body.task_id)
    video_path = _final_video_path(body.task_id)
    if not os.path.isfile(video_path):
        raise HttpException(
            task_id=body.task_id,
            status_code=404,
            message=f"finished video not found for task {body.task_id}",
        )
    try:
        result = tiktok.upload_video_to_inbox(video_path, poll=body.poll)
        creator_console.record_publish(body.task_id, "inbox", result)
    except tiktok.TikTokError as exc:
        raise HttpException(
            task_id=body.task_id, status_code=400, message=str(exc)
        )
    return utils.get_response(200, result)
