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
2. Publish the repo's simple legal pages with GitHub Pages and use these HTTPS
   URLs in the TikTok form:
   - Website URL / Web/Desktop URL: `https://johnchrisley.dev/legal`
   - Terms of Service URL: `https://johnchrisley.dev/legal/terms`
   - Privacy Policy URL: `https://johnchrisley.dev/legal/privacy`

   > ⚠️ Never put `https://app.johnchrisley.dev` in any of the three website
   > fields above. That host is the creator console + OAuth callback and is only
   > online when the bot is running — submitting it as the Website URL caused the
   > "Invalid Website URL" rejection (reviewer crawled it while the Mac was
   > offline). `app.` belongs only in the Login Kit redirect URI below.
3. Add the **Content Posting API** product and request only these scopes:
   `video.publish` + `video.upload`.
4. Start the creator app locally:
   ```bash
   ./creator.sh
   ```
5. Expose the local app with an HTTPS tunnel. Cloudflare Tunnel example:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8080
   ```
   Copy the generated `https://...trycloudflare.com` URL.
6. In TikTok Login Kit settings, set a redirect URI that exactly matches the
   public app callback, currently:
   `https://app.johnchrisley.dev/api/v1/callback`.
7. Copy the app's **client key** and **client secret** into `config.toml`:

   ```toml
   [tiktok]
   client_key = "..."
   client_secret = "..."
   redirect_uri = "https://app.johnchrisley.dev/api/v1/callback"
   privacy_level = "SELF_ONLY"   # PUBLIC_TO_EVERYONE after TikTok audits your app
   disable_comment = false
   disable_duet = false
   disable_stitch = false
   brand_content_toggle = false
   brand_organic_toggle = false
   is_aigc = false
   ```

8. Restart the creator app, then click the console's "TikTok: connect" pill and
   authorize once. The OAuth token is cached in `storage/tiktok_token.json` and
   refreshed automatically.
9. Generate a video, choose TikTok privacy (`SELF_ONLY` for private testing),
   confirm TikTok music usage, then click "Publish to TikTok".

Notes:

- TikTok Web Login Kit redirect URIs must be absolute HTTPS URLs. Plain
  `http://127.0.0.1:8080/...` works for the local server, but cannot be
  registered as a Web redirect URI in TikTok's app settings.
- **Unaudited apps can only post privately** (`SELF_ONLY`). After TikTok audits
  your app, the UI will use the privacy options returned by TikTok's
  `creator_info` endpoint.
- Generated 60s vertical videos in this repo are often larger than 64 MB, so
  the integration uploads them sequentially in TikTok-compliant chunks.
- The caption/hashtags default to the story's `suggested_description` +
  `suggested_hashtags` (persisted to `storage/tasks/<id>/story.json`) but can
  be overridden in the publish request.
- A cover thumbnail is taken from `cover_timestamp_ms` (default 1000 ms).
- For final public posting review, record a demo that shows login, privacy
  selection, interaction settings, music usage consent, and the manual publish
  click.
