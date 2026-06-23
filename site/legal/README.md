# Always-on legal/website pages

Static source for the public pages TikTok app review requires. Hosted on
**GitHub Pages** (free, always on, no Mac) so the URLs resolve 24/7 even when
the bot/Mac is offline.

| Page | URL (submit to TikTok dev portal) |
|------|-----------------------------------|
| Website URL | `https://johnchrisley.dev/legal` |
| Terms of Service | `https://johnchrisley.dev/legal/terms` |
| Privacy Policy | `https://johnchrisley.dev/legal/privacy` |

None of these contain the word "tiktok" or `/api/v1`, which is why the previous
submission (`/api/v1/tiktok/terms`, `/api/v1/tiktok/privacy`) was rejected.

The landing page (`index.html`) pings `https://app.johnchrisley.dev/health` and
shows **Creator service: online / offline** — the bot runs on the Mac and is
only online when actively creating; these pages stay up regardless.

## Deploy

Copied into the GitHub Pages repo `Aresss615/Aresss615.github.io` under `/legal/`.
To update: copy this folder to that repo's `legal/`, commit, push. GitHub Pages
rebuilds in ~1 min.

## TikTok domain-verification files

When you add each URL as a **URL property** in the TikTok dev portal, TikTok gives
you a `tiktok<code>.txt` file. Drop it next to the matching page so it serves at
the property's path, then click Verify:

| URL property | Put the file at |
|--------------|-----------------|
| `https://johnchrisley.dev/legal` | `legal/tiktok<code>.txt` |
| `https://johnchrisley.dev/legal/terms` | `legal/terms/tiktok<code>.txt` |
| `https://johnchrisley.dev/legal/privacy` | `legal/privacy/tiktok<code>.txt` |

Commit + push, wait for the Pages rebuild, then verify in the portal.
