import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class TestCreatorConsoleStaticAssets(unittest.TestCase):
    def test_manual_upload_controls_are_available_after_render(self):
        html = (ROOT_DIR / "resource/public/index.html").read_text(encoding="utf-8")
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")
        css = (
            ROOT_DIR / "resource/public/assets/creator-console.css"
        ).read_text(encoding="utf-8")

        for element_id in (
            "manualUploadPanel",
            "manualRevealFile",
            "manualDownloadFile",
            "manualCaption",
            "copyManualCaption",
        ):
            self.assertIn(f'id="{element_id}"', html)
            self.assertIn(element_id, script)

        self.assertIn("function showManualUpload", script)
        self.assertIn("function revealVideoFile", script)
        self.assertIn("function copyManualCaption", script)
        self.assertIn("showManualUpload(videoUrl)", script)
        self.assertIn("/api/v1/creator/library/", script)
        self.assertIn(".manual-upload-panel", css)
        self.assertIn(".manual-upload-actions", css)
        self.assertIn("white-space: normal", css)

    def test_cancel_controls_are_wired_in_editor_and_queue(self):
        html = (ROOT_DIR / "resource/public/index.html").read_text(encoding="utf-8")
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")

        # Editor cancel button + its handler and the canceled (-2) poll branch.
        self.assertIn('id="cancelTask"', html)
        self.assertIn("function cancelCurrentTask", script)
        self.assertIn("els.cancelTask.addEventListener", script)
        self.assertIn("/cancel", script)
        self.assertIn("task.state === -2", script)

        # Queue-card cancel action.
        self.assertIn('data-action="cancel-queue"', script)
        self.assertIn("/cancel", script)

    def test_finished_queue_clear_control_is_wired(self):
        html = (ROOT_DIR / "resource/public/index.html").read_text(encoding="utf-8")
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="clearFinishedQueue"', html)
        self.assertIn("clearFinishedQueue: document.querySelector", script)
        self.assertIn("function clearFinishedQueue", script)
        self.assertIn("/api/v1/creator/queue/finished", script)
        self.assertIn("els.clearFinishedQueue.addEventListener", script)

    def test_creator_access_key_is_wired_for_tiktok_requests(self):
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATOR_ACCESS_KEY_STORAGE", script)
        self.assertIn("X-Creator-Access-Key", script)
        self.assertIn("function creatorAccessHeaders", script)
        self.assertIn("function promptCreatorAccessKey", script)
        self.assertIn('setTikTokPill("locked", "TikTok: unlock"', script)
        self.assertIn('dataset.action = state === "locked" ? "unlock"', script)

    def test_narrator_gender_override_is_separate_from_detected_metadata(self):
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")

        self.assertIn("currentNarratorGender", script)
        self.assertIn("narrator_gender: currentNarratorGender", script)
        self.assertIn("narrator_gender_override: els.narratorGender.value", script)
        self.assertIn("story.narrator_gender_override || \"\"", script)

    def test_library_uses_platform_publish_status_map(self):
        script = (
            ROOT_DIR / "resource/public/assets/creator-console.js"
        ).read_text(encoding="utf-8")

        self.assertIn("video.publish_status", script)
        self.assertIn("platformStatusLabel", script)


if __name__ == "__main__":
    unittest.main()
