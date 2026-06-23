import json
import os
import shutil
import time

from fastapi import Request
from pydantic import BaseModel

from app.controllers import base
from app.controllers.v1.base import new_router
from app.controllers.v1.video import task_manager
from app.models.exception import HttpException
from app.services import creator_console, creator_queue, task_control, tiktok
from app.services import state as sm
from app.services import task as tm
from app.utils import utils


router = new_router()
_queue_scheduler: creator_queue.CreatorQueueScheduler | None = None


class ChatGptImportRequest(BaseModel):
    raw_json: str


class LibraryCleanupRequest(BaseModel):
    older_than_days: int = 7
    dry_run: bool = False


class LibraryRegenerateRequest(BaseModel):
    narrator_gender: str = ""
    narrator_gender_override: str = ""


class QueueImportRequest(BaseModel):
    raw_json: str


class QueueProcessRequest(BaseModel):
    enabled: bool = True


class QueuePatchRequest(BaseModel):
    caption_text: str | None = None
    status: str | None = None
    position: int | None = None
    schedule: creator_queue.CreatorQueueSchedule | None = None


class LibraryScheduleRequest(BaseModel):
    caption_text: str = ""
    schedule: creator_queue.CreatorQueueSchedule


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
        "warnings": creator_console.duplicate_story_warnings(story),
    }


def _start_creator_video(
    story: creator_console.CreatorStory, request_id: str
) -> dict:
    task_id = utils.get_uuid()
    params = creator_console.build_video_params(story)
    task = {
        "task_id": task_id,
        "request_id": request_id,
        "estimated_seconds": creator_console.estimate_read_seconds(
            story.narration_script
        ),
        "minimum_seconds": creator_console.DEFAULT_MIN_VIDEO_DURATION,
    }
    # Disk is the durable source of story metadata after MemoryState resets.
    story_path = os.path.join(utils.task_dir(task_id), "story.json")
    with open(story_path, "w", encoding="utf-8") as fp:
        json.dump(story.model_dump(), fp)
    sm.state.update_task(task_id)
    task_manager.add_task(tm.start, task_id=task_id, params=params, stop_at="video")
    return task


def _library_task_path(task_id: str) -> str:
    tasks_root = os.path.realpath(utils.task_dir())
    task_path = os.path.realpath(os.path.join(tasks_root, task_id))
    try:
        if os.path.commonpath([tasks_root, task_path]) != tasks_root:
            raise ValueError
    except ValueError as exc:
        raise HttpException(
            task_id=task_id, status_code=404, message=f"task {task_id} not found"
        ) from exc
    if not os.path.isdir(task_path):
        raise HttpException(
            task_id=task_id, status_code=404, message=f"task {task_id} not found"
        )
    return task_path


def _delete_library_task(task_id: str) -> None:
    shutil.rmtree(_library_task_path(task_id))


def _load_library_story(task_id: str) -> creator_console.CreatorStory:
    task_path = _library_task_path(task_id)
    story_path = os.path.join(task_path, "story.json")
    if not os.path.isfile(story_path):
        raise HttpException(
            task_id=task_id,
            status_code=404,
            message=f"story metadata not found for task {task_id}",
        )
    try:
        with open(story_path, "r", encoding="utf-8") as fp:
            return creator_console.story_from_mapping(json.load(fp))
    except (TypeError, ValueError) as exc:
        raise HttpException(task_id=task_id, status_code=400, message=str(exc))


def _validate_schedule(
    schedule: creator_queue.CreatorQueueSchedule, request: Request | None = None
) -> None:
    if schedule.run_at_epoch <= 0:
        raise HttpException(
            task_id="creator-queue",
            status_code=400,
            message="schedule run_at_epoch is required",
        )
    if request is not None:
        base.require_creator_access(request, task_id="creator-queue")
    if schedule.action != "direct":
        return
    if not schedule.privacy:
        raise HttpException(
            task_id="creator-queue",
            status_code=400,
            message="direct schedules require a TikTok privacy setting",
        )
    if not schedule.consent_confirmed:
        raise HttpException(
            task_id="creator-queue",
            status_code=400,
            message="direct schedules require TikTok music usage consent",
        )
    if not tiktok.is_configured() or not tiktok.load_token_cache().get("access_token"):
        raise HttpException(
            task_id="creator-queue",
            status_code=400,
            message="connect TikTok before saving a Direct Post schedule",
        )


def _queue_item_payload(item: creator_queue.CreatorQueueItem) -> dict:
    return item.model_dump()


