import json
import os
import shutil
import threading
import time
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.models import const
from app.services import creator_console, state as sm, task_control, tiktok
from app.utils import utils


QUEUE_DIR_NAME = "creator_queue"
QUEUE_STATE_FILE = "state.json"
FINAL_VIDEO_NAME = "final-1.mp4"
MAX_TIKTOK_CAPTION_CHARS = 2200
MAX_DISPATCH_ATTEMPTS = 3
QUEUE_STATUSES = {
    "queued",
    "rendering",
    "rendered",
    "scheduled",
    "dispatching",
    "sent",
    "failed",
    "canceled",
}
SCHEDULE_ACTIONS = {"draft", "direct"}
FINISHED_QUEUE_STATUSES = {"rendered", "sent", "failed", "canceled"}

_lock = threading.RLock()


class CreatorQueueSchedule(BaseModel):
    run_at_epoch: float
    action: str = "draft"
    timezone_label: str = ""
    attempts: int = 0
    last_attempt_at: float = 0
    last_result: dict[str, Any] = Field(default_factory=dict)
    privacy: str = ""
    cover_timestamp_ms: int | None = None
    disable_comment: bool | None = None
    disable_duet: bool | None = None
    disable_stitch: bool | None = None
    brand_content_toggle: bool | None = None
    brand_organic_toggle: bool | None = None
    is_aigc: bool | None = None
    consent_confirmed: bool = False

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        action = (value or "").strip().lower()
        if action not in SCHEDULE_ACTIONS:
            raise ValueError("schedule action must be draft or direct")
        return action


class CreatorQueueItem(BaseModel):
    queue_id: str
    story: creator_console.CreatorStory
    caption_text: str
    status: str = "queued"
    position: int = 0
    task_id: str = ""
    created_at: float = 0
    updated_at: float = 0
    error: str = ""
    schedule: CreatorQueueSchedule | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        status = (value or "").strip().lower()
        if status not in QUEUE_STATUSES:
            raise ValueError(f"queue status must be one of {sorted(QUEUE_STATUSES)}")
        return status


class CreatorQueueState(BaseModel):
    processing_enabled: bool = False
    updated_at: float = 0


class CreatorQueueScheduler:
    def __init__(
        self,
        start_render: Callable[[creator_console.CreatorStory], dict],
        interval_seconds: float = 5.0,
    ):
        self.start_render = start_render
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        recover_interrupted_rendering()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="creator-queue-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick(self) -> None:
        sync_render_statuses()
        if load_queue_state().processing_enabled:
            start_next_queued_render(self.start_render)
        dispatch_due_schedules()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.tick()
            except Exception as exc:
                logger.warning(f"creator queue scheduler tick failed: {exc}")


def queue_root() -> str:
    return utils.storage_dir(QUEUE_DIR_NAME, create=True)


def queue_state_path() -> str:
    return os.path.join(queue_root(), QUEUE_STATE_FILE)


def queue_item_path(queue_id: str) -> str:
    root = os.path.realpath(queue_root())
    path = os.path.realpath(os.path.join(root, f"{queue_id}.json"))
    try:
        if os.path.commonpath([root, path]) != root:
            raise ValueError
    except ValueError as exc:
        raise FileNotFoundError(f"queue item {queue_id} not found") from exc
    return path


def _atomic_write_json(path: str, payload: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    os.replace(tmp_path, path)


def load_queue_state() -> CreatorQueueState:
    path = queue_state_path()
    if not os.path.isfile(path):
        return CreatorQueueState()
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return CreatorQueueState.model_validate(json.load(fp))
    except (OSError, ValueError):
        return CreatorQueueState()


def save_queue_state(state: CreatorQueueState) -> CreatorQueueState:
    state.updated_at = time.time()
    _atomic_write_json(queue_state_path(), state.model_dump())
    return state


def set_processing_enabled(enabled: bool) -> CreatorQueueState:
    with _lock:
        state = load_queue_state()
        state.processing_enabled = enabled
        return save_queue_state(state)


def load_queue_item(queue_id: str) -> CreatorQueueItem:
    path = queue_item_path(queue_id)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"queue item {queue_id} not found")
    with open(path, "r", encoding="utf-8") as fp:
        return CreatorQueueItem.model_validate(json.load(fp))


def save_queue_item(item: CreatorQueueItem) -> CreatorQueueItem:
    with _lock:
        if not item.created_at:
            item.created_at = time.time()
        item.updated_at = time.time()
        _atomic_write_json(queue_item_path(item.queue_id), item.model_dump())
        return item


