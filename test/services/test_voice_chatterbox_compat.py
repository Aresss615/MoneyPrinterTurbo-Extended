import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import voice


class TestVoiceChatterboxCompat(unittest.TestCase):
    def test_allowlists_omegaconf_checkpoint_globals_for_whisperx(self):
        with patch.dict(voice.os.environ, {}, clear=True):
            with patch.object(voice.torch.serialization, "add_safe_globals") as add_safe_globals:
                voice.configure_torch_safe_globals_for_whisperx()

        add_safe_globals.assert_called_once()
        allowed_names = {item.__name__ for item in add_safe_globals.call_args.args[0]}
        self.assertIn("ListConfig", allowed_names)
        self.assertIn("DictConfig", allowed_names)
        self.assertIn("ContainerMetadata", allowed_names)
        self.assertIn("Any", allowed_names)

    def test_forces_trusted_whisperx_checkpoint_loads_out_of_weights_only_mode(self):
        with patch.dict(voice.os.environ, {}, clear=True):
            voice.configure_torch_safe_globals_for_whisperx()

            self.assertEqual(voice.os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"], "1")


if __name__ == "__main__":
    unittest.main()
