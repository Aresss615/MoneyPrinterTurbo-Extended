# Local Faceless Video Setup Notes

## Packages Installed

- Homebrew tools: `uv`, `ffmpeg`, `imagemagick`
- Python runtime: UV-managed Python 3.11.15 in `.venv`
- Project dependencies: installed from `requirements.txt`
- Local TTS/subtitle dependencies: `chatterbox-tts`, `whisperx`, `torchaudio`, `toml`

## Config Changed

- `config.toml` uses local Ollama:
  - `llm_provider = "ollama"`
  - `ollama_base_url = "http://localhost:11434/v1"`
  - `ollama_model_name = "qwen3:8b"`
- Local video input:
  - `video_source = "local"`
  - `gameplay/minecraft-parkour-1.mp4`
  - `gameplay/` is excluded in `.git/info/exclude`
- Local subtitles and rendering:
  - `subtitle_provider = "edge"`
  - `ffmpeg_path = "/opt/homebrew/bin/ffmpeg"`
  - `imagemagick_path = "/opt/homebrew/bin/magick"`
- Whisper defaults:
  - `model_size = "base"`
  - `device = "cpu"`
  - `compute_type = "int8"`
- UI defaults:
  - `voice_name = "chatterbox:default:Default Voice-Neutral"`
  - `enable_word_highlighting = true`
  - `highlight_color = "#ff0000"`

## Verified Output

- Test task: `fullscreen-check`
- Final MP4: `storage/tasks/fullscreen-check/final-1.mp4`
- Verified with `ffprobe`:
  - Video: `1080x1920`, H.264
  - Audio: AAC
- Verified full-frame (no black bars) via extracted `final-frame.jpg`:
  gameplay fills the entire 9:16 frame using cover-fill center crop, and
  word highlighting renders correctly.
- Subtitle files created:
  - `subtitle.srt`
  - `subtitle_enhanced.json`

> Note: the earlier task `efc1a990-64b6-4df2-aa44-0e3d5e1f520c` was rendered
> before the cover-fill crop fix and still shows black letterbox bars. Use
> `fullscreen-check` as the reference output.

## Future Videos

```bash
CHATTERBOX_DEVICE=cpu CHATTERBOX_CFG_WEIGHT=0.2 uv run python scripts/run_local_faceless_video.py --story "YOUR STORY TEXT HERE"
```
