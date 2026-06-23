#!/usr/bin/env python3
import argparse
import json
import random
import sys
from pathlib import Path
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.schema import VideoParams
from app.services import creator_console
from app.services import task as task_service
from app.utils import utils


DEFAULT_CARD_USERNAME = "u/throwaway_aita"
CAPTION_FONT = "Montserrat-ExtraBold.ttf"
MIN_VIDEO_SECONDS = 60.0  # TikTok monetization minimum
# Edge-TTS narrates ~2.8 words/sec, so ~270 words ≈ 95s (margin over the 60s
# minimum). Padding (min_video_duration) covers any shortfall.
TARGET_NARRATION_WORDS = 270


def derive_card_title(story: str, max_chars: int = 140) -> str:
    """Use the opening question/sentence of the story as the comment-card title."""
    story = story.strip()
    for terminator in ("?", ".", "!"):
        idx = story.find(terminator)
        if idx != -1:
            return story[: idx + 1].strip()
    if len(story) > max_chars:
        return story[:max_chars].rsplit(" ", 1)[0].strip() + "…"
    return story


def build_video_params(
    story: str, card_username: str = DEFAULT_CARD_USERNAME, rng=random
) -> VideoParams:
    story = story.strip()
    if not story:
        raise ValueError("story must not be empty")

    creator_story = creator_console.CreatorStory(
        narration_script=story,
        comment_card_username=card_username,
        comment_card_title=derive_card_title(story),
    )
    narrator_gender = creator_console.resolve_narrator_gender(creator_story)

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
        video_materials=[creator_console.pick_background_material(rng)],
        video_language="en",
        voice_name=creator_console.pick_voice(rng, gender=narrator_gender),
        voice_volume=1.0,
        voice_rate=1.0,
        bgm_type="",
        bgm_file="",
        bgm_volume=0.0,
        subtitle_enabled=True,
        subtitle_position="center",
        custom_position=70.0,
        font_name=CAPTION_FONT,
        text_fore_color="#FFFFFF",
        text_background_color=False,
        font_size=64,
        stroke_color="#000000",
        stroke_width=3,
        enable_word_highlighting=True,
        word_highlight_color="#ff0000",
        max_chars_per_line=40,
        max_lines_per_subtitle=2,
        comment_card_enabled=True,
        comment_card_username=card_username,
        comment_card_title=derive_card_title(story),
        comment_card_likes="99+",
        comment_card_comments="12",
        comment_card_duration=4.0,
        min_video_duration=MIN_VIDEO_SECONDS,
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
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="Skip LLM narration expansion (use the story text as-is).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    task_id = args.task_id.strip() or utils.get_uuid()

    story = args.story
    if not args.no_expand:
        try:
            from app.services import llm

            story = llm.expand_script(story, target_words=TARGET_NARRATION_WORDS)
        except Exception as exc:
            print(
                f"warning: narration expansion failed, using original story: {exc}",
                file=sys.stderr,
            )

    try:
        params = build_video_params(story)
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
