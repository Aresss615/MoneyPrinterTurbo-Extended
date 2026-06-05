#!/usr/bin/env python3

import glob
import itertools
import math
import os
import re
import random
import gc
import shutil
import json
from typing import List
from loguru import logger
import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    vfx,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont, ImageDraw, Image, ImageFilter

from app.models import const
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.utils import utils
from app.services import semantic_video

# High-quality video encoding settings
audio_codec = "aac"
video_codec = "libx264"
fps = 30

# High-quality encoding parameters
video_bitrate = "8000k"  # High bitrate for excellent quality
audio_bitrate = "320k"   # High audio bitrate
crf = 18                 # Constant Rate Factor - lower = higher quality (18-23 is excellent range)
preset = "medium"        # Balance between encoding speed and compression efficiency

# FFmpeg parameters for maximum quality
quality_params = [
    "-crf", str(crf),
    "-preset", preset,
    "-profile:v", "high",
    "-level", "4.1",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart"
]

class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        if duration is None:
            self.duration = end_time - start_time
        else:
            self.duration = duration

    def __str__(self):
        return f"SubClippedVideoClip(file_path={self.file_path}, start_time={self.start_time}, end_time={self.end_time}, duration={self.duration}, width={self.width}, height={self.height})"


def _normalize_word(word: str) -> str:
    """Lowercase and strip all non-alphanumeric characters for matching."""
    return re.sub(r"[^0-9a-z]+", "", (word or "").lower())


def align_spoken_words(text_words, spoken_words):
    """Map each spoken word (in order) to its index in ``text_words``.

    Uses a forward-advancing pointer so repeated words highlight the correct
    occurrence (e.g. the second spoken "the" maps to the second "the" in the
    text, not the first). Punctuation/case are ignored. Returns a list the same
    length as ``spoken_words``; entries are -1 when no match exists, and fall
    back to any earlier occurrence when there is no remaining forward match.
    """
    norm_text = [_normalize_word(w) for w in text_words]
    result = []
    pointer = 0
    for spoken in spoken_words:
        target = _normalize_word(spoken)
        idx = -1
        if target:
            for j in range(pointer, len(norm_text)):
                if norm_text[j] == target:
                    idx = j
                    pointer = j + 1
                    break
            if idx == -1:
                for j, tw in enumerate(norm_text):
                    if tw == target:
                        idx = j
                        break
        result.append(idx)
    return result


def sequential_subclips_needed(audio_duration: float, max_clip_duration: int) -> int:
    """How many consecutive max-length subclips are needed to cover the audio.

    Sequential mode previously took a single subclip per source video, which
    left long narrations with only a few seconds of footage (and a black screen
    for the remainder). For a single long gameplay source we instead walk enough
    consecutive subclips to span the whole narration.
    """
    if max_clip_duration <= 0:
        return 1
    return max(1, math.ceil(audio_duration / max_clip_duration))


def _load_font(font_path: str, size: int):
    """Load a truetype font, falling back to PIL's default if unavailable."""
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text_pixels(text: str, font, max_width: int) -> list:
    """Greedy word-wrap a string to fit within max_width pixels for the font."""
    words = text.split()
    if not words:
        return [""]

    def text_width(s: str) -> float:
        try:
            return font.getlength(s)
        except Exception:
            return font.getbbox(s)[2]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(font, text: str) -> float:
    try:
        return font.getlength(text)
    except Exception:
        return font.getbbox(text)[2]


