import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
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
DEFAULT_MIN_VIDEO_DURATION = 60  # "story" lane floor (seconds)
DEFAULT_MIN_GROWTH = 30  # "growth" lane floor — lets ~35-50s cuts stay short
CAPTION_FONT = "Montserrat-ExtraBold.ttf"
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 3
SHORT_FORM_WORDS_PER_MINUTE = 165
PUBLISH_PLATFORMS = ("tiktok", "facebook", "instagram", "youtube")
DEFAULT_STORY_HISTORY_LIMIT = 12
STORY_FINGERPRINT_WORDS = 48
# Slightly faster than a default read for momentum, the pace a faceless
# Reddit-story clip wants (faster than conversation, slower than synthetic
# overload). Applied via edge-tts in voice.azure_tts_v1.
DEFAULT_VOICE_RATE = 1.1

# A small, curated set of distinctive Edge-TTS voices rotated per video. The
# playbook warns that near-identical synthetic voices make faceless accounts
# interchangeable, so the pool is deliberately short and characterful while
# keeping both genders so resolve_narrator_gender -> pick_voice still works.
# Word-level caption highlighting is preserved automatically (the audio is
# re-transcribed independently of the TTS engine).
VOICE_POOL = [
    "en-US-AndrewNeural-Male",
    "en-US-AvaNeural-Female",
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
        r"\bas (?:a |their |his |her |the )?(?:girl|woman|female|mom|mother)\b",
        r"\bi(?:'|’)?m a (?:girl|woman|female|mom|mother)\b",
        r"\bi am a (?:girl|woman|female|mom|mother)\b",
        r"\bbeing (?:a |their |his |her |the )?(?:mom|mother)\b",
    )
]
_DIRECT_MALE_RE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas (?:a |their |his |her |the )?(?:guy|man|male|dad|father)\b",
        r"\bi(?:'|’)?m a (?:guy|man|male|dad|father)\b",
        r"\bi am a (?:guy|man|male|dad|father)\b",
        r"\bbeing (?:a |their |his |her |the )?(?:dad|father)\b",
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


def _local_narrator_gender(text: str) -> str:
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


def detect_narrator_gender(story: "CreatorStory") -> str:
    title = getattr(story, "comment_card_title", "") or ""
    script = getattr(story, "narration_script", "") or ""
    return _local_narrator_gender(f"{title}\n{script}")


def resolve_narrator_gender(story: "CreatorStory") -> str:
    """Best-effort narrator gender for voice selection.

    Resolution order: manual override, high-confidence local story cues,
    imported/detected story metadata, then unknown. Returns ``"male"``/
    ``"female"`` or ``""`` when there is no usable signal.
    """
    override = normalize_narrator_gender(
        getattr(story, "narrator_gender_override", "")
    )
    if override:
        return override

    detected = detect_narrator_gender(story)
    if detected:
        return detected

    imported = normalize_narrator_gender(getattr(story, "narrator_gender", ""))
    if imported:
        return imported
    return ""


