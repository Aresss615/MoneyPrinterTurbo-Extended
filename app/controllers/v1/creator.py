import json
import os

from fastapi import Request
from pydantic import BaseModel

from app.controllers import base
from app.controllers.v1.base import new_router
from app.controllers.v1.video import task_manager
from app.models.exception import HttpException
from app.services import creator_console
from app.services import state as sm
from app.services import task as tm
from app.utils import utils


router = new_router()


class ChatGptImportRequest(BaseModel):
    raw_json: str


def build_validation_response(story: creator_console.CreatorStory):
    estimated_seconds = creator_console.estimate_read_seconds(story.narration_script)
    word_count = len(story.narration_script.split())
    return {
        "story": story.model_dump(),
        "word_count": word_count,
        "estimated_seconds": estimated_seconds,
        "minimum_seconds": creator_console.DEFAULT_MIN_VIDEO_DURATION,
        "meets_minimum_duration": estimated_seconds
        >= creator_console.DEFAULT_MIN_VIDEO_DURATION,
    }


@router.get("/creator/status", summary="Get creator webserver and bot connection status")
def get_creator_status(request: Request):
    sources = creator_console.list_background_sources()
    gameplay_ready = len(sources) > 0
    return utils.get_response(
        200,
        {
            "webserver_connected": True,
            "bot_connected": gameplay_ready,
            "bot_status": "ready" if gameplay_ready else "missing_gameplay",
            "checks": {
                "api_ready": True,
                "gameplay_ready": gameplay_ready,
                "gameplay_dir": str(creator_console.GAMEPLAY_DIR),
                "background_count": len(sources),
                "backgrounds": [p.name for p in sources],
            },
        },
    )


@router.get("/creator/idea-prompt", summary="Get the reusable ChatGPT Reddit idea prompt")
def get_idea_prompt(request: Request):
    return utils.get_response(
        200,
        {
            "prompt": creator_console.CHATGPT_IDEA_PROMPT,
            "minimum_seconds": creator_console.DEFAULT_MIN_VIDEO_DURATION,
            "target_words": "170-230",
        },
    )


@router.post("/creator/import-chatgpt", summary="Normalize ChatGPT story JSON")
def import_chatgpt_story(request: Request, body: ChatGptImportRequest):
    request_id = base.get_task_id(request)
    try:
        story = creator_console.parse_chatgpt_story_json(body.raw_json)
    except (TypeError, ValueError) as exc:
        raise HttpException(task_id=request_id, status_code=400, message=str(exc))
    return utils.get_response(200, build_validation_response(story))


@router.post("/creator/validate", summary="Validate a creator-console story")
def validate_story(request: Request, body: creator_console.CreatorStory):
    return utils.get_response(200, build_validation_response(body))


@router.post("/creator/videos", summary="Generate a creator-console faceless video")
def create_creator_video(request: Request, body: creator_console.CreatorStory):
    task_id = utils.get_uuid()
    request_id = base.get_task_id(request)
    try:
        params = creator_console.build_video_params(body)
        task = {
            "task_id": task_id,
            "request_id": request_id,
            "estimated_seconds": creator_console.estimate_read_seconds(
                body.narration_script
            ),
            "minimum_seconds": creator_console.DEFAULT_MIN_VIDEO_DURATION,
        }
        # Persist the story to disk so the TikTok publish endpoint can auto-fill
        # the caption + hashtags later. State is rewritten as the task progresses
        # (MemoryState.update_task replaces the dict), so disk is the durable home.
        story_path = os.path.join(utils.task_dir(task_id), "story.json")
        with open(story_path, "w", encoding="utf-8") as fp:
            json.dump(body.model_dump(), fp)
        sm.state.update_task(task_id)
        task_manager.add_task(tm.start, task_id=task_id, params=params, stop_at="video")
        return utils.get_response(200, task)
    except ValueError as exc:
        raise HttpException(
            task_id=task_id, status_code=400, message=f"{request_id}: {str(exc)}"
        )
