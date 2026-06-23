import os
from typing import Optional

from fastapi import Request
from loguru import logger
from pydantic import BaseModel

from app.controllers import base
from app.controllers.v1.base import new_router
from app.models.exception import HttpException
from app.services import creator_console, facebook
from app.utils import utils


router = new_router()


class SetTokenRequest(BaseModel):
    page_id: str
    page_access_token: str


class PublishRequest(BaseModel):
    task_id: str
    description: Optional[str] = None
    title: Optional[str] = None
    published: bool = True


def _final_video_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "final-1.mp4")


@router.get("/facebook/status", summary="Report Facebook page connection status")
def facebook_status(request: Request):
    cache = facebook.load_token_cache()
    connected = bool(cache.get("page_id") and cache.get("page_access_token"))
    page_info = {}
    if connected:
        try:
            page_info = facebook.get_page_info()
        except Exception as exc:
            logger.warning(f"facebook page_info failed: {exc}")
    return utils.get_response(
        200,
        {
            "configured": facebook.is_configured(),
            "connected": connected,
            "page_id": cache.get("page_id", ""),
            "page_name": page_info.get("name", ""),
            "page_info": page_info,
        },
    )


@router.post("/facebook/set-token", summary="Save a Facebook Page Access Token")
def facebook_set_token(request: Request, body: SetTokenRequest):
    request_id = base.get_task_id(request)
    if not body.page_id.strip() or not body.page_access_token.strip():
        raise HttpException(
            task_id=request_id,
            status_code=400,
            message="page_id and page_access_token are required",
        )
    try:
        facebook.save_token_cache(body.page_id, body.page_access_token)
        page_info = facebook.get_page_info(
            page_id=body.page_id.strip(),
            access_token=body.page_access_token.strip(),
        )
    except facebook.FacebookError as exc:
        raise HttpException(task_id=request_id, status_code=400, message=str(exc))
    return utils.get_response(
        200,
        {
            "saved": True,
            "page_id": body.page_id.strip(),
            "page_name": page_info.get("name", ""),
        },
    )


@router.post("/facebook/publish", summary="Publish a finished video to a Facebook Page")
def facebook_publish(request: Request, body: PublishRequest):
    request_id = base.get_task_id(request)
    video_path = _final_video_path(body.task_id)
    if not os.path.isfile(video_path):
        raise HttpException(
            task_id=body.task_id,
            status_code=404,
            message=f"finished video not found for task {body.task_id}",
        )

    try:
        result = facebook.post_video(
            video_path,
            description=body.description or "",
            title=body.title or "",
            published=body.published,
        )
        creator_console.record_facebook_publish(body.task_id, result)
    except facebook.FacebookError as exc:
        raise HttpException(
            task_id=body.task_id, status_code=400, message=str(exc)
        )
    return utils.get_response(200, result)
