import json
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.models.schema import MaterialInfo, VideoParams
from app.utils import utils


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


def pick_voice(rng=random, gender: str = "") -> str:
    """Pick an Edge-TTS voice, filtered by narrator gender when known."""
    gender = (gender or "").strip().lower()
    pool = VOICE_POOL or [DEFAULT_VOICE_NAME]
    if gender in ("male", "female"):
        suffix = f"-{gender.capitalize()}"
        filtered = [voice for voice in pool if voice.endswith(suffix)]
        if filtered:
            pool = filtered
        else:
            logger.warning(
                f"no '{gender}' voices in VOICE_POOL; falling back to a random voice"
            )
    else:
        logger.warning("narrator gender unknown; picking a random voice")
    return rng.choice(pool)


# Reddit demographic self-tags like "28F", "(30m)", "F23", "M 41". The age digit
# adjacent to the M/F is what keeps this from matching stray letters in prose.
_SELF_TAG_RE = re.compile(
    r"\b(?:(?:\d{1,2}\s*([mf]))|(?:([mf])\s*\d{1,2}))\b", re.IGNORECASE
)
# Strong first-person self-identification (weighted high).
_DIRECT_FEMALE_RE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas a woman\b",
        r"\bi'?m a (?:girl|woman)\b",
        r"\bi am a (?:girl|woman)\b",
        r"\bbeing a (?:mom|mother)\b",
    )
]
_DIRECT_MALE_RE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas a man\b",
        r"\bi'?m a (?:guy|man)\b",
        r"\bi am a (?:guy|man)\b",
        r"\bbeing a (?:dad|father)\b",
    )
]
# Partner cues assume a heterosexual relationship — lowest-weight fallback only.
_PARTNER_FEMALE_RE = [
    re.compile(p, re.IGNORECASE)
    for p in (r"\bmy husband\b", r"\bmy fianc[eé]e?\b", r"\bmy boyfriend\b")
]
_PARTNER_MALE_RE = [
    re.compile(p, re.IGNORECASE) for p in (r"\bmy wife\b", r"\bmy girlfriend\b")
]


def _self_tag_gender(text: str) -> str:
    match = _SELF_TAG_RE.search(text)
    if not match:
        return ""
    sex = (match.group(1) or match.group(2) or "").lower()
    return "female" if sex == "f" else "male" if sex == "m" else ""


def resolve_narrator_gender(story: "CreatorStory") -> str:
    """Best-effort narrator gender for voice selection.

    Resolution order: the explicit ``narrator_gender`` field, then Reddit
    self-tags (e.g. ``28F``), then weighted keyword voting over the script.
    Returns ``"male"``/``"female"`` or ``""`` when there is no usable signal.
    """
    explicit = normalize_narrator_gender(getattr(story, "narrator_gender", ""))
    if explicit in ("male", "female"):
        return explicit

    title = getattr(story, "comment_card_title", "") or ""
    script = getattr(story, "narration_script", "") or ""
    text = f"{title}\n{script}"

    tag = _self_tag_gender(text)
    if tag:
        return tag

    female = sum(3 * len(p.findall(text)) for p in _DIRECT_FEMALE_RE)
    male = sum(3 * len(p.findall(text)) for p in _DIRECT_MALE_RE)
    female += sum(len(p.findall(text)) for p in _PARTNER_FEMALE_RE)
    male += sum(len(p.findall(text)) for p in _PARTNER_MALE_RE)
    if female > male:
        return "female"
    if male > female:
        return "male"
    return ""


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

