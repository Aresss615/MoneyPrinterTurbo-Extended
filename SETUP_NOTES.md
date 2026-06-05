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
  - `gameplay/minecraft-parkour-1-vertical.mp4`
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
  - Gameplay source: `1080x1920`, `60 fps`
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

## Multiple backgrounds & rotating voices

The pipeline now auto-discovers **every** video file in `gameplay/` (`.mp4`,
`.mov`, `.mkv`, `.avi`, `.flv`, `.webm`, `.m4v`) and picks one at random per
render. Both 16:9 and 9:16 sources work — landscape clips are center-cropped to
9:16 automatically. Just drop new files into `gameplay/`; no code change needed.

Each video also gets a random **Edge-TTS** voice from the pool in
`app/services/creator_console.py` (`VOICE_POOL`). Word-level caption
highlighting is preserved automatically (the audio is re-transcribed
independently of the TTS engine). Chatterbox remains available as a fallback
(`DEFAULT_VOICE_NAME`); edit `VOICE_POOL` to taste.

## TikTok publishing (Direct Post)

Manually publish a finished video to TikTok from the creator console
("Publish to TikTok" button) or via `POST /api/v1/tiktok/publish`.

One-time setup:

1. Register an app at https://developers.tiktok.com.
2. Add the **Content Posting API** product and request the
   `video.publish` + `video.upload` scopes.
3. Set a redirect URI that matches `config.toml [tiktok] redirect_uri`
   (default `http://127.0.0.1:8080/api/v1/tiktok/callback`).
4. Copy the app's **client key** and **client secret** into `config.toml`:

   ```toml
   [tiktok]
   client_key = "..."
   client_secret = "..."
   redirect_uri = "http://127.0.0.1:8080/api/v1/tiktok/callback"
   privacy_level = "SELF_ONLY"   # PUBLIC_TO_EVERYONE after TikTok audits your app
   ```

5. Start the server (`creator.sh`), then open `/api/v1/tiktok/auth-url`
   (the console's "TikTok: connect" pill links here) and authorize once.
   The OAuth token is cached in `storage/tiktok_token.json` and refreshed
   automatically.

Notes:

- **Unaudited apps can only post privately** (`SELF_ONLY`). After TikTok
  audits your app, change `privacy_level` to `PUBLIC_TO_EVERYONE` — no code
  change required.
- The caption/hashtags default to the story's `suggested_description` +
  `suggested_hashtags` (persisted to `storage/tasks/<id>/story.json`) but can
  be overridden in the publish request.
- A cover thumbnail is taken from `cover_timestamp_ms` (default 1000 ms).
