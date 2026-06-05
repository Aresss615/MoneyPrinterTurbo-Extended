import json
import math
import random
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.models.schema import MaterialInfo, VideoParams


ROOT_DIR = Path(__file__).resolve().parents[2]
GAMEPLAY_DIR = ROOT_DIR / "gameplay"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v"}
DEFAULT_VOICE_NAME = "chatterbox:default:Default Voice-Neutral"  # fallback only
DEFAULT_CARD_USERNAME = "u/throwaway_aita"
DEFAULT_MIN_VIDEO_DURATION = 60
CAPTION_FONT = "Montserrat-ExtraBold.ttf"
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 3
SHORT_FORM_WORDS_PER_MINUTE = 165

# Free Edge-TTS voices rotated at random per video for variety. Word-level
# caption highlighting is preserved automatically (the audio is re-transcribed
# independently of the TTS engine). Edit this list to taste.
VOICE_POOL = [
    "en-US-AvaNeural-Female",
    "en-US-AndrewNeural-Male",
    "en-US-EmmaNeural-Female",
    "en-US-BrianNeural-Male",
    "en-US-JennyNeural-Female",
    "en-US-GuyNeural-Male",
    "en-GB-SoniaNeural-Female",
    "en-GB-RyanNeural-Male",
    "en-AU-NatashaNeural-Female",
]


def list_background_sources() -> list[Path]:
    """Discover every background video dropped into ``gameplay/``.

    Both 16:9 and 9:16 sources are supported; landscape clips are
    center-cropped to 9:16 downstream by ``video.resize_clip_to_cover``.
    """
    if not GAMEPLAY_DIR.exists():
        return []
    return sorted(
        p
        for p in GAMEPLAY_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in VIDEO_EXTENSIONS
        and not p.name.startswith(".")
    )


def pick_background_material(rng=random) -> MaterialInfo:
    """Pick one background video at random from ``gameplay/``."""
    sources = list_background_sources()
    if not sources:
        raise FileNotFoundError(f"no background videos found in {GAMEPLAY_DIR}")
    return MaterialInfo(provider="local", url=str(rng.choice(sources)), duration=0)


def pick_voice(rng=random) -> str:
    """Pick one Edge-TTS voice at random from :data:`VOICE_POOL`."""
    pool = VOICE_POOL or [DEFAULT_VOICE_NAME]
    return rng.choice(pool)


CHATGPT_IDEA_PROMPT = """Browse Reddit for a strong short-form story suitable for a faceless TikTok/Reels video.

Target style:
- AITA, relationship drama, entitled people, workplace drama, family conflict, travel/airplane conflict, or roommate conflict
- Clear conflict in the first 2 seconds
- Strong moral dilemma or rage-bait hook
- 60-75 seconds when read aloud
- First-person narration
- Easy to understand without Reddit context
- Safe for monetized short-form content

Rules:
- Use only public Reddit posts.
- Do not include real names, usernames, locations, workplaces, or identifying details.
- Do not invent a Reddit source URL. If you cannot verify a source, say so.
- Paraphrase the story into a clean narration script instead of copying the post word-for-word.
- Keep the emotional conflict, but remove rambling, edits, updates, and unnecessary details.
- Make it sound natural when spoken by TTS.
- End with a question that invites comments.

Return ONLY this JSON:

{
  "source_url": "",
  "subreddit": "",
  "original_title": "",
  "comment_card_username": "u/throwaway_aita",
  "comment_card_title": "",
  "comment_card_likes": "99+",
  "video_subject": "",
  "narration_script": "",
  "caption_keywords_to_highlight": [],
  "suggested_hook": "",
  "suggested_description": "",
  "suggested_hashtags": [],
  "content_notes": ""
}

Field rules:
- comment_card_title: max 120 characters, written like a Reddit post title.
- narration_script: 170-230 words, first person, no markdown, no bullet points.
- caption_keywords_to_highlight: 8-15 short words or phrases that should be red-highlighted in captions.
- suggested_hook: one short sentence for the first 2 seconds.
- suggested_description: TikTok/Reels caption, max 150 characters.
- suggested_hashtags: 5-8 hashtags.
- content_notes: mention if anything was softened, anonymized, or potentially sensitive."""


class CreatorStory(BaseModel):
    source_url: str = ""
    subreddit: str = ""
    original_title: str = ""
    comment_card_username: str = DEFAULT_CARD_USERNAME
    comment_card_title: str = ""
    comment_card_likes: str = "99+"
    video_subject: str = "AITA story"
    narration_script: str
    caption_keywords_to_highlight: list[str] = Field(default_factory=list)
    suggested_hook: str = ""
    suggested_description: str = ""
    suggested_hashtags: list[str] = Field(default_factory=list)
    content_notes: str = ""


