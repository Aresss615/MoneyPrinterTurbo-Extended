from uuid import uuid4

import hmac
import os

from fastapi import Request

from app.config import config
from app.models.exception import HttpException

CREATOR_ACCESS_KEY_HEADER = "x-creator-access-key"


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request):
    token = get_api_key(request)
    if token != config.app.get("api_key", ""):
        request_id = get_task_id(request)
        request_url = request.url
        user_agent = request.headers.get("user-agent")
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message=f"invalid token: {request_url}, {user_agent}",
        )


def creator_access_key() -> str:
    return (
        os.getenv("CREATOR_ACCESS_KEY")
        or str(config.app.get("creator_access_key", ""))
    ).strip()


def creator_access_key_required() -> bool:
    return bool(creator_access_key())


def has_creator_access(request: Request) -> bool:
    expected = creator_access_key()
    if not expected:
        return True
    provided = request.headers.get(CREATOR_ACCESS_KEY_HEADER, "")
    return hmac.compare_digest(provided, expected)


def require_creator_access(
    request: Request,
    task_id: str | None = None,
    message: str = "creator access key required",
) -> None:
    if has_creator_access(request):
        return
    raise HttpException(
        task_id=task_id or get_task_id(request),
        status_code=401,
        message=message,
    )
