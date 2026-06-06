import unittest
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

# add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models import const
from app.services import state as sm
from app.services import task as tm
from app.services import task_control
from app.models.schema import MaterialInfo, VideoParams
from app.utils import utils

resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")

class TestTaskService(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_start_aborts_immediately_when_cancel_requested(self):
        task_id = "cancel-before-start"
        task_path = utils.task_dir(task_id)
        self.addCleanup(shutil.rmtree, task_path, ignore_errors=True)
        self.addCleanup(task_control.clear, task_id)
        task_control.request_cancel(task_id)

        params = VideoParams(
            video_subject="cancel",
            video_script="A short cancellable script.",
            voice_name="en-US-AvaNeural-Female",
        )

        result = tm.start(task_id=task_id, params=params)

        self.assertIsNone(result)
        self.assertEqual(
            sm.state.get_task(task_id).get("state"), const.TASK_STATE_CANCELED
        )
        self.assertFalse(os.path.isdir(task_path))
        self.assertFalse(task_control.is_canceled(task_id))

    def test_start_aborts_at_checkpoint_after_script(self):
        task_id = "cancel-after-script"
        task_path = utils.task_dir(task_id)
        self.addCleanup(shutil.rmtree, task_path, ignore_errors=True)
        self.addCleanup(task_control.clear, task_id)

        def fake_generate_script(tid, _params):
            # Simulate a cancel arriving while the script is being generated.
            task_control.request_cancel(tid)
            return "A generated script."

        params = VideoParams(
            video_subject="cancel",
            video_script="A short cancellable script.",
            voice_name="en-US-AvaNeural-Female",
        )

        with patch.object(tm, "generate_script", side_effect=fake_generate_script):
            result = tm.start(task_id=task_id, params=params)

        self.assertIsNone(result)
        self.assertEqual(
            sm.state.get_task(task_id).get("state"), const.TASK_STATE_CANCELED
        )
        self.assertFalse(os.path.isdir(task_path))
    
    def test_task_local_materials(self):
        task_id = "00000000-0000-0000-0000-000000000000"
        video_materials=[]
        for i in range(1, 4):
            video_materials.append(MaterialInfo(
                provider="local",
                url=os.path.join(resources_dir, f"{i}.png"),
                duration=0
            ))

        params = VideoParams(
            video_subject="金钱的作用",
            video_script="金钱不仅是交换媒介，更是社会资源的分配工具。它能满足基本生存需求，如食物和住房，也能提供教育、医疗等提升生活品质的机会。拥有足够的金钱意味着更多选择权，比如职业自由或创业可能。但金钱的作用也有边界，它无法直接购买幸福、健康或真诚的人际关系。过度追逐财富可能导致价值观扭曲，忽视精神层面的需求。理想的状态是理性看待金钱，将其作为实现目标的工具而非终极目的。",
            video_terms="money importance, wealth and society, financial freedom, money and happiness, role of money",
            video_aspect="9:16",
            video_concat_mode="random",
            video_transition_mode="None",
            video_clip_duration=3,
            video_count=1,
            video_source="local",
            video_materials=video_materials,
            video_language="",
            voice_name="zh-CN-XiaoxiaoNeural-Female",
            voice_volume=1.0,
            voice_rate=1.0,
            bgm_type="random",
            bgm_file="",
            bgm_volume=0.2,
            subtitle_enabled=True,
            subtitle_position="bottom",
            custom_position=70.0,
            font_name="MicrosoftYaHeiBold.ttc",
            text_fore_color="#FFFFFF",
            text_background_color=True,
            font_size=60,
            stroke_color="#000000",
            stroke_width=1.5,
            n_threads=2,
            paragraph_number=1
        )
        result = tm.start(task_id=task_id, params=params)
        print(result)
    

if __name__ == "__main__":
    unittest.main() 