CHATGPT_IDEA_PROMPT = """You are the story scout and scriptwriter for a faceless Reddit-story TikTok account. The account wins on RETENTION, not volume: a strong hook, fast escalation, a reversal, and a verdict question. Find ONE public Reddit story and turn it into a tight spoken script.

Niche — pick EXACTLY ONE territory and make the story clearly belong to it:
1. Family betrayal & inheritance (wills, money, favoritism, hidden paperwork, family duty)
2. Relationship & wedding implosions (cheating, broken engagements, wedding/in-law drama)
3. Workplace revenge & boundaries (unfair bosses, stolen credit, malicious compliance, punished for an emergency)

Retention rules (most important):
- Open AT the moment of conflict. The first sentence is the hook — no backstory, no "so for context".
- Escalate every 5-8 seconds: each beat adds a new fact, stake, secret, or shift in sympathy.
- Include at least one "wait, what?" reversal — a reveal that recontextualizes the story.
- End on a verdict question, never a generic "what do you think" or "part 2".

Pacing template the narration MUST follow:
- 0-3s Hook: start at the conflict.
- 3-8s Premise: who did what to whom.
- 8-15s Friction: the first complicating fact.
- 15-25s Escalation: a new stake, secret, or contradiction.
- 25-40s Reversal: the "wait, what?" beat.
- Final beat: the verdict question.

Length lane (choose one and write to its word count):
- "growth": 90-130 words (~35-50s read aloud). Tighter, one clean reversal.
- "story": 170-260 words (~60-95s read aloud). Room for a second stake and a deeper reversal.
Default to "story" unless the source is too thin to sustain it.

Frame one — comment_card_title is the first thing the viewer sees: a 6-10 word punchy line that STATES the conflict (not a full Reddit title, not a summary).

Write for speech, not reading:
- Vary sentence length. Use short, punchy sentences at the reversal.
- Natural spoken phrasing a TTS voice can read with momentum.

Safety & ethics:
- Use only public Reddit posts.
- Do not include real names, usernames, locations, workplaces, schools, or identifying details.
- Do not invent a Reddit source URL. If you cannot verify a source, leave it blank.
- Paraphrase into a clean narration script instead of copying the post word-for-word.
- Keep the emotional conflict, but remove rambling, edits, updates, and unnecessary details.
- Keep it safe for monetized short-form content (no graphic sexual content, explicit violence, or minors in harm).

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
  "territory": "",
  "length_lane": "story",
  "comment_card_username": "u/throwaway_aita",
  "comment_card_title": "",
  "comment_card_likes": "99+",
  "video_subject": "",
  "narration_script": "",
  "caption_keywords_to_highlight": [],
  "suggested_hook": "",
  "comment_prompt": "",
  "suggested_description": "",
  "suggested_hashtags": [],
  "content_notes": "",
  "narrator_gender": ""
}

Field rules:
- territory: which ONE niche this belongs to — "family", "relationship", or "workplace".
- length_lane: "growth" (90-130 words) or "story" (170-260 words).
- comment_card_title: 6-10 words that STATE the conflict, written like a punchy Reddit title. This is frame one — the first thing the viewer sees.
- narration_script: first person, follows the pacing template, word count set by length_lane, no markdown, no bullet points.
- caption_keywords_to_highlight: 8-15 short words or phrases that should be red-highlighted in captions.
- suggested_hook: the first narrated sentence — the conflict, in one line.
- comment_prompt: the closing verdict question. Use one of: "NTA or YTA?", "Was OP wrong or justified?", "Who was actually in the wrong?", "What would you do?", "Would you cut them off?". Never "part 2" or "comment below".
- suggested_description: TikTok/Reels caption, max 150 characters, plain-language and keyworded for search (name the theme, e.g. "AITA inheritance family drama"), ending with the comment_prompt question.
- suggested_hashtags: 5-8 hashtags.
- content_notes: mention if anything was softened, anonymized, or potentially sensitive.
- narrator_gender: "male" or "female" — the gender of the first-person narrator telling the story, inferred from the content. Use "" only if genuinely ambiguous."""


class CreatorStory(BaseModel):
    source_url: str = ""
    subreddit: str = ""
    original_title: str = ""
    territory: str = ""
    length_lane: str = "story"
    comment_card_username: str = DEFAULT_CARD_USERNAME
    comment_card_title: str = ""
    comment_card_likes: str = "99+"
    video_subject: str = "AITA story"
    narration_script: str
    caption_keywords_to_highlight: list[str] = Field(default_factory=list)
    suggested_hook: str = ""
    comment_prompt: str = ""
    suggested_description: str = ""
    suggested_hashtags: list[str] = Field(default_factory=list)
    content_notes: str = ""
    # Imported/detected narrator metadata. Manual selection lives in
    # narrator_gender_override so Auto does not erase this value.
    narrator_gender: str = ""
    narrator_gender_override: str = ""