def start_creator_queue_scheduler() -> None:
    global _queue_scheduler
    if _queue_scheduler is None:
        _queue_scheduler = creator_queue.CreatorQueueScheduler(
            lambda story: _start_creator_video(story, "creator-queue")
        )
    _queue_scheduler.start()


def stop_creator_queue_scheduler() -> None:
    if _queue_scheduler is not None:
        _queue_scheduler.stop()


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
            "prompt": creator_console.build_chatgpt_idea_prompt(),
            "minimum_seconds": creator_console.DEFAULT_MIN_VIDEO_DURATION,
            "target_words": "170-260",
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
    request_id = base.get_task_id(request)
    try:
        return utils.get_response(200, _start_creator_video(body, request_id))
    except ValueError as exc:
        raise HttpException(
            task_id=request_id, status_code=400, message=f"{request_id}: {str(exc)}"
        )


@router.post(
    "/creator/videos/{task_id}/cancel", summary="Cancel a rendering creator video"
)
def cancel_creator_video(request: Request, task_id: str):
    task_control.request_cancel(task_id)
    return utils.get_response(200, {"canceled": task_id})


@router.post("/creator/queue/import", summary="Import ChatGPT JSON into the story queue")
def import_creator_queue(request: Request, body: QueueImportRequest):
    request_id = base.get_task_id(request)
    try:
        items = creator_queue.import_queue_items(body.raw_json)
    except (TypeError, ValueError) as exc:
        raise HttpException(task_id=request_id, status_code=400, message=str(exc))
    return utils.get_response(
        200, {"items": [_queue_item_payload(item) for item in items]}
    )


@router.get("/creator/queue", summary="List story queue items")
def get_creator_queue(request: Request, status: str = ""):
    try:
        items = creator_queue.list_queue_items(status=status or None)
    except ValueError as exc:
        raise HttpException(
            task_id="creator-queue", status_code=400, message=str(exc)
        )
    state = creator_queue.load_queue_state()
    return utils.get_response(
        200,
        {
            "items": [_queue_item_payload(item) for item in items],
            "processing_enabled": state.processing_enabled,
        },
    )


@router.post("/creator/queue/process", summary="Start or pause sequential queue rendering")
def process_creator_queue(request: Request, body: QueueProcessRequest | None = None):
    enabled = True if body is None else body.enabled
    state = creator_queue.set_processing_enabled(enabled)
    started = None
    if enabled:
        started = creator_queue.start_next_queued_render(
            lambda story: _start_creator_video(story, base.get_task_id(request))
        )
    return utils.get_response(
        200,
        {
            "processing_enabled": state.processing_enabled,
            "started": _queue_item_payload(started) if started else None,
        },
    )


@router.delete("/creator/queue/finished", summary="Clear finished story queue items")
def clear_finished_creator_queue(request: Request):
    deleted = creator_queue.clear_finished_queue_items()
    return utils.get_response(
        200,
        {
            "deleted": len(deleted),
            "deleted_ids": [item.queue_id for item in deleted],
            "deleted_statuses": [item.status for item in deleted],
        },
    )


@router.patch("/creator/queue/{queue_id}", summary="Update a story queue item")
def update_creator_queue_item(request: Request, queue_id: str, body: QueuePatchRequest):
    if "schedule" in body.model_fields_set and body.schedule is not None:
        _validate_schedule(body.schedule, request)
    try:
        item = creator_queue.update_queue_item(
            queue_id,
            caption_text=body.caption_text
            if "caption_text" in body.model_fields_set
            else None,
            status=body.status if "status" in body.model_fields_set else None,
            position=body.position if "position" in body.model_fields_set else None,
            schedule=body.schedule if body.schedule is not None else None,
            clear_schedule="schedule" in body.model_fields_set
            and body.schedule is None,
        )
    except FileNotFoundError as exc:
        raise HttpException(task_id=queue_id, status_code=404, message=str(exc))
    except ValueError as exc:
        raise HttpException(task_id=queue_id, status_code=400, message=str(exc))
    return utils.get_response(200, {"item": _queue_item_payload(item)})


@router.delete("/creator/queue/{queue_id}", summary="Remove a story queue item")
def delete_creator_queue_item(request: Request, queue_id: str):
    try:
        deleted = creator_queue.delete_queue_item(queue_id)
    except FileNotFoundError as exc:
        raise HttpException(task_id=queue_id, status_code=404, message=str(exc))
    except ValueError as exc:
        raise HttpException(task_id=queue_id, status_code=400, message=str(exc))
    return utils.get_response(200, {"deleted": deleted.queue_id})