def estimate_read_seconds(script: str, words_per_minute: int = SHORT_FORM_WORDS_PER_MINUTE) -> int:
    words = re.findall(r"\b[\w'-]+\b", script or "")
    if not words:
        return 0
    return int(math.ceil(len(words) * 60 / words_per_minute))


def derive_card_title(story: str, max_chars: int = 120) -> str:
    story = " ".join((story or "").strip().split())
    if not story:
        return ""

    for terminator in ("?", ".", "!"):
        idx = story.find(terminator)
        if idx != -1:
            title = story[: idx + 1].strip()
            return truncate_text(title, max_chars)

    return truncate_text(story, max_chars)


def parse_chatgpt_story_json(raw_json: str) -> CreatorStory:
    payload = json.loads(normalize_json_like_text(raw_json))
    if not isinstance(payload, dict):
        raise ValueError("ChatGPT story JSON must be an object.")
    return story_from_mapping(payload)


def story_from_mapping(payload: dict[str, Any]) -> CreatorStory:
    narration = clean_text(payload.get("narration_script") or payload.get("video_script") or "")
    title = clean_text(payload.get("comment_card_title") or "")
    if not title:
        title = derive_card_title(narration)

    return CreatorStory(
        source_url=clean_text(payload.get("source_url") or ""),
        subreddit=clean_text(payload.get("subreddit") or ""),
        original_title=clean_text(payload.get("original_title") or ""),
        comment_card_username=clean_text(
            payload.get("comment_card_username") or DEFAULT_CARD_USERNAME
        ),
        comment_card_title=truncate_text(title, 120),
        comment_card_likes=clean_text(payload.get("comment_card_likes") or "99+"),
        video_subject=clean_text(payload.get("video_subject") or title or "AITA story"),
        narration_script=narration,
        caption_keywords_to_highlight=normalize_string_list(
            payload.get("caption_keywords_to_highlight") or []
        ),
        suggested_hook=clean_text(payload.get("suggested_hook") or ""),
        suggested_description=truncate_text(
            clean_text(payload.get("suggested_description") or ""), 150
        ),
        suggested_hashtags=normalize_hashtags(payload.get("suggested_hashtags") or []),
        content_notes=clean_text(payload.get("content_notes") or ""),
    )


def build_video_params(story: CreatorStory, rng=random) -> VideoParams:
    script = clean_text(story.narration_script)
    if not script:
        raise ValueError("narration_script must not be empty")

    title = story.comment_card_title or derive_card_title(script)
    return VideoParams(
        video_subject=story.video_subject or title or "AITA story",
        video_script=script,
        video_terms="",
        video_aspect="9:16",
        video_concat_mode="sequential",
        video_transition_mode=None,
        video_clip_duration=5,
        video_count=1,
        video_source="local",
        video_materials=[pick_background_material(rng)],
        video_language="en",
        voice_name=pick_voice(rng),
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
        font_size=CAPTION_FONT_SIZE,
        stroke_color="#000000",
        stroke_width=CAPTION_STROKE_WIDTH,
        enable_word_highlighting=True,
        word_highlight_color="#ff0000",
        max_chars_per_line=40,
        max_lines_per_subtitle=2,
        comment_card_enabled=True,
        comment_card_username=story.comment_card_username or DEFAULT_CARD_USERNAME,
        comment_card_title=title,
        comment_card_likes=story.comment_card_likes or "99+",
        comment_card_duration=4.0,
        min_video_duration=DEFAULT_MIN_VIDEO_DURATION,
        n_threads=2,
        paragraph_number=1,
    )


def normalize_json_like_text(raw_json: str) -> str:
    text = strip_json_fence(raw_json)
    return normalize_smart_quotes(text)


def strip_json_fence(raw_json: str) -> str:
    text = (raw_json or "").strip()
    if re.match(r"^(?:`{3,}|~{3,})", text):
        text = re.sub(r"^(?:`{3,}|~{3,})(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*(?:`{3,}|~{3,})$", "", text)
    return text.strip()


def normalize_smart_quotes(text: str) -> str:
    return (text or "").translate(
        str.maketrans(
            {
                "“": '"',
                "”": '"',
                "„": '"',
                "‟": '"',
                "’": "'",
                "‘": "'",
                "‚": "'",
                "‛": "'",
            }
        )
    )


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def truncate_text(value: str, max_chars: int) -> str:
    value = clean_text(value)
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;\n]", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []

    normalized = []
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = clean_text(item)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def normalize_hashtags(value: Any) -> list[str]:
    hashtags = []
    for tag in normalize_string_list(value):
        tag = tag.lstrip("#")
        tag = re.sub(r"\s+", "", tag)
        if tag:
            hashtags.append(f"#{tag}")
    return hashtags