def normalize_length_lane(value: Any) -> str:
    """Coerce a length-lane value to ``"growth"`` or ``"story"`` (default)."""
    lane = clean_text(value).lower()
    return lane if lane in ("growth", "story") else "story"


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

    comment_prompt = clean_text(payload.get("comment_prompt") or "")
    description = truncate_text(
        clean_text(payload.get("suggested_description") or ""), 150
    )
    # Growth posts skip the long caption; fall back to the verdict prompt so
    # every clip still ships a judgment-oriented, comment-driving caption.
    if not description and comment_prompt:
        description = truncate_text(comment_prompt, 150)

    return CreatorStory(
        source_url=clean_text(payload.get("source_url") or ""),
        subreddit=clean_text(payload.get("subreddit") or ""),
        original_title=clean_text(payload.get("original_title") or ""),
        territory=clean_text(payload.get("territory") or "").lower(),
        length_lane=normalize_length_lane(payload.get("length_lane")),
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
        comment_prompt=comment_prompt,
        suggested_description=description,
        suggested_hashtags=normalize_hashtags(payload.get("suggested_hashtags") or []),
        content_notes=clean_text(payload.get("content_notes") or ""),
        narrator_gender=normalize_narrator_gender(payload.get("narrator_gender") or ""),
        narrator_gender_override=normalize_narrator_gender(
            payload.get("narrator_gender_override") or ""
        ),
    )