@router.post("/creator/queue/{queue_id}/cancel", summary="Cancel a story queue item")
def cancel_creator_queue_item(request: Request, queue_id: str):
    try:
        item = creator_queue.cancel_queue_item(queue_id)
    except FileNotFoundError as exc:
        raise HttpException(task_id=queue_id, status_code=404, message=str(exc))
    except ValueError as exc:
        raise HttpException(task_id=queue_id, status_code=400, message=str(exc))
    return utils.get_response(200, {"item": _queue_item_payload(item)})


@router.get("/creator/library", summary="List generated creator videos")
def get_creator_library(request: Request):
    videos = creator_console.list_library_videos()
    schedules_by_task = creator_queue.scheduled_items_by_task(
        [video["task_id"] for video in videos]
    )
    for video in videos:
        video["schedules"] = [
            _queue_item_payload(item)
            for item in schedules_by_task.get(video["task_id"], [])
        ]
    return utils.get_response(
        200,
        {
            "videos": videos,
            "total_size_bytes": sum(video["size_bytes"] for video in videos),
        },
    )


@router.post("/creator/library/cleanup", summary="Delete old unposted creator videos")
def cleanup_creator_library(request: Request, body: LibraryCleanupRequest):
    cutoff = time.time() - max(1, body.older_than_days) * 86400
    deleted = []
    freed_bytes = 0
    for video in creator_console.list_library_videos():
        if video["posted"] or video["created_at"] >= cutoff:
            continue
        deleted.append(video["task_id"])
        freed_bytes += video["size_bytes"]
        if not body.dry_run:
            _delete_library_task(video["task_id"])
    return utils.get_response(
        200,
        {"deleted": deleted, "freed_bytes": freed_bytes, "dry_run": body.dry_run},
    )


@router.delete("/creator/library/{task_id}", summary="Delete a generated creator video")
def delete_creator_library_video(request: Request, task_id: str):
    _delete_library_task(task_id)
    return utils.get_response(200, {"deleted": task_id})


@router.post(
    "/creator/library/{task_id}/reveal",
    summary="Reveal a generated creator video in the local file manager",
)
def reveal_creator_library_video(request: Request, task_id: str):
    task_path = _library_task_path(task_id)
    video_path = os.path.join(task_path, "final-1.mp4")
    if not os.path.isfile(video_path):
        raise HttpException(
            task_id=task_id,
            status_code=404,
            message=f"finished video not found for task {task_id}",
        )
    try:
        creator_console.reveal_path_in_file_manager(video_path)
    except OSError as exc:
        raise HttpException(
            task_id=task_id,
            status_code=500,
            message=f"could not open file location: {exc}",
        ) from exc
    return utils.get_response(200, {"task_id": task_id, "path": video_path})


@router.post(
    "/creator/library/{task_id}/regenerate",
    summary="Regenerate a creator video from stored story metadata",
)
def regenerate_creator_library_video(
    request: Request, task_id: str, body: LibraryRegenerateRequest
):
    try:
        story = _load_library_story(task_id)
        if "narrator_gender_override" in body.model_fields_set:
            story.narrator_gender_override = creator_console.normalize_narrator_gender(
                body.narrator_gender_override
            )
        elif "narrator_gender" in body.model_fields_set:
            story.narrator_gender_override = creator_console.normalize_narrator_gender(
                body.narrator_gender
            )
        # TTS timing drives caption sync, so regenerate re-renders the full video
        # instead of swapping audio in place.
        task = _start_creator_video(story, base.get_task_id(request))
    except (TypeError, ValueError) as exc:
        raise HttpException(task_id=task_id, status_code=400, message=str(exc))
    return utils.get_response(200, task)


@router.post(
    "/creator/library/{task_id}/schedule",
    summary="Schedule an existing creator video for TikTok",
)
def schedule_creator_library_video(
    request: Request, task_id: str, body: LibraryScheduleRequest
):
    task_path = _library_task_path(task_id)
    if not os.path.isfile(os.path.join(task_path, "final-1.mp4")):
        raise HttpException(
            task_id=task_id,
            status_code=404,
            message=f"finished video not found for task {task_id}",
        )
    _validate_schedule(body.schedule, request)
    story = _load_library_story(task_id)
    item = creator_queue.create_scheduled_item_for_task(
        task_id,
        story,
        body.schedule,
        caption_text=body.caption_text,
    )
    return utils.get_response(200, {"item": _queue_item_payload(item)})
