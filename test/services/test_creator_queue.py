import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestCreatorQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)

        from app.utils import utils

        self.storage_patch = patch.object(
            utils, "storage_dir", side_effect=self._storage_dir
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def _storage_dir(self, sub_dir="", create=False):
        path = self.temp_root
        if sub_dir:
            path = path / sub_dir
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _story_payload(self, title="AITA for leaving?", description="Caption"):
        return {
            "comment_card_title": title,
            "narration_script": "AITA story " * 40,
            "suggested_description": description,
            "suggested_hashtags": ["#aita", "storytime"],
        }

    def test_import_accepts_single_array_and_multiple_json_objects(self):
        from app.services import creator_queue

        single = creator_queue.import_queue_items(
            json.dumps(self._story_payload("Single story", "Single caption"))
        )
        array = creator_queue.import_queue_items(
            json.dumps(
                [
                    self._story_payload("Array one", "First"),
                    self._story_payload("Array two", "Second"),
                ]
            )
        )
        pasted = creator_queue.import_queue_items(
            "\n".join(
                [
                    json.dumps(self._story_payload("Pasted one", "Third")),
                    json.dumps(self._story_payload("Pasted two", "Fourth")),
                ]
            )
        )

        items = creator_queue.list_queue_items()

        self.assertEqual(len(single), 1)
        self.assertEqual(len(array), 2)
        self.assertEqual(len(pasted), 2)
        self.assertEqual([item.position for item in items], [1, 2, 3, 4, 5])
        self.assertEqual(items[0].caption_text, "Single caption #aita #storytime")
        self.assertEqual(items[-1].story.comment_card_title, "Pasted two")

    def test_caption_builder_uses_description_hashtags_and_falls_back_to_title(self):
        from app.services import creator_console, creator_queue

        story = creator_console.CreatorStory(
            narration_script="AITA story " * 40,
            comment_card_title="Fallback title",
            suggested_description="Main caption",
            suggested_hashtags=["aita", "#redditstories"],
        )
        fallback = creator_console.CreatorStory(
            narration_script="AITA story " * 40,
            comment_card_title="Fallback title",
        )

        self.assertEqual(
            creator_queue.build_tiktok_caption(story),
            "Main caption #aita #redditstories",
        )
        self.assertEqual(creator_queue.build_tiktok_caption(fallback), "Fallback title")

    def test_sequential_processor_starts_only_one_queued_render(self):
        from app.services import creator_queue

        creator_queue.import_queue_items(
            json.dumps(
                [
                    self._story_payload("First"),
                    self._story_payload("Second"),
                ]
            )
        )
        started = []

        def start_render(story):
            started.append(story.comment_card_title)
            return {"task_id": f"task-{len(started)}"}

        first = creator_queue.start_next_queued_render(start_render)
        second = creator_queue.start_next_queued_render(start_render)
        items = creator_queue.list_queue_items()

        self.assertEqual(first.task_id, "task-1")
        self.assertIsNone(second)
        self.assertEqual(started, ["First"])
        self.assertEqual([item.status for item in items], ["rendering", "queued"])

    def test_restart_recovery_requeues_rendering_item_without_final_video(self):
        from app.services import creator_queue
        from app.utils import utils

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]
        item.status = "rendering"
        item.task_id = "missing-video"
        creator_queue.save_queue_item(item)

        creator_queue.recover_interrupted_rendering()
        recovered = creator_queue.load_queue_item(item.queue_id)

        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.task_id, "")

        rendered = creator_queue.import_queue_items(
            json.dumps(self._story_payload("Rendered"))
        )[0]
        rendered.status = "rendering"
        rendered.task_id = "done-video"
        Path(utils.task_dir("done-video"), "final-1.mp4").write_bytes(b"video")
        creator_queue.save_queue_item(rendered)

        creator_queue.recover_interrupted_rendering()

        self.assertEqual(creator_queue.load_queue_item(rendered.queue_id).status, "rendered")

    def test_scheduler_dispatches_due_draft_without_caption_payload(self):
        from app.services import creator_queue
        from app.utils import utils

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]
        item.status = "scheduled"
        item.task_id = "draft-task"
        item.schedule = creator_queue.CreatorQueueSchedule(
            run_at_epoch=time.time() - 5,
            action="draft",
            timezone_label="UTC",
        )
        creator_queue.save_queue_item(item)
        Path(utils.task_dir("draft-task"), "final-1.mp4").write_bytes(b"video")

        with patch(
            "app.services.creator_queue.tiktok.upload_video_to_inbox",
            return_value={"status": "PUBLISH_COMPLETE", "publish_id": "draft-1"},
        ) as upload:
            dispatched = creator_queue.dispatch_due_schedules(now=time.time())

        updated = creator_queue.load_queue_item(item.queue_id)

        self.assertEqual(dispatched.queue_id, item.queue_id)
        self.assertEqual(updated.status, "sent")
        upload.assert_called_once()
        self.assertTrue(upload.call_args.args[0].endswith("final-1.mp4"))
        self.assertEqual(upload.call_args.kwargs, {"poll": True})

    def test_scheduler_dispatches_due_direct_with_caption_and_settings(self):
        from app.services import creator_queue
        from app.utils import utils

        item = creator_queue.import_queue_items(
            json.dumps(self._story_payload(description="Direct caption"))
        )[0]
        item.status = "scheduled"
        item.task_id = "direct-task"
        item.schedule = creator_queue.CreatorQueueSchedule(
            run_at_epoch=time.time() - 5,
            action="direct",
            timezone_label="UTC",
            privacy="SELF_ONLY",
            disable_comment=True,
            disable_duet=False,
            disable_stitch=True,
            is_aigc=True,
            consent_confirmed=True,
        )
        creator_queue.save_queue_item(item)
        Path(utils.task_dir("direct-task"), "final-1.mp4").write_bytes(b"video")

        with patch(
            "app.services.creator_queue.tiktok.publish_video",
            return_value={"status": "PUBLISH_COMPLETE", "publish_id": "direct-1"},
        ) as publish:
            creator_queue.dispatch_due_schedules(now=time.time())

        updated = creator_queue.load_queue_item(item.queue_id)

        self.assertEqual(updated.status, "sent")
        self.assertEqual(publish.call_args.kwargs["description"], "Direct caption #aita #storytime")
        self.assertEqual(publish.call_args.kwargs["hashtags"], [])
        self.assertEqual(publish.call_args.kwargs["privacy"], "SELF_ONLY")
        self.assertTrue(publish.call_args.kwargs["disable_comment"])
        self.assertFalse(publish.call_args.kwargs["disable_duet"])
        self.assertTrue(publish.call_args.kwargs["disable_stitch"])
        self.assertTrue(publish.call_args.kwargs["is_aigc"])


    def test_cancel_rendering_item_requests_task_cancel_and_marks_canceled(self):
        from app.services import creator_queue, task_control

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]
        item.status = "rendering"
        item.task_id = "rendering-task"
        creator_queue.save_queue_item(item)
        self.addCleanup(task_control.clear, "rendering-task")

        canceled = creator_queue.cancel_queue_item(item.queue_id)

        self.assertEqual(canceled.status, "canceled")
        self.assertTrue(task_control.is_canceled("rendering-task"))

    def test_cancel_queued_item_marks_canceled_without_task_cancel(self):
        from app.services import creator_queue, task_control

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]

        canceled = creator_queue.cancel_queue_item(item.queue_id)

        self.assertEqual(canceled.status, "canceled")
        self.assertFalse(task_control.is_canceled(item.task_id or item.queue_id))

    def test_cancel_dispatching_item_is_refused(self):
        from app.services import creator_queue

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]
        item.status = "dispatching"
        item.task_id = "dispatching-task"
        creator_queue.save_queue_item(item)

        with self.assertRaises(ValueError):
            creator_queue.cancel_queue_item(item.queue_id)

        self.assertEqual(
            creator_queue.load_queue_item(item.queue_id).status, "dispatching"
        )

    def test_sync_marks_canceled_when_task_state_is_canceled(self):
        from app.models import const
        from app.services import creator_queue
        from app.services import state as sm

        item = creator_queue.import_queue_items(json.dumps(self._story_payload()))[0]
        item.status = "rendering"
        item.task_id = "self-canceled-task"
        creator_queue.save_queue_item(item)
        sm.state.update_task("self-canceled-task", state=const.TASK_STATE_CANCELED)

        creator_queue.sync_render_statuses()

        self.assertEqual(
            creator_queue.load_queue_item(item.queue_id).status, "canceled"
        )

    def test_clear_finished_queue_items_removes_terminal_items_and_keeps_active_work(self):
        from app.services import creator_queue
        from app.utils import utils

        statuses = [
            "queued",
            "rendering",
            "rendered",
            "scheduled",
            "dispatching",
            "sent",
            "failed",
            "canceled",
        ]
        for status in statuses:
            item = creator_queue.import_queue_items(
                json.dumps(self._story_payload(status.title()))
            )[0]
            item.status = status
            if status != "queued":
                item.task_id = f"{status}-task"
                task_path = Path(utils.task_dir(item.task_id))
                if status != "rendering":
                    (task_path / "final-1.mp4").write_bytes(b"video")
            creator_queue.save_queue_item(item)

        removed = creator_queue.clear_finished_queue_items()
        remaining = creator_queue.list_queue_items()

        self.assertEqual(
            [item.status for item in removed],
            ["rendered", "sent", "failed", "canceled"],
        )
        self.assertEqual(
            [item.status for item in remaining],
            ["queued", "rendering", "scheduled", "dispatching"],
        )
        self.assertEqual([item.position for item in remaining], [1, 2, 3, 4])
        for status in ("rendered", "sent", "failed", "canceled"):
            self.assertFalse((self.temp_root / "tasks" / f"{status}-task").exists())
        for status in ("rendering", "scheduled", "dispatching"):
            self.assertTrue((self.temp_root / "tasks" / f"{status}-task").exists())


if __name__ == "__main__":
    unittest.main()
