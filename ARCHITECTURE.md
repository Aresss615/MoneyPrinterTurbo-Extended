# ARCHITECTURE - MoneyPrinterTurbo-Extended

High-level system shape. Detail lives in CLAUDE.md, README.md, and the fork's
`LOCAL_PIPELINE_PLAN.md`. Seeded from README + ~/knowledge on 2026-06-22; source
not deep-inspected, so internals are Needs verification.

## Overview
Faceless short-form video generation pipeline (fork of MoneyPrinterTurbo). Produces
Reddit-story / AITA TikToks: gameplay background + comment card + karaoke captions,
fully automated from script to publish.

## Pipeline stages (from README + ~/knowledge; verify in code)
1. Script generation - AI (Ollama local model).
2. TTS voiceover - Chatterbox (local, voice cloning) or Edge-TTS.
3. Word-level timing / subtitles - WhisperX, word-by-word highlight sync.
4. Video selection - semantic matching of script to clips; gameplay backgrounds
   from `gameplay/`.
5. Assembly - ffmpeg compositing (background + comment card + captions).
6. Publish - TikTok Content Posting API (per ~/knowledge) - Needs verification.

## Components (by directory; roles inferred, verify)
- `app/` - application/API code. `main.py` - entry point. `api.sh` / `webui.sh` - launchers.
- `webui/` - web interface. `config.toml` - runtime config.
- `gameplay/` - background video assets. `reference_audio/` - TTS voice refs.
- `storage/` - generated output. `resource/`, `prompts.txt` - prompt/resource assets.
- `scripts/`, `notebooks/`, `test/` - tooling, experiments, tests.

## External dependencies
- Python + UV venvs; `requirements.txt`, CUDA variant + `environment.yml`.
- Ollama, WhisperX, Chatterbox TTS / Edge-TTS, ffmpeg.
- Docker (`Dockerfile`, `docker-compose.yml`).
- Cloudflare tunnel for public hosting at app.johnchrisley.dev - Needs verification (still live?).

## Key flows / external surfaces
- Web UI + API server for triggering generation.
- TikTok publishing integration - Needs verification.

## Change notes (newest at top)
<!-- AUTO:ARCH -->

- 2026-06-22 - Architecture seeded from README + ~/knowledge; internals pending verification.