def delete_queue_item(queue_id: str) -> CreatorQueueItem:
    with _lock:
        item = load_queue_item(queue_id)
        if item.status == "dispatching":
            raise ValueError("cannot delete an item while it is dispatching")
        os.remove(queue_item_path(queue_id))
        renumber_queue_positions()
        return item


def _task_dir_path(task_id: str) -> str:
    tasks_root = os.path.realpath(utils.task_dir())
    task_path = os.path.realpath(os.path.join(tasks_root, task_id))
    try:
        if os.path.commonpath([tasks_root, task_path]) != tasks_root:
            raise ValueError
    except ValueError:
        return ""
    return task_path


def _delete_task_artifacts(task_id: str) -> None:
    if not task_id:
        return
    task_path = _task_dir_path(task_id)
    if task_path:
        shutil.rmtree(task_path, ignore_errors=True)


def clear_finished_queue_items() -> list[CreatorQueueItem]:
    """Remove terminal queue records while preserving active render/publish work."""
    with _lock:
        sync_render_statuses()
        items = list_queue_items()
        removed = [item for item in items if item.status in FINISHED_QUEUE_STATUSES]
        active_task_ids = {
            item.task_id
            for item in items
            if item.status not in FINISHED_QUEUE_STATUSES and item.task_id
        }
        for task_id in {item.task_id for item in removed if item.task_id}:
            if task_id not in active_task_ids:
                _delete_task_artifacts(task_id)
        for item in removed:
            path = queue_item_path(item.queue_id)
            if os.path.exists(path):
                os.remove(path)
        if removed:
            renumber_queue_positions()
        return removed


def cancel_queue_item(queue_id: str) -> CreatorQueueItem:
    """Cancel a queue item.

    A ``rendering`` item has its render thread asked to stop cooperatively and is
    marked ``canceled``; the scheduler then auto-starts the next queued item. A
    ``dispatching`` item is refused (never interrupt a TikTok upload). Any other
    status is simply marked ``canceled``.
    """
    with _lock:
        item = load_queue_item(queue_id)
        if item.status == "dispatching":
            raise ValueError("cannot cancel an item while it is dispatching")
        if item.status == "rendering" and item.task_id:
            task_control.request_cancel(item.task_id)
        item.status = "canceled"
        item.error = ""
        return save_queue_item(item)


def list_queue_items(status: str | None = None) -> list[CreatorQueueItem]:
    root = Path(queue_root())
    items: list[CreatorQueueItem] = []
    for path in root.glob("*.json"):
        if path.name == QUEUE_STATE_FILE:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fp:
                item = CreatorQueueItem.model_validate(json.load(fp))
        except (OSError, ValueError) as exc:
            logger.warning(f"failed to read creator queue item {path}: {exc}")
            continue
        if status and item.status != status:
            continue
        items.append(item)
    items.sort(key=lambda item: (item.position, item.created_at, item.queue_id))
    return items


def next_queue_position() -> int:
    items = list_queue_items()
    if not items:
        return 1
    return max(item.position for item in items) + 1


def renumber_queue_positions() -> list[CreatorQueueItem]:
    with _lock:
        items = list_queue_items()
        for index, item in enumerate(items, start=1):
            if item.position != index:
                item.position = index
                save_queue_item(item)
        return items


def set_queue_position(queue_id: str, position: int) -> CreatorQueueItem:
    with _lock:
        items = [item for item in list_queue_items() if item.queue_id != queue_id]
        item = load_queue_item(queue_id)
        position = max(1, min(int(position or 1), len(items) + 1))
        items.insert(position - 1, item)
        for index, queued_item in enumerate(items, start=1):
            queued_item.position = index
            save_queue_item(queued_item)
        return load_queue_item(queue_id)


def build_tiktok_caption(
    story: creator_console.CreatorStory, max_chars: int = MAX_TIKTOK_CAPTION_CHARS
) -> str:
    hashtags = creator_console.normalize_hashtags(story.suggested_hashtags)
    caption = creator_console.clean_text(
        " ".join(
            part
            for part in [
                story.suggested_description,
                " ".join(hashtags),
            ]
            if creator_console.clean_text(part)
        )
    )
    if not caption:
        caption = creator_console.clean_text(
            story.comment_card_title or story.video_subject or "AITA story"
        )
    if len(caption) <= max_chars:
        return caption
    return creator_console.truncate_text(caption, max_chars)


