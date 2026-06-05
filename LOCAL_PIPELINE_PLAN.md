# MoneyPrinterTurbo Local Faceless Video Setup Plan

## Summary

Set up a local-only faceless-video pipeline from `Asad-Ismail/MoneyPrinterTurbo-Extended` in `/Users/jc/dev/projects/MoneyPrinterTurbo-Extended`, using the GitHub fork, UV-managed Python 3.11, local Chatterbox TTS, local Ollama `qwen3:8b`, word-by-word caption highlighting, and the copied gameplay file `gameplay/minecraft-parkour-1.mp4`.

Reference repo: https://github.com/Asad-Ismail/MoneyPrinterTurbo-Extended

Chatterbox install reference: https://github.com/resemble-ai/chatterbox

## Key Changes

- Fork/clone with GitHub CLI:
  - Run `gh auth status`; if unauthenticated, stop for user auth.
  - Run from `/Users/jc/dev/projects`: `gh repo fork Asad-Ismail/MoneyPrinterTurbo-Extended --clone --remote`.
  - If `MoneyPrinterTurbo-Extended` already exists, stop and ask before overwriting.
- Install/check system deps:
  - `brew install uv ffmpeg imagemagick` only for missing packages.
  - Verify `ffmpeg -version`, `magick -version`, `uv --version`.
  - Use `uv python install 3.11`, then `uv venv --python 3.11 .venv`.
  - Install dependencies with UV only: `uv pip install -r requirements.txt` plus `uv pip install chatterbox-tts whisperx torchaudio toml`.
- Copy gameplay into repo:
  - Create `gameplay/`.
  - Copy `/Users/jc/dev/projects/minecraft-parkour-1.mp4` to `gameplay/minecraft-parkour-1.mp4`.
  - Add `gameplay/` to `.git/info/exclude` so the 3.3GB file is not committed.
- Add local glue/config:
  - Create `LOCAL_PIPELINE_PLAN.md` in the repo with this plan.
  - Create/update `config.toml` from `config.example.toml`.
  - Set `[app] llm_provider = "ollama"`, `ollama_base_url = "http://localhost:11434/v1"`, `ollama_model_name = "qwen3:8b"`, `video_source = "local"`, `subtitle_provider = "edge"`, `enable_redis = false`, `ffmpeg_path = "/opt/homebrew/bin/ffmpeg"`, `imagemagick_path = "/opt/homebrew/bin/magick"`.
  - Set `[whisper] model_size = "base"`, `device = "cpu"`, `compute_type = "int8"`.
  - Set UI defaults for Chatterbox voice and word highlighting where present.
- Add one runner script, e.g. `scripts/run_local_faceless_video.py`, that imports the existing project services and calls the existing pipeline directly with:
  - `video_script`: the supplied AITA story text.
  - `voice_name = "chatterbox:default:Default Voice-Neutral"`.
  - `video_source = "local"`.
  - `video_materials = [{ provider = "local", url = "<repo>/gameplay/minecraft-parkour-1.mp4" }]`.
  - `video_aspect = "9:16"`, `video_concat_mode = "sequential"`, `bgm_type = ""`, `subtitle_enabled = true`, `enable_word_highlighting = true`.

## Verification Steps

- Check Ollama:
  - Run `ollama list`.
  - If server is down, start local server with `ollama serve`, then re-run `ollama list`.
  - If `qwen3:8b` is missing, stop and ask.
- Run a short local TTS smoke test:
  - Generate a 1-2 sentence Chatterbox audio file through the project's existing `voice.tts`.
  - Confirm the audio file exists and `ffprobe` reports a valid duration.
- Run the full test video command:
  - `CHATTERBOX_DEVICE=cpu CHATTERBOX_CFG_WEIGHT=0.2 uv run python scripts/run_local_faceless_video.py --story "AITA for telling my roommate to stop eating my food? I labeled everything in the fridge but he kept finishing my leftovers and acting confused when I asked."`
- Verify output:
  - Locate final MP4 under the project task/output folder.
  - Run `ffprobe` and confirm width/height is `1080x1920`.
  - Confirm audio stream exists.
  - Confirm generated task folder contains `subtitle.srt` and `subtitle_enhanced.json`.

## Final Notes File

After the successful MP4 is produced, create `SETUP_NOTES.md` in the repo with:

- Packages installed: `uv`, `ffmpeg`, `imagemagick`, Python 3.11 environment, project requirements, Chatterbox/WhisperX dependencies.
- Config changed: local Ollama, local Chatterbox voice, word highlighting, 9:16, local gameplay material.
- One command for future videos:
  - `CHATTERBOX_DEVICE=cpu CHATTERBOX_CFG_WEIGHT=0.2 uv run python scripts/run_local_faceless_video.py --story "YOUR STORY TEXT HERE"`

## Assumptions

- Work happens in `/Users/jc/dev/projects/MoneyPrinterTurbo-Extended`.
- GitHub fork creation uses the installed `gh` CLI.
- The gameplay file is copied into the repo but excluded from git.
- Chatterbox and Whisper models may download open model weights on first run, but no cloud TTS/LLM/API inference is used.
- CPU mode is the default for Chatterbox/WhisperX because this fork does not expose an Apple MLX/MPS path cleanly.