Output format (READ CAREFULLY — invalid JSON cannot be imported):
- Return ONE single, complete JSON object and NOTHING else: no prose before or after, no code fences, no comments.
- It MUST start with `{` and end with `}`. Do not stop early or truncate — emit every field below, then the closing `}`.
- Use straight double quotes `"` for all keys and strings. Never use smart/curly quotes.
- Inside any string value, escape every double quote as `\\"` and write the text as one line — replace real line breaks with `\\n`. This matters most for `narration_script`, which often contains dialogue.
- Do not put a comma after the last field in the object or the last item in an array (no trailing commas).
- If the story has quoted dialogue, prefer single quotes inside the narration (e.g. 'stop') so the JSON stays simple.

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
  "content_notes": "",
  "narrator_gender": ""
}

Field rules:
- comment_card_title: max 120 characters, written like a Reddit post title.
- narration_script: 170-230 words, first person, no markdown, no bullet points.
- caption_keywords_to_highlight: 8-15 short words or phrases that should be red-highlighted in captions.
- suggested_hook: one short sentence for the first 2 seconds.
- suggested_description: TikTok/Reels caption, max 150 characters.
- suggested_hashtags: 5-8 hashtags.
- content_notes: mention if anything was softened, anonymized, or potentially sensitive.
- narrator_gender: "male" or "female" — the gender of the first-person narrator telling the story, inferred from the content. Use "" only if genuinely ambiguous."""


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
    narrator_gender: str = ""


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
    payload = loads_creator_json(normalize_json_like_text(raw_json))
    if not isinstance(payload, dict):
        raise ValueError("ChatGPT story JSON must be an object.")
    return story_from_mapping(payload)


def loads_creator_json(text: str) -> Any:
    """Parse pasted ChatGPT JSON, repairing the breakages LLMs commonly emit.

    Strict :func:`json.loads` is tried first so well-formed input is untouched.
    On failure we run :func:`repair_json_like_text` (escapes inner quotes and
    raw newlines, drops trailing commas) and retry. If it still cannot parse,
    we raise a human-readable :class:`ValueError` instead of leaking a cryptic
    ``Expecting ',' delimiter`` message to the webapp.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        try:
            return json.loads(repair_json_like_text(text))
        except json.JSONDecodeError:
            raise ValueError(
                "Could not parse the pasted JSON. Make sure you copied the "
                "entire object — it must start with '{' and end with '}' — and "
                "that quotes inside the story are escaped. "
                f"(JSON error: {first_error})"
            ) from first_error


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
        narrator_gender=normalize_narrator_gender(payload.get("narrator_gender") or ""),
    )


def build_video_params(story: CreatorStory, rng=random) -> VideoParams:
    script = clean_text(story.narration_script)
    if not script:
        raise ValueError("narration_script must not be empty")

    title = story.comment_card_title or derive_card_title(script)
    gender = resolve_narrator_gender(story)
    # Persist the resolved gender so the dumped story.json is debuggable next time.
    story.narrator_gender = gender
    voice_name = pick_voice(rng, gender=gender)
    logger.info(
        f"narrator gender resolved to '{gender or 'unknown'}' → voice {voice_name}"
    )
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
        voice_name=voice_name,
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