def parse_queue_stories(raw_json: str) -> list[creator_console.CreatorStory]:
    text = creator_console.normalize_json_like_text(raw_json)
    try:
        payload = creator_console.loads_creator_json(text)
        return _stories_from_payload(payload)
    except ValueError as first_error:
        try:
            payloads = _decode_multiple_payloads(text)
        except ValueError as exc:
            raise first_error from exc
        return _stories_from_payload(payloads)


def _stories_from_payload(payload: Any) -> list[creator_console.CreatorStory]:
    if isinstance(payload, dict):
        return [creator_console.story_from_mapping(payload)]
    if isinstance(payload, list):
        stories = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("Queue import array must contain JSON objects.")
            stories.append(creator_console.story_from_mapping(entry))
        return stories
    raise ValueError("Queue import must be a JSON object, array, or pasted objects.")


def _decode_multiple_payloads(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    repaired = creator_console.repair_json_like_text(text)
    index = 0
    values = []
    while index < len(repaired):
        while index < len(repaired) and repaired[index].isspace():
            index += 1
        if index >= len(repaired):
            break
        try:
            value, end_index = decoder.raw_decode(repaired, index)
        except JSONDecodeError as exc:
            raise ValueError(f"Could not parse pasted queue JSON: {exc}") from exc
        values.append(value)
        index = end_index
    if not values:
        raise ValueError("Queue import did not contain any JSON objects.")
    return values


def import_queue_items(raw_json: str) -> list[CreatorQueueItem]:
    stories = parse_queue_stories(raw_json)
    now = time.time()
    position = next_queue_position()
    items = []
    with _lock:
        for story in stories:
            item = CreatorQueueItem(
                queue_id=utils.get_uuid(),
                story=story,
                caption_text=build_tiktok_caption(story),
                status="queued",
                position=position,
                created_at=now,
                updated_at=now,
            )
            save_queue_item(item)
            items.append(item)
            position += 1
    return items


def create_scheduled_item_for_task(
    task_id: str,
    story: creator_console.CreatorStory,
    schedule: CreatorQueueSchedule,
    caption_text: str = "",
) -> CreatorQueueItem:
    now = time.time()
    item = CreatorQueueItem(
        queue_id=utils.get_uuid(),
        story=story,
        caption_text=creator_console.clean_text(caption_text)
        or build_tiktok_caption(story),
        status="scheduled",
        position=next_queue_position(),
        task_id=task_id,
        created_at=now,
        updated_at=now,
        schedule=schedule,
    )
    return save_queue_item(item)


def update_queue_item(
    queue_id: str,
    *,
    caption_text: str | None = None,
    status: str | None = None,
    schedule: CreatorQueueSchedule | None = None,
    clear_schedule: bool = False,
    position: int | None = None,
) -> CreatorQueueItem:
    with _lock:
        item = load_queue_item(queue_id)
        if caption_text is not None:
            item.caption_text = creator_console.clean_text(caption_text)
        if clear_schedule:
            item.schedule = None
            if item.status == "scheduled":
                item.status = "rendered" if item.task_id and final_video_exists(item.task_id) else "queued"
        elif schedule is not None:
            item.schedule = schedule
            if item.task_id and final_video_exists(item.task_id):
                item.status = "scheduled"
        if status is not None:
            item.status = status
        save_queue_item(item)
        if position is not None:
            item = set_queue_position(queue_id, position)
        return item


def final_video_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), FINAL_VIDEO_NAME)


def final_video_exists(task_id: str) -> bool:
    return bool(task_id and os.path.isfile(final_video_path(task_id)))


def start_next_queued_render(
    start_render: Callable[[creator_console.CreatorStory], dict]
) -> CreatorQueueItem | None:
    with _lock:
        if any(item.status == "rendering" for item in list_queue_items()):
            return None
        queued = [item for item in list_queue_items() if item.status == "queued"]
        if not queued:
            return None
        item = queued[0]
        item.status = "rendering"
        item.error = ""
        save_queue_item(item)
    try:
        task = start_render(item.story)
        task_id = task.get("task_id", "")
        if not task_id:
            raise ValueError("render start did not return a task_id")
    except Exception as exc:
        with _lock:
            item = load_queue_item(item.queue_id)
            item.status = "failed"
            item.error = str(exc)
            save_queue_item(item)
        return item
    with _lock:
        item = load_queue_item(item.queue_id)
        item.task_id = task_id
        item.status = "rendering"
        item.error = ""
        save_queue_item(item)
        return item


