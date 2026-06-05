import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestGenerateAudioFallback(unittest.TestCase):
    def test_falls_back_to_chatterbox_when_edge_voice_fails(self):
        from app.services import task

        params = types.SimpleNamespace(
            voice_name="en-US-AvaNeural-Female", voice_rate=1.0
        )
        fake_sub_maker = MagicMock()

        # First call (Edge) returns None -> should retry with Chatterbox.
        with patch.object(
            task.voice, "tts", side_effect=[None, fake_sub_maker]
        ) as tts, patch.object(task.voice, "get_audio_duration", return_value=5):
            audio_file, duration, sub_maker = task.generate_audio(
                "fallback-task", params, "AITA for keeping my seat?"
            )

        self.assertEqual(tts.call_count, 2)
        # Retry used the local Chatterbox fallback voice.
        self.assertEqual(
            tts.call_args_list[1].kwargs["voice_name"],
            task.voice.parse_voice_name(task.FALLBACK_VOICE_NAME),
        )
        self.assertEqual(params.voice_name, task.FALLBACK_VOICE_NAME)
        self.assertIs(sub_maker, fake_sub_maker)
        self.assertEqual(duration, 5)

    def test_does_not_retry_when_chatterbox_voice_fails(self):
        from app.services import task

        params = types.SimpleNamespace(
            voice_name="chatterbox:default:Default Voice-Neutral", voice_rate=1.0
        )

        with patch.object(task.voice, "tts", return_value=None) as tts, patch.object(
            task.sm.state, "update_task"
        ):
            audio_file, duration, sub_maker = task.generate_audio(
                "fallback-task-2", params, "AITA?"
            )

        # No fallback when the primary voice is already Chatterbox.
        tts.assert_called_once()
        self.assertIsNone(sub_maker)


if __name__ == "__main__":
    unittest.main()
