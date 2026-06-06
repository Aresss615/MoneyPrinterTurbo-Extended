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
            "manualOpenFile",
            "manualDownloadFile",
            "manualCaption",
            "copyManualCaption",
        ):
            self.assertIn(f'id="{element_id}"', html)
            self.assertIn(element_id, script)

        self.assertIn("function showManualUpload", script)
        self.assertIn("function copyManualCaption", script)
        self.assertIn("showManualUpload(videoUrl)", script)
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


if __name__ == "__main__":
    unittest.main()