def sync_render_statuses() -> list[CreatorQueueItem]:
    updated = []
    with _lock:
        for item in list_queue_items():
            if item.status != "rendering":
                continue
            if final_video_exists(item.task_id):
                item.status = "scheduled" if item.schedule else "rendered"
                item.error = ""
                updated.append(save_queue_item(item))
                continue
            task = sm.state.get_task(item.task_id) if item.task_id else None
            if task and task.get("state") == const.TASK_STATE_CANCELED:
                item.status = "canceled"
                item.error = ""
                updated.append(save_queue_item(item))
                continue
            if task and task.get("state") == const.TASK_STATE_FAILED:
                item.status = "failed"
                item.error = "Video render failed."
                updated.append(save_queue_item(item))
    return updated


def recover_interrupted_rendering() -> list[CreatorQueueItem]:
    recovered = []
    with _lock:
        for item in list_queue_items():
            if item.status != "rendering":
                continue
            if final_video_exists(item.task_id):
                item.status = "scheduled" if item.schedule else "rendered"
            else:
                item.status = "queued"
                item.task_id = ""
                item.error = "Recovered after app restart."
            recovered.append(save_queue_item(item))
    return recovered


def dispatch_due_schedules(
    now: float | None = None, max_attempts: int = MAX_DISPATCH_ATTEMPTS
) -> CreatorQueueItem | None:
    now = time.time() if now is None else now
    with _lock:
        due = [
            item
            for item in list_queue_items()
            if item.status == "scheduled"
            and item.schedule
            and item.schedule.run_at_epoch <= now
        ]
        if not due:
            return None
        item = due[0]
        item.status = "dispatching"
        item.error = ""
        save_queue_item(item)
    try:
        result = _dispatch_item(item)
    except Exception as exc:
        with _lock:
            item = load_queue_item(item.queue_id)
            assert item.schedule is not None
            item.schedule.attempts += 1
            item.schedule.last_attempt_at = now
            item.schedule.last_result = {"error": str(exc)}
            item.error = str(exc)
            if item.schedule.attempts >= max_attempts:
                item.status = "failed"
            else:
                item.status = "scheduled"
                item.schedule.run_at_epoch = now + _retry_delay_seconds(
                    item.schedule.attempts
                )
            return save_queue_item(item)
    with _lock:
        item = load_queue_item(item.queue_id)
        assert item.schedule is not None
        item.schedule.attempts += 1
        item.schedule.last_attempt_at = now
        item.schedule.last_result = result
        item.status = "sent"
        item.error = ""
        return save_queue_item(item)


def _retry_delay_seconds(attempts: int) -> int:
    return min(3600, 60 * (2 ** max(0, attempts - 1)))


def _dispatch_item(item: CreatorQueueItem) -> dict:
    if not item.schedule:
        raise ValueError("queue item has no schedule")
    if not item.task_id or not final_video_exists(item.task_id):
        raise ValueError("scheduled video is not rendered yet")

    video_path = final_video_path(item.task_id)
    if item.schedule.action == "draft":
        result = tiktok.upload_video_to_inbox(video_path, poll=True)
        creator_console.record_publish(item.task_id, "inbox", result)
        return result

    result = tiktok.publish_video(
        video_path,
        description=item.caption_text,
        hashtags=[],
        privacy=item.schedule.privacy or None,
        cover_timestamp_ms=item.schedule.cover_timestamp_ms,
        disable_comment=item.schedule.disable_comment,
        disable_duet=item.schedule.disable_duet,
        disable_stitch=item.schedule.disable_stitch,
        brand_content_toggle=item.schedule.brand_content_toggle,
        brand_organic_toggle=item.schedule.brand_organic_toggle,
        is_aigc=item.schedule.is_aigc,
        poll=True,
    )
    creator_console.record_publish(item.task_id, "direct", result)
    return result


def scheduled_items_by_task(task_ids: list[str]) -> dict[str, list[CreatorQueueItem]]:
    wanted = set(task_ids)
    result: dict[str, list[CreatorQueueItem]] = {task_id: [] for task_id in task_ids}
    for item in list_queue_items():
        if item.task_id in wanted and item.schedule:
            result.setdefault(item.task_id, []).append(item)
    return result