def create_comment_card_image(
    width: int,
    username: str,
    title: str,
    font_path: str,
    likes: str = "99+",
    comments: str = "12",
    verified: bool = True,
):
    """Render a Reddit/TikTok-style comment card as an RGBA PIL image.

    Matches the reference card: a translucent dark rounded panel with a drop
    shadow, an avatar, the username + verified badge, a "now playing" music
    chip, a row of reaction emojis, the wrapped title, and a like / comment /
    share footer row. The overall image width equals ``width`` (the card is
    inset to leave room for the shadow); height grows with the wrapped title.
    """
    shadow_pad = max(6, int(width * 0.028))
    card_w = width - 2 * shadow_pad

    pad = int(card_w * 0.05)
    avatar_d = int(card_w * 0.115)
    username_size = max(14, int(card_w * 0.046))
    title_size = max(16, int(card_w * 0.064))
    footer_size = max(13, int(card_w * 0.042))
    emoji_size = max(14, int(card_w * 0.05))

    username_font = _load_font(font_path, username_size)
    title_font = _load_font(font_path, title_size)
    footer_font = _load_font(font_path, footer_size)
    chip_font = _load_font(font_path, max(12, int(card_w * 0.034)))

    text_left = pad + avatar_d + int(card_w * 0.03)
    title_max_width = card_w - 2 * pad
    title_lines = _wrap_text_pixels(title, title_font, title_max_width)

    line_gap = int(title_size * 0.32)
    title_line_h = title_size + line_gap
    title_block_h = title_line_h * len(title_lines)

    header_h = avatar_d
    reactions_h = emoji_size
    footer_h = int(footer_size * 1.8)
    gap = int(card_w * 0.03)

    card_h = pad + header_h + gap + reactions_h + gap + title_block_h + gap + footer_h + pad
    img_h = card_h + 2 * shadow_pad

    img = Image.new("RGBA", (width, img_h), (0, 0, 0, 0))
    radius = int(card_w * 0.055)

    # Drop shadow
    shadow = Image.new("RGBA", (width, img_h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [shadow_pad, shadow_pad + int(shadow_pad * 0.4),
         shadow_pad + card_w, shadow_pad + card_h + int(shadow_pad * 0.4)],
        radius=radius, fill=(0, 0, 0, 150),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_pad * 0.7))
    img.alpha_composite(shadow)

    # Card body drawn on its own layer, then pasted at the shadow offset
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=radius, fill=(18, 18, 22, 240))

    # Avatar (gray disc with a simple person silhouette)
    ax0, ay0 = pad, pad
    ax1, ay1 = pad + avatar_d, pad + avatar_d
    draw.ellipse([ax0, ay0, ax1, ay1], fill=(122, 126, 135, 255))
    head_r = avatar_d * 0.18
    cx = (ax0 + ax1) / 2
    draw.ellipse(
        [cx - head_r, ay0 + avatar_d * 0.22, cx + head_r, ay0 + avatar_d * 0.22 + 2 * head_r],
        fill=(60, 63, 70, 255),
    )
    draw.ellipse(
        [ax0 + avatar_d * 0.22, ay0 + avatar_d * 0.58, ax1 - avatar_d * 0.22, ay1 + avatar_d * 0.30],
        fill=(60, 63, 70, 255),
    )

    # Username + verified badge
    uname_y = pad + (avatar_d - username_size) // 2 - int(username_size * 0.15)
    draw.text((text_left, uname_y), username, font=username_font, fill=(236, 236, 240, 255))
    uname_w = _text_width(username_font, username)
    if verified:
        badge_d = int(username_size * 0.95)
        bx = int(text_left + uname_w + card_w * 0.02)
        by = int(uname_y + (username_size - badge_d) // 2)
        draw.ellipse([bx, by, bx + badge_d, by + badge_d], fill=(64, 150, 255, 255))
        draw.line(
            [(bx + badge_d * 0.27, by + badge_d * 0.52),
             (bx + badge_d * 0.43, by + badge_d * 0.68),
             (bx + badge_d * 0.75, by + badge_d * 0.32)],
            fill=(255, 255, 255, 255), width=max(2, badge_d // 8), joint="curve",
        )

    # Now-playing music chip (top-right)
    _draw_music_chip(draw, card_w - pad, pad, chip_font, "0:09", card_w)

    # Reaction emoji row
    ry = pad + header_h + gap
    _draw_reactions(card, text_left, ry, emoji_size)

    # Title
    ty = pad + header_h + gap + reactions_h + gap
    for line in title_lines:
        draw.text((pad, ty), line, font=title_font, fill=(246, 246, 249, 255))
        ty += title_line_h

    # Footer: heart + likes, speech bubble + comments, share on the right
    fy = card_h - pad - footer_h
    icon = int(footer_size * 1.05)
    fcolor = (205, 205, 210, 255)
    cy = fy + (footer_h - footer_size) // 2

    hx = pad
    _draw_heart(draw, hx, fy + (footer_h - icon) // 2, icon, fill=(255, 92, 97, 255))
    draw.text((hx + icon + int(card_w * 0.015), cy), likes, font=footer_font, fill=fcolor)

    bx = int(hx + icon + int(card_w * 0.015) + _text_width(footer_font, likes) + card_w * 0.05)
    _draw_speech_bubble(draw, bx, fy + (footer_h - icon) // 2, icon, fcolor)
    draw.text((bx + icon + int(card_w * 0.015), cy), comments, font=footer_font, fill=fcolor)

    share_text = "Share"
    share_w = _text_width(footer_font, share_text)
    arrow = int(footer_size * 0.95)
    sx = int(card_w - pad - share_w)
    _draw_share_arrow(draw, sx - arrow - int(card_w * 0.012), fy + (footer_h - arrow) // 2, arrow, fcolor)
    draw.text((sx, cy), share_text, font=footer_font, fill=fcolor)

    img.alpha_composite(card, (shadow_pad, shadow_pad))
    return img


def _draw_heart(draw, x, y, size, fill):
    """Draw a small filled heart with its top-left at (x, y)."""
    r = size / 4
    draw.ellipse([x, y, x + 2 * r, y + 2 * r], fill=fill)
    draw.ellipse([x + 2 * r, y, x + 4 * r, y + 2 * r], fill=fill)
    draw.polygon([(x, y + r), (x + 2 * r, y + size), (x + 4 * r, y + r)], fill=fill)


def _draw_speech_bubble(draw, x, y, size, color):
    """Draw a small outlined speech bubble (comment icon)."""
    w = max(2, size // 9)
    draw.rounded_rectangle([x, y, x + size, y + size * 0.78], radius=size // 4, outline=color, width=w)
    draw.polygon([(x + size * 0.25, y + size * 0.78),
                  (x + size * 0.25, y + size),
                  (x + size * 0.5, y + size * 0.78)], fill=color)


def _draw_share_arrow(draw, x, y, size, color):
    """Draw a small share/reply arrow."""
    w = max(2, size // 8)
    draw.arc([x, y + size * 0.15, x + size, y + size * 1.1], start=200, end=340, fill=color, width=w)
    draw.line([(x + size * 0.5, y), (x + size, y + size * 0.32), (x + size * 0.5, y + size * 0.62)],
              fill=color, width=w, joint="curve")


def _draw_music_chip(draw, right_x, top_y, font, text, card_w):
    """Draw a rounded 'now playing' chip with a music note, right-aligned at right_x."""
    note_d = max(6, int(card_w * 0.02))
    text_w = _text_width(font, text)
    inner_pad = int(card_w * 0.018)
    gap = int(card_w * 0.012)
    chip_w = int(inner_pad + note_d * 1.8 + gap + text_w + inner_pad)
    chip_h = int(max(note_d * 2.4, _text_width(font, "0") and font.size * 1.6))
    x0 = int(right_x - chip_w)
    y0 = top_y
    draw.rounded_rectangle([x0, y0, x0 + chip_w, y0 + chip_h], radius=chip_h // 2, fill=(44, 44, 50, 235))
    # music note: head + stem
    nx = x0 + inner_pad
    ny = y0 + chip_h // 2
    draw.ellipse([nx, ny, nx + note_d, ny + note_d * 0.8], fill=(235, 235, 240, 255))
    stem_x = nx + note_d - max(1, note_d // 6)
    draw.line([(stem_x, ny + note_d * 0.4), (stem_x, ny - note_d)], fill=(235, 235, 240, 255), width=max(2, note_d // 5))
    draw.line([(stem_x, ny - note_d), (stem_x + note_d * 0.6, ny - note_d * 0.7)], fill=(235, 235, 240, 255), width=max(2, note_d // 5))
    draw.text((nx + note_d * 1.8 + gap, y0 + (chip_h - font.size) // 2), text, font=font, fill=(225, 225, 230, 255))


def _draw_reactions(card_img, x, y, size):
    """Draw a small row of reaction emojis (smile, surprise, heart)."""
    draw = ImageDraw.Draw(card_img)
    yellow = (255, 199, 64, 255)
    dark = (60, 50, 20, 255)
    step = int(size * 1.18)

    # smiley
    cx = x
    draw.ellipse([cx, y, cx + size, y + size], fill=yellow)
    er = size * 0.10
    draw.ellipse([cx + size * 0.30 - er, y + size * 0.36 - er, cx + size * 0.30 + er, y + size * 0.36 + er], fill=dark)
    draw.ellipse([cx + size * 0.70 - er, y + size * 0.36 - er, cx + size * 0.70 + er, y + size * 0.36 + er], fill=dark)
    draw.arc([cx + size * 0.25, y + size * 0.35, cx + size * 0.75, y + size * 0.80], start=20, end=160, fill=dark, width=max(2, size // 12))

    # surprised (O mouth)
    cx = x + step
    draw.ellipse([cx, y, cx + size, y + size], fill=yellow)
    draw.ellipse([cx + size * 0.30 - er, y + size * 0.34 - er, cx + size * 0.30 + er, y + size * 0.34 + er], fill=dark)
    draw.ellipse([cx + size * 0.70 - er, y + size * 0.34 - er, cx + size * 0.70 + er, y + size * 0.34 + er], fill=dark)
    draw.ellipse([cx + size * 0.40, y + size * 0.55, cx + size * 0.60, y + size * 0.80], outline=dark, width=max(2, size // 12))

    # heart reaction
    cx = x + 2 * step
    _draw_heart(draw, cx, int(y + size * 0.12), int(size * 0.82), fill=(255, 92, 97, 255))


def create_comment_card_clip(params, video_width: int, video_height: int, font_path: str):
    """Build a positioned, time-limited ImageClip of the comment card overlay.

    Returns None when no title/subject text is available. The card is shown for
    the opening ``comment_card_duration`` seconds, fading out at the end.
    """
    title = (getattr(params, "comment_card_title", "") or "").strip()
    if not title:
        title = (getattr(params, "video_subject", "") or "").strip()
    if not title:
        return None

    username = getattr(params, "comment_card_username", None) or "u/throwaway"
    likes = getattr(params, "comment_card_likes", None) or "99+"
    comments = getattr(params, "comment_card_comments", None) or "12"
    duration = float(getattr(params, "comment_card_duration", 4.0) or 4.0)

    card_width = int(video_width * 0.86)
    card_img = create_comment_card_image(
        width=card_width,
        username=username,
        title=title,
        font_path=font_path,
        likes=likes,
        comments=comments,
    )

    clip = ImageClip(np.array(card_img)).with_start(0).with_duration(duration)
    y = int(video_height * 0.26)
    clip = clip.with_position(("center", y))
    try:
        clip = clip.with_effects([vfx.CrossFadeOut(0.4)])
    except Exception as e:
        logger.warning(f"comment card fade-out unavailable: {e}")
    return clip


def calculate_cover_resize_and_crop(source_size: tuple[int, int], target_size: tuple[int, int]):
    source_width, source_height = source_size
    target_width, target_height = target_size

    scale_factor = max(target_width / source_width, target_height / source_height)
    scaled_width = max(target_width, round(source_width * scale_factor))
    scaled_height = max(target_height, round(source_height * scale_factor))

    x1 = max(0, (scaled_width - target_width) // 2)
    y1 = max(0, (scaled_height - target_height) // 2)
    x2 = x1 + target_width
    y2 = y1 + target_height

    return (scaled_width, scaled_height), (x1, y1, x2, y2)


def resize_clip_to_cover(clip, target_width: int, target_height: int):
    scaled_size, crop_box = calculate_cover_resize_and_crop(
        source_size=clip.size,
        target_size=(target_width, target_height),
    )

    x1, y1, x2, y2 = crop_box
    return clip.resized(new_size=scaled_size).cropped(x1=x1, y1=y1, x2=x2, y2=y2)


def close_clip(clip):
    if clip is None:
        return
        
    try:
        # close main resources
        if hasattr(clip, 'reader') and clip.reader is not None:
            clip.reader.close()
            
        # close audio resources
        if hasattr(clip, 'audio') and clip.audio is not None:
            if hasattr(clip.audio, 'reader') and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
            
        # close mask resources
        if hasattr(clip, 'mask') and clip.mask is not None:
            if hasattr(clip.mask, 'reader') and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
            
        # handle child clips in composite clips
        if hasattr(clip, 'clips') and clip.clips:
            for child_clip in clip.clips:
                if child_clip is not clip:  # avoid possible circular references
                    close_clip(child_clip)
            
        # clear clip list
        if hasattr(clip, 'clips'):
            clip.clips = []
            
    except Exception as e:
        logger.error(f"failed to close clip: {str(e)}")
    
    del clip
    gc.collect()

def delete_files(files: List[str] | str):
    if isinstance(files, str):
        files = [files]
        
    for file in files:
        try:
            os.remove(file)
        except OSError:
            pass

def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = None,
    max_clip_duration: int = 5,
    threads: int = 2,
    script: str = "",
    params: VideoParams = None,
    min_video_duration: float = 0,
) -> str:
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    logger.info(f"audio duration: {audio_duration} seconds")
    # Build gameplay to at least this long; lets the video run past the
    # narration (e.g. to satisfy a platform minimum length) with a silent tail.
    target_duration = max(audio_duration, float(min_video_duration or 0))
    if target_duration > audio_duration:
        logger.info(f"target video duration (min length): {target_duration} seconds")
    # Required duration of each clip
    req_dur = audio_duration / len(video_paths)
    req_dur = max_clip_duration
    logger.info(f"maximum clip duration: {req_dur} seconds")
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    # Check if semantic mode is enabled
    if video_concat_mode.value == "semantic" and script:
        logger.info("Using semantic video selection mode")
        
        # Load video metadata
        video_metadata = []
        for video_path in video_paths:
            metadata = semantic_video.load_video_metadata(video_path)
            if metadata:
                video_metadata.append(metadata)
            else:
                logger.debug(f"No metadata found for {video_path}, using filename")
                filename = os.path.splitext(os.path.basename(video_path))[0]
                metadata = {
                    'video_path': video_path,
                    'search_term': filename,
                    'file_size': os.path.getsize(video_path) if os.path.exists(video_path) else 0,
                    'created_at': os.path.getctime(video_path) if os.path.exists(video_path) else 0
                }
                video_metadata.append(metadata)
        
        # Use semantic video selection
        selected_videos = semantic_video.select_videos_for_script(
            script=script,
            video_metadata=video_metadata,
            audio_duration=audio_duration,
            max_clip_duration=max_clip_duration,
            similarity_threshold=params.similarity_threshold if params else 0.5,
            diversity_threshold=params.diversity_threshold if params else 5,
            max_video_reuse=params.max_video_reuse if params else 2,
            min_segment_length=params.min_segment_length if params else 25,
            semantic_model=params.semantic_model if params else "all-mpnet-base-v2",
            enable_image_similarity=params.enable_image_similarity if params else False,
            image_similarity_threshold=params.image_similarity_threshold if params else 0.7,
            image_similarity_model=params.image_similarity_model if params else "clip-vit-base-patch32"
        )
        
        # Process selected videos
        processed_clips = []
        video_duration = 0
        max_reuse_limit = params.max_video_reuse if params and hasattr(params, 'max_video_reuse') and params.max_video_reuse is not None else None
        
        for i, selection in enumerate(selected_videos):
            # Don't break early when max_video_reuse=1 to utilize all selected videos
            if video_duration > target_duration and not (max_reuse_limit and max_reuse_limit == 1):
                break
                
            video_path = selection['video_path']
            target_duration = min(selection['duration'], max_clip_duration)
            
            logger.debug(f"processing semantic clip {i+1}: {os.path.basename(video_path)}, target duration: {target_duration:.2f}s")
            
            try:
                clip = VideoFileClip(video_path)
                clip_duration = min(clip.duration, target_duration)
                
                # Random start time for variety
                max_start = max(0, clip.duration - clip_duration)
                start_time = random.uniform(0, max_start) if max_start > 0 else 0
                
                clip = clip.subclipped(start_time, start_time + clip_duration)
                
                # Resize clip if needed
                clip_w, clip_h = clip.size
                if clip_w != video_width or clip_h != video_height:
                    clip_ratio = clip.w / clip.h
                    video_ratio = video_width / video_height
                    logger.debug(f"resizing clip, source: {clip_w}x{clip_h}, ratio: {clip_ratio:.2f}, target: {video_width}x{video_height}, ratio: {video_ratio:.2f}")
                    
                    clip = resize_clip_to_cover(clip, video_width, video_height)
                
                # Apply transitions if specified
                if video_transition_mode and video_transition_mode.value != VideoTransitionMode.none.value:
                    shuffle_side = random.choice(["left", "right", "top", "bottom"])
                    if video_transition_mode.value == VideoTransitionMode.fade_in.value:
                        clip = video_effects.fadein_transition(clip, 1)
                    elif video_transition_mode.value == VideoTransitionMode.fade_out.value:
                        clip = video_effects.fadeout_transition(clip, 1)
                    elif video_transition_mode.value == VideoTransitionMode.slide_in.value:
                        clip = video_effects.slidein_transition(clip, 1, shuffle_side)
                    elif video_transition_mode.value == VideoTransitionMode.slide_out.value:
                        clip = video_effects.slideout_transition(clip, 1, shuffle_side)
                    elif video_transition_mode.value == VideoTransitionMode.shuffle.value:
                        transition_funcs = [
                            lambda c: video_effects.fadein_transition(c, 1),
                            lambda c: video_effects.fadeout_transition(c, 1),
                            lambda c: video_effects.slidein_transition(c, 1, shuffle_side),
                            lambda c: video_effects.slideout_transition(c, 1, shuffle_side),
                        ]
                        shuffle_transition = random.choice(transition_funcs)
                        clip = shuffle_transition(clip)
                
                # Write clip to temp file
                clip_file = f"{output_dir}/temp-semantic-clip-{i+1}.mp4"
                clip.write_videofile(
                    clip_file, 
                    logger=None, 
                    fps=fps, 
                    codec=video_codec,
                    bitrate=video_bitrate,
                    audio_bitrate=audio_bitrate,
                    ffmpeg_params=quality_params
                )
                
                close_clip(clip)
                
                processed_clips.append(SubClippedVideoClip(file_path=clip_file, duration=clip_duration, width=clip_w, height=clip_h))
                video_duration += clip_duration
                
            except Exception as e:
                logger.error(f"failed to process semantic clip: {str(e)}")
        
    else:
        # Original random/sequential logic
        processed_clips = []
        subclipped_items = []
        video_duration = 0
        for video_path in video_paths:
            clip = VideoFileClip(video_path)
            clip_duration = clip.duration
            clip_w, clip_h = clip.size
            close_clip(clip)
            
            start_time = 0

            while start_time < clip_duration:
                end_time = min(start_time + max_clip_duration, clip_duration)            
                if clip_duration - start_time >= max_clip_duration:
                    subclipped_items.append(SubClippedVideoClip(file_path= video_path, start_time=start_time, end_time=end_time, width=clip_w, height=clip_h))
                start_time = end_time
                if video_concat_mode.value == VideoConcatMode.sequential.value:
                    # Collect enough consecutive subclips to cover the narration
                    # instead of stopping after the first one, which left long
                    # audio with only a few seconds of footage (black thereafter).
                    if len(subclipped_items) >= sequential_subclips_needed(target_duration, max_clip_duration):
                        break

        # random subclipped_items order
        if video_concat_mode.value == VideoConcatMode.random.value:
            random.shuffle(subclipped_items)
            
        logger.debug(f"total subclipped items: {len(subclipped_items)}")
        
        # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
        for i, subclipped_item in enumerate(subclipped_items):
            if video_duration > target_duration:
                break
            
            logger.debug(f"processing clip {i+1}: {subclipped_item.width}x{subclipped_item.height}, current duration: {video_duration:.2f}s, remaining: {audio_duration - video_duration:.2f}s")
            
            try:
                clip = VideoFileClip(subclipped_item.file_path).subclipped(subclipped_item.start_time, subclipped_item.end_time)
                clip_duration = clip.duration
                # Not all videos are same size, so we need to resize them
                clip_w, clip_h = clip.size
                if clip_w != video_width or clip_h != video_height:
                    clip_ratio = clip.w / clip.h
                    video_ratio = video_width / video_height
                    logger.debug(f"resizing clip, source: {clip_w}x{clip_h}, ratio: {clip_ratio:.2f}, target: {video_width}x{video_height}, ratio: {video_ratio:.2f}")
                    
                    clip = resize_clip_to_cover(clip, video_width, video_height)
                        
                shuffle_side = random.choice(["left", "right", "top", "bottom"])
                if video_transition_mode and video_transition_mode.value == VideoTransitionMode.none.value:
                    clip = clip
                elif video_transition_mode and video_transition_mode.value == VideoTransitionMode.fade_in.value:
                    clip = video_effects.fadein_transition(clip, 1)
                elif video_transition_mode and video_transition_mode.value == VideoTransitionMode.fade_out.value:
                    clip = video_effects.fadeout_transition(clip, 1)
                elif video_transition_mode and video_transition_mode.value == VideoTransitionMode.slide_in.value:
                    clip = video_effects.slidein_transition(clip, 1, shuffle_side)
                elif video_transition_mode and video_transition_mode.value == VideoTransitionMode.slide_out.value:
                    clip = video_effects.slideout_transition(clip, 1, shuffle_side)
                elif video_transition_mode and video_transition_mode.value == VideoTransitionMode.shuffle.value:
                    transition_funcs = [
                        lambda c: video_effects.fadein_transition(c, 1),
                        lambda c: video_effects.fadeout_transition(c, 1),
                        lambda c: video_effects.slidein_transition(c, 1, shuffle_side),
                        lambda c: video_effects.slideout_transition(c, 1, shuffle_side),
                    ]
                    shuffle_transition = random.choice(transition_funcs)
                    clip = shuffle_transition(clip)

                if clip.duration > max_clip_duration:
                    clip = clip.subclipped(0, max_clip_duration)
                    
                # wirte clip to temp file
                clip_file = f"{output_dir}/temp-clip-{i+1}.mp4"
                clip.write_videofile(
                    clip_file, 
                    logger=None, 
                    fps=fps, 
                    codec=video_codec,
                    bitrate=video_bitrate,
                    audio_bitrate=audio_bitrate,
                    ffmpeg_params=quality_params
                )
                
                close_clip(clip)
            
                processed_clips.append(SubClippedVideoClip(file_path=clip_file, duration=clip.duration, width=clip_w, height=clip_h))
                video_duration += clip.duration
                
            except Exception as e:
                logger.error(f"failed to process clip: {str(e)}")
    
    # loop processed clips until the video duration matches or exceeds the audio duration.
    if video_duration < target_duration:
        # Check if we should respect max_video_reuse setting (already defined for semantic mode)
        if 'max_reuse_limit' not in locals():
            max_reuse_limit = params.max_video_reuse if params and hasattr(params, 'max_video_reuse') and params.max_video_reuse is not None else None
        
        if max_reuse_limit and max_reuse_limit == 1:
            # User has set max reuse to 1, don't loop clips
            logger.warning(f"video duration ({video_duration:.2f}s) is shorter than audio duration ({audio_duration:.2f}s), but max_video_reuse is set to 1 - NOT looping clips.")
            logger.info(f"final video duration: {video_duration:.2f}s, audio duration: {audio_duration:.2f}s")
        else:
            # Original looping behavior for other cases
            logger.warning(f"video duration ({video_duration:.2f}s) is shorter than audio duration ({audio_duration:.2f}s), looping clips to match audio length.")
            
            if max_reuse_limit:
                # Track how many times each clip has been used for reuse limit
                clip_usage = {}
                base_clips = processed_clips.copy()
                original_clip_count = len(base_clips)
                
                # Initialize usage counter
                for i, clip in enumerate(base_clips):
                    clip_usage[i] = 1  # Already used once
                
                clip_cycle = itertools.cycle(enumerate(base_clips))
                clips_added = 0
                
                for clip_idx, clip in clip_cycle:
                    if video_duration >= target_duration:
                        break
                    
                    # Check if this clip has reached the reuse limit
                    if clip_usage[clip_idx] >= max_reuse_limit:
                        # Skip clips that have reached the reuse limit
                        continue
                    
                    processed_clips.append(clip)
                    video_duration += clip.duration
                    clip_usage[clip_idx] += 1
                    clips_added += 1
                    
                    # Safety check: if all clips have reached the limit, break
                    if all(usage >= max_reuse_limit for usage in clip_usage.values()):
                        logger.warning(f"all clips have reached max reuse limit ({max_reuse_limit}), stopping at {video_duration:.2f}s")
                        break
                
                logger.info(f"video duration: {video_duration:.2f}s, audio duration: {audio_duration:.2f}s, looped {clips_added} clips (respecting max_reuse_limit: {max_reuse_limit})")
            else:
                # Original unlimited looping behavior
                base_clips = processed_clips.copy()
                for clip in itertools.cycle(base_clips):
                    if video_duration >= target_duration:
                        break
                    processed_clips.append(clip)
                    video_duration += clip.duration
                logger.info(f"video duration: {video_duration:.2f}s, audio duration: {audio_duration:.2f}s, looped {len(processed_clips)-len(base_clips)} clips")
     
    # merge video clips using direct concatenation to avoid quality degradation
    logger.info("starting clip merging process")
    if not processed_clips:
        logger.warning("no clips available for merging")
        return combined_video_path
    
    # if there is only one clip, use it directly
    if len(processed_clips) == 1:
        logger.info("using single clip directly")
        shutil.copy(processed_clips[0].file_path, combined_video_path)
        delete_files([processed_clips[0].file_path])
        logger.info("video combining completed")
        return combined_video_path
    
    # Load all clips at once and concatenate in single operation to preserve quality
    logger.info(f"loading {len(processed_clips)} clips for direct concatenation")
    clips_to_merge = []
    
    try:
        for i, clip_info in enumerate(processed_clips):
            logger.info(f"loading clip {i+1}/{len(processed_clips)}: {os.path.basename(clip_info.file_path)}")
            clip = VideoFileClip(clip_info.file_path)
            clips_to_merge.append(clip)
        
        # Concatenate all clips in single operation - NO QUALITY LOSS!
        logger.info("concatenating all clips in single operation")
        final_clip = concatenate_videoclips(clips_to_merge)
        
        # Write final result with high quality settings
        logger.info("writing final concatenated video with high quality")
        final_clip.write_videofile(
            combined_video_path,
            threads=threads,
            logger=None,
            temp_audiofile_path=output_dir,
            audio_codec=audio_codec,
            fps=fps,
            codec=video_codec,
            bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            ffmpeg_params=quality_params
        )
        
        # Clean up clips
        for clip in clips_to_merge:
            close_clip(clip)
        close_clip(final_clip)
        
    except Exception as e:
        logger.error(f"failed to concatenate clips: {str(e)}")
        # Fallback to progressive merging if direct concatenation fails
        logger.warning("falling back to progressive merging")
        return _progressive_merge_fallback(processed_clips, combined_video_path, output_dir, threads)
    
    # clean temp files
    clip_files = [clip.file_path for clip in processed_clips]
    delete_files(clip_files)
            
    logger.info("video combining completed")
    return combined_video_path


def _progressive_merge_fallback(processed_clips, combined_video_path, output_dir, threads):
    """Fallback progressive merging method if direct concatenation fails"""
    logger.info("using progressive merge fallback")
    
    # create initial video file as base
    base_clip_path = processed_clips[0].file_path
    temp_merged_video = f"{output_dir}/temp-merged-video.mp4"
    temp_merged_next = f"{output_dir}/temp-merged-next.mp4"
    
    # copy first clip as initial merged video
    shutil.copy(base_clip_path, temp_merged_video)
    
    # merge remaining video clips one by one
    for i, clip in enumerate(processed_clips[1:], 1):
        logger.info(f"merging clip {i}/{len(processed_clips)-1}, duration: {clip.duration:.2f}s")
        
        try:
            # load current base video and next clip to merge
            base_clip = VideoFileClip(temp_merged_video)
            next_clip = VideoFileClip(clip.file_path)
            
            # merge these two clips
            merged_clip = concatenate_videoclips([base_clip, next_clip])

            # save merged result to temp file
            merged_clip.write_videofile(
                filename=temp_merged_next,
                threads=threads,
                logger=None,
                temp_audiofile_path=output_dir,
                audio_codec=audio_codec,
                fps=fps,
                codec=video_codec,
                bitrate=video_bitrate,
                audio_bitrate=audio_bitrate,
                ffmpeg_params=quality_params
            )
            close_clip(base_clip)
            close_clip(next_clip)
            close_clip(merged_clip)
            
            # replace base file with new merged file
            delete_files(temp_merged_video)
            os.rename(temp_merged_next, temp_merged_video)
            
        except Exception as e:
            logger.error(f"failed to merge clip: {str(e)}")
            continue
    
    # after merging, rename final result to target file name
    os.rename(temp_merged_video, combined_video_path)
    
    # clean temp files
    clip_files = [clip.file_path for clip in processed_clips]
    delete_files(clip_files)
    
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # Create ImageFont
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    processed = True
    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    
    # Improved word wrapping with better line balancing
    for word in words:
        _before = _txt_
        test_txt = _txt_ + f"{word} " if _txt_ else f"{word} "
        _width, _height = get_text_size(test_txt)
        
        if _width <= max_width:
            _txt_ = test_txt
        else:
            if _txt_.strip() == word.strip():
                # Single word is too long, force break
                processed = False
                break
            
            # Add current line and start new line
            _wrapped_lines_.append(_before.strip())
            _txt_ = f"{word} "
    
    # Add remaining text
    if _txt_.strip():
        _wrapped_lines_.append(_txt_.strip())
    
    if processed:
        # Balance line lengths for better visual appearance
        _wrapped_lines_ = _balance_line_lengths(_wrapped_lines_, font, max_width)
        result = "\n".join(_wrapped_lines_)
        height = len(_wrapped_lines_) * height
        return result, height

    # Fallback: character-by-character wrapping
    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for char in chars:
        test_txt = _txt_ + char
        _width, _height = get_text_size(test_txt)
        if _width <= max_width:
            _txt_ = test_txt
        else:
            if _txt_:
                _wrapped_lines_.append(_txt_)
            _txt_ = char
    
    if _txt_:
        _wrapped_lines_.append(_txt_)
    
    result = "\n".join(_wrapped_lines_)
    height = len(_wrapped_lines_) * height
    return result, height


def _balance_line_lengths(lines, font, max_width):
    """
    Balance line lengths for better visual appearance when center-aligned
    """
    if len(lines) <= 1:
        return lines
    
    def get_text_width(text):
        left, top, right, bottom = font.getbbox(text.strip())
        return right - left
    
    balanced_lines = []
    
    for i, line in enumerate(lines):
        if i < len(lines) - 1:  # Not the last line
            current_line_width = get_text_width(line)
            next_line = lines[i + 1]
            
            # Try to balance by moving words between lines
            words_current = line.split()
            words_next = next_line.split()
            
            # If current line is much shorter than max width and next line has words
            if current_line_width < max_width * 0.7 and len(words_next) > 1:
                # Try moving first word from next line to current line
                test_line = line + " " + words_next[0]
                test_width = get_text_width(test_line)
                
                if test_width <= max_width:
                    # Move the word
                    balanced_lines.append(test_line)
                    lines[i + 1] = " ".join(words_next[1:])  # Update next line
                    continue
        
        balanced_lines.append(line)
    
    return balanced_lines


def create_enhanced_subtitle_clips(enhanced_subtitle_path, params, video_width, video_height, font_path):
    """
    Create text clips with true word-by-word highlighting
    Creates subtitle images where only the currently spoken word is highlighted
    """
    text_clips = []
    
    # Load enhanced subtitle data
    with open(enhanced_subtitle_path, 'r', encoding='utf-8') as f:
        enhanced_data = json.load(f)
    
    def hex_to_rgb(hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def position_clip(clip, params, video_height):
        """Apply positioning to a clip based on subtitle position settings"""
        if params.subtitle_position == "bottom":
            return clip.with_position(("center", video_height * 0.85))
        elif params.subtitle_position == "top":
            return clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            custom_y = (video_height * params.custom_position / 100)
            return clip.with_position(("center", custom_y))
        else:  # center
            return clip.with_position(("center", "center"))
    
    def create_word_highlighted_image(text, highlighted_word_indices, font_size, normal_color, highlight_color, stroke_color, stroke_width):
        """Create an image with specific words highlighted"""
        try:
            font = ImageFont.truetype(font_path, font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()
        
        # Clean text: remove commas but keep line breaks they indicate
        # Replace comma + space with just space, and standalone commas with nothing
        cleaned_text = text.replace(', ', ' ').replace(',', ' ')
        
        # Wrap text using the same logic
        max_width = int(video_width * 0.9)
        wrapped_txt, _ = wrap_text(
            cleaned_text, max_width=max_width, font=font_path, fontsize=font_size
        )
        
        # Split into lines and words
        lines = wrapped_txt.split('\n')
        
        # Calculate image dimensions
        line_height = int(font_size * 1.3)
        img_height = len(lines) * line_height + 40  # Add padding
        img_width = max_width + 40  # Add padding
        
        # Create transparent image
        img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Colors
        normal_rgb = hex_to_rgb(normal_color)
        highlight_rgb = hex_to_rgb(highlight_color)
        stroke_rgb = hex_to_rgb(stroke_color) if stroke_color else None
        
        word_index = 0
        y_pos = 20
        
        for line in lines:
            words = line.split()
            
            # Calculate total line width for center alignment
            line_width = 0
            for word in words:
                word_bbox = font.getbbox(word + ' ')
                line_width += word_bbox[2] - word_bbox[0]
            
            # Center the line
            x_pos = (img_width - line_width) // 2
            x_pos = max(20, x_pos)  # Ensure minimum padding
            
            for word in words:
                # Determine color for this word
                word_color = highlight_rgb if word_index in highlighted_word_indices else normal_rgb
                
                # Draw word with stroke if specified
                if stroke_rgb and stroke_width > 0:
                    # Draw stroke by drawing text multiple times with offset
                    stroke_w = int(stroke_width)
                    for dx in range(-stroke_w, stroke_w + 1):
                        for dy in range(-stroke_w, stroke_w + 1):
                            if dx != 0 or dy != 0:
                                draw.text((x_pos + dx, y_pos + dy), word, font=font, fill=stroke_rgb)
                
                # Draw main text
                draw.text((x_pos, y_pos), word, font=font, fill=word_color)
                
                # Calculate next position
                word_bbox = font.getbbox(word + ' ')
                x_pos += word_bbox[2] - word_bbox[0]
                word_index += 1
            
            y_pos += line_height
        
        return img
    
    def create_subtitle_clip(text, highlighted_word_indices, start_time, duration, params):
        """Create a subtitle clip with specified highlighting"""
        try:
            img = create_word_highlighted_image(
                text=text,
                highlighted_word_indices=highlighted_word_indices,
                font_size=int(params.font_size),
                normal_color=params.text_fore_color,
                highlight_color=params.word_highlight_color,
                stroke_color=params.stroke_color,
                stroke_width=int(params.stroke_width)
            )
            
            clip = ImageClip(np.array(img)).with_duration(duration).with_start(start_time)
            return position_clip(clip, params, video_height)
            
        except Exception as e:
            logger.error(f"Failed to create subtitle clip: {str(e)}")
            return None
    
    for subtitle_data in enhanced_data:
        start_time = subtitle_data['start_time']
        end_time = subtitle_data['end_time']
        text = subtitle_data['text']
        words = subtitle_data['words']
        
        # Sort words by start time
        sorted_words = sorted(words, key=lambda w: w['start'])
        
        # Create word mapping to indices
        text_words = []
        for line in text.split('\n'):
            text_words.extend(line.split())
        
        # Map spoken words to text indices in sequence so repeated words
        # highlight the correct occurrence instead of always the first one.
        aligned_indices = align_spoken_words(
            text_words, [w['word'] for w in sorted_words]
        )

        # Create time segments with word highlighting
        current_time = start_time

        for word_pos, word_data in enumerate(sorted_words):
            word_start = max(word_data['start'], start_time)
            word_end = min(word_data['end'], end_time)

            if word_start >= word_end:
                continue

            word_index = aligned_indices[word_pos]

            # Create segment before word (normal colors)
            if word_start > current_time:
                clip = create_subtitle_clip(text, set(), current_time, word_start - current_time, params)
                if clip:
                    text_clips.append(clip)
            
            # Create highlighted segment during word
            if word_index >= 0:
                clip = create_subtitle_clip(text, {word_index}, word_start, word_end - word_start, params)
                if clip:
                    text_clips.append(clip)
            
            current_time = word_end
        
        # Create final normal segment if needed
        if current_time < end_time:
            clip = create_subtitle_clip(text, set(), current_time, end_time - current_time, params)
            if clip:
                text_clips.append(clip)
    
    return text_clips


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"generating video: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/harry0703/MoneyPrinterTurbo/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"  ⑤ font: {font_path}")

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        
        # Clean text: remove commas but keep spaces for readability
        cleaned_phrase = phrase.replace(', ', ' ').replace(',', ' ')
        
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            cleaned_phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        interline = int(params.font_size * 0.25)
        size=(int(max_width), int(txt_height + params.font_size * 0.25 + (interline * (wrapped_txt.count("\n") + 1))))

        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            method='caption',  # Use caption method for better text wrapping
            size=size,
            # align='center',  # Removed - not supported in MoviePy 2.2.1
            # interline=interline,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # Ensure the subtitle is fully within the screen bounds
            margin = 10  # Additional margin, in pixels
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )  # Constrain the y value within the valid range
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    overlay_clips = []
    if getattr(params, "comment_card_enabled", False):
        try:
            card_clip = create_comment_card_clip(params, video_width, video_height, font_path)
            if card_clip is not None:
                overlay_clips.append(card_clip)
                logger.info("added Reddit-style comment card overlay")
        except Exception as e:
            logger.error(f"failed to build comment card overlay: {e}")

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if subtitle_path and os.path.exists(subtitle_path):
        # Check if word highlighting is enabled and enhanced subtitles are available
        enhanced_subtitle_path = getattr(params, '_enhanced_subtitle_path', None)
        use_word_highlighting = (
            getattr(params, 'enable_word_highlighting', False) and
            enhanced_subtitle_path and
            os.path.exists(enhanced_subtitle_path)
        )
        
        if use_word_highlighting:
            logger.info("Using enhanced subtitles with word highlighting")
            text_clips = create_enhanced_subtitle_clips(
                enhanced_subtitle_path, params, video_width, video_height, font_path
            )
        else:
            # Traditional subtitle rendering
            sub = SubtitlesClip(
                subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
            )
            text_clips = []
            for item in sub.subtitles:
                clip = create_text_clip(subtitle_item=item)
                text_clips.append(clip)

        if overlay_clips and getattr(params, "comment_card_enabled", False):
            # While the comment card is shown, hide captions so the intro matches
            # the reference (card alone first), then captions take over.
            card_secs = float(getattr(params, "comment_card_duration", 4.0) or 4.0)
            text_clips = [
                c for c in text_clips
                if getattr(c, "start", None) is None or c.start >= card_secs - 0.05
            ]

        video_clip = CompositeVideoClip([video_clip, *overlay_clips, *text_clips])
    elif overlay_clips:
        # No subtitles, but we still need to overlay the comment card.
        video_clip = CompositeVideoClip([video_clip, *overlay_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    video_clip.write_videofile(
        output_file,
        audio_codec=audio_codec,
        temp_audiofile_path=output_dir,
        threads=params.n_threads or 2,
        logger=None,
        fps=fps,
        codec=video_codec,
        bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        ffmpeg_params=quality_params
    )
    video_clip.close()
    del video_clip


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"low resolution material: {width}x{height}, minimum 480x480 required")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # Create an image clip and set its duration to 3 seconds
            clip = (
                ImageClip(material.url)
                .with_duration(clip_duration)
                .with_position("center")
            )
            # Apply a zoom effect using the resize method.
            # A lambda function is used to make the zoom effect dynamic over time.
            # The zoom effect starts from the original size and gradually scales up to 120%.
            # t represents the current time, and clip.duration is the total duration of the clip (3 seconds).
            # Note: 1 represents 100% size, so 1.2 represents 120% size.
            zoom_clip = clip.resized(
                lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
            )

            # Optionally, create a composite video clip containing the zoomed clip.
            # This is useful when you want to add other elements to the video.
            final_clip = CompositeVideoClip([zoom_clip])

            # Output the video to a file.
            video_file = f"{material.url}.mp4"
            final_clip.write_videofile(
                video_file, 
                fps=30, 
                logger=None,
                codec=video_codec,
                bitrate=video_bitrate,
                audio_bitrate=audio_bitrate,
                ffmpeg_params=quality_params
            )
            close_clip(clip)
            material.url = video_file
            logger.success(f"image processed: {video_file}")
    return materials
