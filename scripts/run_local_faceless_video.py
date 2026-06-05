#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.schema import MaterialInfo, VideoParams
from app.services import task as task_service
from app.utils import utils


DEFAULT_VOICE_NAME = "chatterbox:default:Default Voice-Neutral"
GAMEPLAY_PATH = ROOT_DIR / "gameplay" / "minecraft-parkour-1.mp4"


def build_video_params(story: str) -> VideoParams:
    story = story.strip()
    if not story:
        raise ValueError("story must not be empty")

    if not GAMEPLAY_PATH.exists():
        raise FileNotFoundError(f"missing local gameplay file: {GAMEPLAY_PATH}")

    return VideoParams(
        video_subject="AITA story",
        video_script=story,
        video_terms="",
        video_aspect="9:16",
        video_concat_mode="sequential",
        video_transition_mode=None,
        video_clip_duration=5,
        video_count=1,
        video_source="local",
        video_materials=[
            MaterialInfo(provider="local", url=str(GAMEPLAY_PATH), duration=0)
        ],
        video_language="en",
        voice_name=DEFAULT_VOICE_NAME,
        voice_volume=1.0,
        voice_rate=1.0,
        bgm_type="",
        bgm_file="",
        bgm_volume=0.0,
        subtitle_enabled=True,
        subtitle_position="bottom",
        custom_position=70.0,
        font_name="STHeitiMedium.ttc",
        text_fore_color="#FFFFFF",
        text_background_color=True,
        font_size=60,
        stroke_color="#000000",
        stroke_width=1.5,
        enable_word_highlighting=True,
        word_highlight_color="#ff0000",
        max_chars_per_line=40,
        max_lines_per_subtitle=2,
        n_threads=2,
        paragraph_number=1,
    )


def build_output(task_id: str, result: dict) -> dict:
    task_dir = Path(utils.task_dir(task_id))
    enhanced_subtitle_path = task_dir / "subtitle_enhanced.json"

    return {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "videos": result.get("videos", []),
        "combined_videos": result.get("combined_videos", []),
        "audio_file": result.get("audio_file", ""),
        "audio_duration": result.get("audio_duration", 0),
        "subtitle_path": result.get("subtitle_path", ""),
        "enhanced_subtitle_path": (
            str(enhanced_subtitle_path) if enhanced_subtitle_path.exists() else ""
        ),
        "materials": result.get("materials", []),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local MoneyPrinterTurbo faceless-video pipeline."
    )
    parser.add_argument("--story", required=True, help="Story text to narrate.")
    parser.add_argument(
        "--task-id",
        default="",
        help="Optional deterministic task id. Defaults to a generated UUID.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    task_id = args.task_id.strip() or utils.get_uuid()

    try:
        params = build_video_params(args.story)
        result = task_service.start(task_id=task_id, params=params, stop_at="video")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not result:
        print("error: video pipeline failed", file=sys.stderr)
        return 1

    print(json.dumps(build_output(task_id, result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
