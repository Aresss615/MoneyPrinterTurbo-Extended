# DECISIONS - MoneyPrinterTurbo-Extended

Append-only decision log. Newest at top. Never edit an old entry; to change a
decision, add a new one and set "Supersedes". Record only choices that are
expensive to reverse or that a future session would re-argue (see
~/knowledge/MAINTENANCE.md).

Entries written by the `decide:` commit prefix start with Why/Alternatives = TODO.
Fill them in. Seed entries reconciled from README + ~/knowledge on 2026-06-22.

<!-- AUTO:DECISIONS -->

## 2026-06-23 - Gate creator/TikTok functions behind an owner access key before public hosting
Decision: Protect the creator-console's TikTok functions with an owner-only access
key (Codex change). When a key is configured, requests must send it in the
`X-Creator-Access-Key` header or they are rejected (401).
Why: The TikTok OAuth token is stored server-wide, not per device. On a public
tunnel, any device that opens the hosted creator console could see/use the same
connected TikTok account. The key gates owner-only actions before public hosting.
How it works:
- Config accepts either `[app] creator_access_key = "your-long-private-key"` or the
  `CREATOR_ACCESS_KEY` env var (env wins). Empty key = gate disabled (local dev).
- The creator console shows a TikTok locked/unlock state; the owner enters the key
  once per browser and it is stored locally for subsequent requests.
- Protected: TikTok OAuth/status, publish, inbox upload, and TikTok
  schedule-related endpoints. Comparison uses `hmac.compare_digest` (base.py).
Alternatives rejected: per-device OAuth tokens (larger change); leaving the console
open and relying on an obscure URL (unsafe once publicly hosted).

## 2026-06-22 - Fork MoneyPrinterTurbo rather than build from scratch (reconciled)
Decision: Build on harry0703/MoneyPrinterTurbo as an enhanced fork.
Why: Reuse an existing end-to-end pipeline and extend it (subtitles, TTS, matching)
instead of reimplementing. (README)
Alternatives rejected: TODO - Needs verification.

## 2026-06-22 - Use local/free models over paid APIs (reconciled)
Decision: Use Chatterbox (local TTS, voice cloning) + Edge-TTS and Ollama for
scripts, instead of Azure/paid TTS or hosted LLMs.
Why: No API costs / no rate limits; matches Jc's standing cost-cutting + local-first
rule (~/knowledge/preference.md). (README "no API costs")
Alternatives rejected: Azure TTS / paid hosted models.

## 2026-06-22 - Public hosting via Cloudflare tunnel (seeded)
Decision: Expose the app at app.johnchrisley.dev through a Cloudflare tunnel.
Why: Needed a public URL for TikTok app review. (~/knowledge)
Alternatives rejected: TODO - Needs verification. Note: current liveness Needs verification.
