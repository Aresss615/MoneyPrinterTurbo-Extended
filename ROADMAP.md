# ROADMAP - MoneyPrinterTurbo-Extended

Maintained per ~/knowledge/MAINTENANCE.md. Move items the moment their real state
changes. "Done" requires verification (test passes / runs / renders), not a claim.
Seeded from README + ~/knowledge on 2026-06-22. Most items Needs verification until
the running pipeline is confirmed.

## Now (in progress)
- Creator console / library / queue work - uncommitted changes in the working tree
  as of 2026-06-22 (app/services/creator_console.py, creator_queue.py, etc.)
- Confirm whether app.johnchrisley.dev is still live (was served for TikTok review) -
  Needs verification

## Done (2026-06-23)
- Creator access-key gate (Codex): owner key protects TikTok OAuth/status, publish,
  inbox upload, and TikTok schedule endpoints before public hosting. Config via
  `[app] creator_access_key` or `CREATOR_ACCESS_KEY`; console shows a locked/unlock
  state, key entered once per browser. Targeted tests: 59 passed. Full `test/` still
  has 4 unrelated failures (ffmpeg media-dimension issue; missing Azure/SiliconFlow
  voice credentials). Uncommitted in the working tree.

## Next
- Facebook publishing path - `app/controllers/v1/facebook.py` is new/untracked; finish it

## Backlog
- Tune semantic video matching / caption styling
- Cost control: keep generation fully local (Ollama / Chatterbox), avoid paid TTS

## Blocked
-

## Done (confirmed via git history 2026-06-22)
- TikTok publishing: OAuth, chunked upload (video.upload), inbox-draft publish,
  site-verification served for app.johnchrisley.dev (commits 54308e3, 6dd4f4f, 9d78638)
- Multi-source backgrounds + voice rotation (commit 54308e3)
- Word-by-word subtitle highlighting (WhisperX) and Reddit comment-card intro
- v2 video polish: 60s min length, bold font, highlight-glitch fix (commit eda6c31)
- qwen3 reasoning-artifact stripping in narration (commit 97e09bc)
- Chatterbox local TTS + semantic video-text matching (per README; corroborated by history)

## Milestones (newest at top)
<!-- AUTO:MILESTONES -->

- 2026-06-22 - Docs seeded from README + ~/knowledge
