# Always-on legal/website pages

Static source for the public pages TikTok app review requires. Hosted on
**GitHub Pages** (free, always on, no Mac) so the URLs resolve 24/7 even when
the bot/Mac is offline.

| TikTok field | URL (submit to TikTok dev portal) |
|--------------|-----------------------------------|
| Website URL / Web/Desktop URL | `https://johnchrisley.dev/legal` |
| Terms of Service URL | `https://johnchrisley.dev/legal/terms` |
| Privacy Policy URL | `https://johnchrisley.dev/legal/privacy` |
| Login Kit redirect URI | `https://app.johnchrisley.dev/api/v1/callback` |

None of these contain the word "tiktok" or `/api/v1`, which is why the first
submission (`/api/v1/tiktok/terms`, `/api/v1/tiktok/privacy`) was rejected.

**Do not submit `https://app.johnchrisley.dev` as the Website/Web/Desktop URL.**
That host is the creator console + OAuth callback; it runs on the Mac through the
Cloudflare tunnel and is **only online when the bot is actively creating**. The
second rejection ("Invalid Website URL") was caused by submitting `app.` as the
Website URL — TikTok's reviewer crawled it while the Mac was offline. `app.`
belongs **only** in the Login Kit redirect URI, which is matched, not crawled.

The always-on public website for review is `https://johnchrisley.dev/legal` (a
GitHub Pages product page describing JC Video Factory). Use that for the Website
URL field; it stays up 24/7 regardless of the Mac.

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