def build_video_params(story: CreatorStory, rng=random) -> VideoParams:
    script = clean_text(story.narration_script)
    if not script:
        raise ValueError("narration_script must not be empty")

    title = story.comment_card_title or derive_card_title(script)
    detected_gender = detect_narrator_gender(story)
    if detected_gender:
        story.narrator_gender = detected_gender
    else:
        story.narrator_gender = normalize_narrator_gender(story.narrator_gender)
    story.narrator_gender_override = normalize_narrator_gender(
        story.narrator_gender_override
    )
    gender = resolve_narrator_gender(story)
    voice_name = pick_voice(rng, gender=gender)
    lane = normalize_length_lane(story.length_lane)
    min_duration = DEFAULT_MIN_GROWTH if lane == "growth" else DEFAULT_MIN_VIDEO_DURATION
    logger.info(
        f"narrator gender resolved to '{gender or 'unknown'}' → voice {voice_name}; "
        f"length lane '{lane}' → min_video_duration {min_duration}s"
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
        voice_rate=DEFAULT_VOICE_RATE,
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
        min_video_duration=min_duration,
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


def _canonical_url(value: str) -> str:
    return clean_text(value).rstrip("/").lower()


def _canonical_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def script_fingerprint(script: str) -> str:
    tokens = re.findall(r"[a-z0-9']+", (script or "").lower())
    if not tokens:
        return ""
    basis = " ".join(tokens[:STORY_FINGERPRINT_WORDS])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _history_entry_from_story(
    story: dict[str, Any], *, created_at: float, origin: str
) -> dict[str, Any] | None:
    if not isinstance(story, dict):
        return None
    title = clean_text(
        story.get("comment_card_title")
        or story.get("original_title")
        or story.get("video_subject")
        or ""
    )
    source_url = clean_text(story.get("source_url") or "")
    script = clean_text(story.get("narration_script") or story.get("video_script") or "")
    fingerprint = script_fingerprint(script)
    if not title and not source_url and not fingerprint:
        return None
    return {
        "title": title,
        "source_url": source_url,
        "script_fingerprint": fingerprint,
        "script_excerpt": truncate_text(script, 140),
        "created_at": created_at,
        "origin": origin,
    }


def _read_json_file(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def generated_story_history(limit: int = DEFAULT_STORY_HISTORY_LIMIT) -> list[dict]:
    """Return recent generated/imported story fingerprints from tasks and queue."""
    entries: list[dict] = []

    tasks_root = Path(utils.task_dir())
    for story_path in tasks_root.glob("*/story.json"):
        try:
            story = _read_json_file(story_path)
            entry = _history_entry_from_story(
                story,
                created_at=story_path.stat().st_mtime,
                origin=f"task:{story_path.parent.name}",
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"failed to read story history item {story_path}: {exc}")
            continue
        if entry:
            entries.append(entry)

    queue_root = Path(utils.storage_dir("creator_queue"))
    if queue_root.exists():
        for item_path in queue_root.glob("*.json"):
            if item_path.name == "state.json":
                continue
            try:
                item = _read_json_file(item_path)
                story = item.get("story", item) if isinstance(item, dict) else {}
                created_at = float(
                    item.get("updated_at") or item.get("created_at") or item_path.stat().st_mtime
                )
                entry = _history_entry_from_story(
                    story, created_at=created_at, origin=f"queue:{item_path.stem}"
                )
            except (OSError, ValueError, TypeError) as exc:
                logger.warning(f"failed to read queue history item {item_path}: {exc}")
                continue
            if entry:
                entries.append(entry)

    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in sorted(entries, key=lambda item: item["created_at"], reverse=True):
        key = (
            _canonical_title(entry.get("title", "")),
            _canonical_url(entry.get("source_url", "")),
            entry.get("script_fingerprint", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def duplicate_story_warnings(story: CreatorStory) -> list[str]:
    warnings: list[str] = []
    source_url = _canonical_url(story.source_url)
    title = _canonical_title(story.comment_card_title or story.original_title)
    fingerprint = script_fingerprint(story.narration_script)

    for entry in generated_story_history(limit=50):
        entry_title = _canonical_title(entry.get("title", ""))
        entry_url = _canonical_url(entry.get("source_url", ""))
        entry_fingerprint = entry.get("script_fingerprint", "")
        label = entry.get("title") or entry.get("source_url") or entry.get("origin", "story")
        if source_url and source_url == entry_url:
            warnings.append(f"Possible duplicate source URL: {label}")
        if title and title == entry_title:
            warnings.append(f"Possible duplicate title: {label}")
        if fingerprint and fingerprint == entry_fingerprint:
            warnings.append(f"Possible duplicate script fingerprint: {label}")
    return list(dict.fromkeys(warnings))


def build_chatgpt_idea_prompt(limit: int = DEFAULT_STORY_HISTORY_LIMIT) -> str:
    history = generated_story_history(limit=limit)
    lines = [
        "Do not reuse these stories/topics/sources:",
        "- Every new ChatGPT chat is stateless: treat this section as the only memory of what has already been generated.",
        "- Avoid the listed titles, source URLs, script fingerprints, and substantially similar themes.",
    ]
    if history:
        for entry in history:
            title = entry.get("title") or "Untitled story"
            source = entry.get("source_url") or "source blank"
            fingerprint = entry.get("script_fingerprint") or "no-script"
            excerpt = entry.get("script_excerpt") or ""
            lines.append(
                f"- {title} | {source} | script:{fingerprint}"
                + (f" | {excerpt}" if excerpt else "")
            )
    else:
        lines.append("- No recent local stories found, but still avoid repeating obvious Reddit classics.")
    return f"{CHATGPT_IDEA_PROMPT}\n\n" + "\n".join(lines)


def publish_marker_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "publish.json")


def facebook_publish_marker_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "facebook_publish.json")


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


def record_facebook_publish(task_id: str, result: dict) -> None:
    """Persist that a video was posted to a Facebook Page."""
    marker = {
        "method": "facebook",
        "video_id": result.get("id", ""),
        "posted_at": time.time(),
    }
    with open(facebook_publish_marker_path(task_id), "w", encoding="utf-8") as fp:
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


def load_facebook_publish_marker(task_id: str) -> dict:
    path = facebook_publish_marker_path(task_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError):
        return {}


def platform_publish_status(task_id: str) -> dict[str, dict]:
    status = {platform: {} for platform in PUBLISH_PLATFORMS}
    status["tiktok"] = load_publish_marker(task_id)
    status["facebook"] = load_facebook_publish_marker(task_id)
    return status


def reveal_path_in_file_manager(path: str) -> None:
    """Ask the local OS to reveal a generated file in its file manager."""
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(str(target))

    if sys.platform == "darwin":
        command = ["open", "-R", str(target)]
    elif sys.platform.startswith("win"):
        command = ["explorer", f"/select,{target}"]
    else:
        command = ["xdg-open", str(target.parent if target.is_file() else target)]
    subprocess.Popen(command)


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
        fb_marker = load_facebook_publish_marker(task_id)
        items.append(
            {
                "task_id": task_id,
                "display_name": title,
                "slug": slugify(title),
                "video_url": f"/tasks/{task_id}/final-1.mp4",
                "created_at": os.path.getmtime(video_path),
                "size_bytes": os.path.getsize(video_path),
                "posted": marker,
                "facebook_posted": fb_marker,
                "publish_status": platform_publish_status(task_id),
                "suggested_description": story.get("suggested_description", ""),
                "suggested_hashtags": story.get("suggested_hashtags", []),
            }
        )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items
