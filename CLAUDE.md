# CLAUDE.md

Guidance for Claude Code in this repo. Global operating rules + context about the
owner (Jc) live in ~/knowledge (read ~/knowledge/INDEX.md first). This file is the
project-specific layer and wins on project facts.

## Project Overview
Enhanced fork of MoneyPrinterTurbo (harry0703): a faceless short-form video pipeline.
Jc's use: local AITA / Reddit-story TikTok videos (Minecraft gameplay background +
Reddit comment card + karaoke word-by-word captions), end to end - AI script -> TTS
voiceover -> auto subtitles -> assembly -> publish. Monetization-focused. Active.

Hosting: app.johnchrisley.dev via a Cloudflare tunnel (stood up for TikTok app
review) - per ~/knowledge, verify still live.

## What this fork adds (from README)
- Word-by-word subtitle highlighting synced to TTS word boundaries (WhisperX).
- Semantic video-text matching (script -> relevant clips, not random).
- Chatterbox TTS - free local TTS with voice cloning; Edge-TTS also supported.

## Stack
- Python (Jc uses UV venvs per ~/knowledge). See `requirements.txt` /
  `requirements-cuda.txt` / `environment.yml`. CUDA setup scripts present.
- Local AI: Ollama (qwen3:8b per ~/knowledge - verify), WhisperX, Chatterbox/Edge-TTS, ffmpeg.
- Web UI (`webui/`, `webui.sh`) + an API/server (`app/`, `main.py`, `api.sh`).
- Docker support (`Dockerfile`, `docker-compose.yml`).

## Run (verify against the actual scripts before relying)
- `./webui.sh` - launch the web UI. `./api.sh` - launch the API. `main.py` - entry.
- Config in `config.toml` (copy from `config.example.toml`).
- Gameplay backgrounds in `gameplay/`; reference voices in `reference_audio/`.

## Security: creator access-key gate (before public hosting)
The TikTok OAuth token is stored server-wide, NOT per device - any device that opens
the hosted creator console could otherwise see/use the same connected TikTok account.
Before exposing the console publicly, set an owner access key so creator/TikTok
functions are gated (Codex change, 2026-06-23):
- Configure via `[app] creator_access_key = "your-long-private-key"` in `config.toml`,
  or the `CREATOR_ACCESS_KEY` env var (env wins). Empty = gate disabled (local only).
- Requests must send the key in the `X-Creator-Access-Key` header; the console shows a
  TikTok locked/unlock state and the owner enters the key once per browser.
- Protected endpoints: TikTok OAuth/status, publish, inbox upload, and TikTok
  schedule-related endpoints (see `app/controllers/base.py`).

## Conventions (Jc's global rules - see ~/knowledge/preference.md)
- Prefer local/free models (Ollama) over paid APIs; cut costs.
- Never use Binance as a price feed (not relevant here, but a standing rule).
- Commits: one short imperative line, no AI attribution, commit often.
- TDD where practical; verify by running before claiming done.

## Project docs
- ROADMAP.md / DECISIONS.md / ARCHITECTURE.md - maintained via
  ~/knowledge/scripts/projectdocs.sh (post-commit hook installed). Tag commits
  `decide:` / `milestone:`/`ship:` / `arch:` to auto-route.
- Fork-internal planning: `plan.md`, `LOCAL_PIPELINE_PLAN.md`, `SETUP_NOTES.md`.

## Status
Active per ~/knowledge. Exact current pipeline state, hosting liveness, and which
TTS/model is in use are Needs verification (source not deep-inspected 2026-06-22).
