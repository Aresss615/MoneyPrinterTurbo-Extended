import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestTaskControl(unittest.TestCase):
    def setUp(self):
        from app.services import task_control

        self.task_control = task_control
        self.addCleanup(task_control.clear, "task-a")
        self.addCleanup(task_control.clear, "task-b")

    def test_request_cancel_marks_task_canceled(self):
        self.assertFalse(self.task_control.is_canceled("task-a"))

        self.task_control.request_cancel("task-a")

        self.assertTrue(self.task_control.is_canceled("task-a"))

    def test_cancel_is_isolated_per_task(self):
        self.task_control.request_cancel("task-a")

        self.assertTrue(self.task_control.is_canceled("task-a"))
        self.assertFalse(self.task_control.is_canceled("task-b"))

    def test_clear_resets_cancel_state(self):
        self.task_control.request_cancel("task-a")

        self.task_control.clear("task-a")

        self.assertFalse(self.task_control.is_canceled("task-a"))

    def test_clear_is_safe_when_not_canceled(self):
        # Should not raise even if the task was never requested for cancel.
        self.task_control.clear("task-b")

        self.assertFalse(self.task_control.is_canceled("task-b"))


if __name__ == "__main__":
    unittest.main()