def repair_json_like_text(text: str) -> str:
    """Best-effort repair of almost-valid JSON pasted from an LLM.

    Targets the breakages we actually see when a model fills a long
    ``narration_script`` by hand: unescaped double quotes inside string values
    (dialogue), raw newlines/tabs inside strings, and trailing commas. It walks
    the text once, tracking whether each string is an object key or a value, and
    re-escapes characters that would otherwise abort parsing. Only invoked as a
    fallback after strict parsing fails, so valid JSON is never altered.

    A quote that closes a string is distinguished from an inner quote by what
    follows it: a value's closing quote is followed by ``,``/``}``/``]`` (and a
    ``,`` must in turn be followed by another string, ``}`` or ``]``), while a
    key's closing quote is followed by ``:``. Anything else is treated as an
    unescaped inner quote and escaped in place.
    """
    out: list[str] = []
    stack: list[str] = []  # '{' or '[' for each open container
    expect_key = False  # only meaningful while the current container is '{'
    whitespace = " \t\r\n"
    n = len(text)
    i = 0

    def skip_ws(idx: int) -> int:
        while idx < n and text[idx] in whitespace:
            idx += 1
        return idx

    while i < n:
        ch = text[i]
        if ch == '"':
            is_key = bool(stack) and stack[-1] == "{" and expect_key
            out.append('"')
            i += 1
            while i < n:
                c = text[i]
                if c == "\\":  # keep existing escape sequences verbatim
                    out.append(c)
                    if i + 1 < n:
                        out.append(text[i + 1])
                        i += 2
                    else:
                        i += 1
                    continue
                if c == '"':
                    j = skip_ws(i + 1)
                    nxt = text[j] if j < n else ""
                    if is_key:
                        closing = nxt == ":"
                    elif nxt in ("", "}", "]"):
                        closing = True
                    elif nxt == ",":
                        k = skip_ws(j + 1)
                        after = text[k] if k < n else ""
                        closing = after in ("", '"', "}", "]")
                    else:
                        closing = False
                    if closing:
                        out.append('"')
                        i += 1
                        break
                    out.append('\\"')
                    i += 1
                    continue
                if c == "\n":
                    out.append("\\n")
                elif c == "\r":
                    out.append("\\r")
                elif c == "\t":
                    out.append("\\t")
                else:
                    out.append(c)
                i += 1
            if stack and stack[-1] == "{":
                expect_key = False
            continue
        if ch == "{":
            stack.append("{")
            expect_key = True
            out.append(ch)
        elif ch == "[":
            stack.append("[")
            out.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            out.append(ch)
        elif ch == ":":
            expect_key = False
            out.append(ch)
        elif ch == ",":
            j = skip_ws(i + 1)
            nxt = text[j] if j < n else ""
            if nxt in ("}", "]"):  # trailing comma -> drop it
                i += 1
                continue
            out.append(ch)
            if stack and stack[-1] == "{":
                expect_key = True
        else:
            out.append(ch)
        i += 1

    return "".join(out)


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


def normalize_narrator_gender(value: Any) -> str:
    gender = clean_text(value).lower()
    return gender if gender in ("male", "female") else ""


def publish_marker_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "publish.json")


def record_publish(task_id: str, method: str, result: dict) -> None:
    """Persist that a video was sent to TikTok."""
    marker = {
        "method": method,
        "status": result.get("status", ""),
        "publish_id": result.get("publish_id", ""),
        "posted_at": time.time(),
    }
    with open(publish_marker_path(task_id), "w", encoding="utf-8") as fp:
        json.dump(marker, fp, indent=2)


def load_publish_marker(task_id: str) -> dict:
    path = publish_marker_path(task_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError):
        return {}


def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:max_len].rstrip("-")) or "video"


def list_library_videos() -> list[dict]:
    """Scan storage/tasks for finished videos, newest first."""
    tasks_root = utils.task_dir()
    items = []
    for task_id in os.listdir(tasks_root):
        task_path = os.path.join(tasks_root, task_id)
        video_path = os.path.join(task_path, "final-1.mp4")
        if not os.path.isfile(video_path):
            continue
        story = {}
        story_path = os.path.join(task_path, "story.json")
        if os.path.isfile(story_path):
            try:
                with open(story_path, "r", encoding="utf-8") as fp:
                    story = json.load(fp)
            except (ValueError, OSError):
                story = {}
        title = story.get("comment_card_title") or story.get("video_subject") or task_id
        marker = load_publish_marker(task_id)
        items.append(
            {
                "task_id": task_id,
                "display_name": title,
                "slug": slugify(title),
                "video_url": f"/tasks/{task_id}/final-1.mp4",
                "created_at": os.path.getmtime(video_path),
                "size_bytes": os.path.getsize(video_path),
                "posted": marker,
                "suggested_description": story.get("suggested_description", ""),
                "suggested_hashtags": story.get("suggested_hashtags", []),
            }
        )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items
