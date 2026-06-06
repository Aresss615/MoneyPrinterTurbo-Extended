# Plan: Narrator-gender fix + Video Library

Implementation plan for MoneyPrinterTurbo-Extended (the faceless-video creator console).
Hand this to an implementing agent. Work on branch `feat/backgrounds-voices-tiktok`
(current branch). Do not change OAuth scopes or the TikTok publish/inbox API logic.

## Goal

1. **Fix the wrong-gender narrator.** First-person stories must be narrated by a voice
   matching the storyteller's gender (e.g. a woman's story → a female voice). Today
   `pick_voice()` chooses randomly from a mixed-gender pool, ignoring the story.
2. **Add a Video Library** in the web console listing every generated video, each with:
   post-as-draft, post-as-Direct-Post, posted-status badge, regenerate-with-corrected-voice,
   copy caption/hashtags, and delete. Plus a story-based display name + download filename,
   and a storage-cleanup tool.

## Repo facts (already verified — rely on these)

- Each video lives at `storage/tasks/<task_id>/final-1.mp4`, with `story.json`
  (a dumped `CreatorStory`) written beside it at submission time
  (`app/controllers/v1/creator.py` `create_creator_video`).
- Static mount: `app/asgi.py` mounts `storage/tasks` at `/tasks`, so the video URL is
  `/tasks/<task_id>/final-1.mp4`.
- Task state (`app/services/state.py` MemoryState) is in-memory only and lost on restart;
  the **files on disk are the durable source of truth** for the library — scan them.
- Voice pool: `app/services/creator_console.py` `VOICE_POOL`. Every entry already ends in
  `-Male` or `-Female` (e.g. `"en-US-AvaNeural-Female"`, `"en-US-AndrewNeural-Male"`).
- The story JSON model is `CreatorStory` in `app/services/creator_console.py`.
- TikTok publish endpoints live in `app/controllers/v1/tiktok.py`:
  `POST /api/v1/tiktok/publish` (Direct Post) and `POST /api/v1/tiktok/upload-inbox` (draft).
  Both take `{task_id, ...}` and the video path is `storage/tasks/<task_id>/final-1.mp4`.
- Frontend is static: `resource/public/index.html` + `resource/public/assets/creator-console.js`
  (no build step). Tabs use `.tab[data-tab]` / `.tab-panel[data-panel]` with `switchTab()`.
  Left nav uses `.nav-item[data-section]`. The story payload is built by `collectStory()`.
- Tests live under `test/services/` and `test/controllers/`, pytest style.

---

## Part 1 — Narrator gender

### 1.1 `app/services/creator_console.py`

**Add a gender field to `CreatorStory`** (after `content_notes`):

```python
narrator_gender: str = ""  # "", "male", or "female"; "" = auto/unknown
```

**Update the ChatGPT prompt** (`CHATGPT_IDEA_PROMPT`):
- Add `"narrator_gender": ""` to the JSON template object (near `content_notes`).
- Add a field rule:
  `- narrator_gender: "male" or "female" — the gender of the first-person narrator
  telling the story, inferred from the content. Use "" only if genuinely ambiguous.`

**Make `pick_voice` gender-aware:**

```python
def pick_voice(rng=random, gender: str = "") -> str:
    """Pick an Edge-TTS voice, filtered by narrator gender when known.

    gender is "male"/"female"/"" (case-insensitive). Unknown/empty or a gender
    with no matching voices falls back to the full pool (previous behavior).
    """
    gender = (gender or "").strip().lower()
    pool = VOICE_POOL or [DEFAULT_VOICE_NAME]
    if gender in ("male", "female"):
        suffix = f"-{gender.capitalize()}"  # "-Male" / "-Female"
        filtered = [v for v in pool if v.endswith(suffix)]
        if filtered:
            pool = filtered
    return rng.choice(pool)
```

**Thread gender through `build_video_params`** — change the `voice_name` line:

```python
voice_name=pick_voice(rng, gender=story.narrator_gender),
```

### 1.2 UI: Narrator voice override (Auto/Male/Female)

`resource/public/index.html` — add a select in the create form (place it near the other
story inputs in the `data-section="story"` area, e.g. just above the Generate button):

```html
<label class="field">
  <span>Narrator voice</span>
  <select id="narratorGender">
    <option value="">Auto (match story)</option>
    <option value="male">Male</option>
    <option value="female">Female</option>
  </select>
</label>
```

`resource/public/assets/creator-console.js`:
- Add `narratorGender: document.querySelector("#narratorGender")` to the `els` object.
- In `collectStory()` add `narrator_gender: els.narratorGender.value,` to the returned object.
- In `fillFromStory(story)` add `els.narratorGender.value = story.narrator_gender || "";`
  so pasted ChatGPT JSON / restored drafts populate it.
- The dropdown should participate in autosave: add `els.narratorGender` to the `input`-listener
  list in `bindEvents()` (use `"change"` if `"input"` doesn't fire for selects in your setup).

**Semantics:** dropdown `""` (Auto) means "use the LLM's `narrator_gender` from the story";
`male`/`female` force it. Because `collectStory()` overwrites `narrator_gender` with the
dropdown value, when the user pastes JSON the dropdown is pre-filled from the JSON (via
`fillFromStory`), so Auto correctly preserves the LLM's inference.

---

## Part 2 — Per-video posted status (`publish.json`)

### 2.1 Marker helper — `app/services/creator_console.py`

```python
def publish_marker_path(task_id: str) -> str:
    return os.path.join(utils.task_dir(task_id), "publish.json")

def record_publish(task_id: str, method: str, result: dict) -> None:
    """Persist that a video was sent to TikTok. method is "inbox" or "direct"."""
    marker = {
        "method": method,
        "status": result.get("status", ""),
        "publish_id": result.get("publish_id", ""),
        "posted_at": time.time(),
    }
    with open(publish_marker_path(task_id), "w", encoding="utf-8") as fp:
        json.dump(marker, fp, indent=2)

def load_publish_marker(task_id: str) -> dict:
    path = publish_marker_path(task_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError):
        return {}
```

(Add `import os`, `import time`, `from app.utils import utils` if not already imported there.)

### 2.2 Write the marker on successful publish — `app/controllers/v1/tiktok.py`

- In `tiktok_publish`, after a successful `tiktok.publish_video(...)` call:
  `creator_console.record_publish(body.task_id, "direct", result)`
- In `tiktok_upload_inbox`, after a successful `tiktok.upload_video_to_inbox(...)`:
  `creator_console.record_publish(body.task_id, "inbox", result)`

Import `from app.services import creator_console`. Only write on success (inside the `try`,
after the call returns without raising).

---

## Part 3 — Library backend (`app/controllers/v1/creator.py`)

Add these endpoints to the existing `creator.py` router. Use `utils.get_response(...)` and
`HttpException` like the rest of the file.

### 3.1 Slug + display helpers — `app/services/creator_console.py`

```python
def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:max_len].rstrip("-")) or "video"
```

### 3.2 Library scan helper — `app/services/creator_console.py`

```python
def list_library_videos() -> list[dict]:
    """Scan storage/tasks for finished videos, newest first."""
    tasks_root = utils.task_dir()
    items = []
    for task_id in os.listdir(tasks_root):
        task_path = os.path.join(tasks_root, task_id)
        video_path = os.path.join(task_path, "final-1.mp4")
        if not os.path.isfile(video_path):
            continue
        story = {}
        story_path = os.path.join(task_path, "story.json")
        if os.path.isfile(story_path):
            try:
                with open(story_path, "r", encoding="utf-8") as fp:
                    story = json.load(fp)
            except (ValueError, OSError):
                story = {}
        title = story.get("comment_card_title") or story.get("video_subject") or task_id
        marker = load_publish_marker(task_id)
        items.append({
            "task_id": task_id,
            "display_name": title,
            "slug": slugify(title),
            "video_url": f"/tasks/{task_id}/final-1.mp4",
            "created_at": os.path.getmtime(video_path),
            "size_bytes": os.path.getsize(video_path),
            "posted": marker,  # {} when never posted
            "suggested_description": story.get("suggested_description", ""),
            "suggested_hashtags": story.get("suggested_hashtags", []),
        })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items
```

### 3.3 Endpoints

**`GET /api/v1/creator/library`** → `{ "videos": [...], "total_size_bytes": <int> }`
using `list_library_videos()`.

**`DELETE /api/v1/creator/library/{task_id}`**
- Validate `task_id` is a real subdir of `utils.task_dir()` (reject `..`/path traversal:
  resolve and confirm `os.path.commonpath` is the tasks root; 404 if the dir doesn't exist).
- `shutil.rmtree(task_path)`; return `{ "deleted": task_id }`.

**`POST /api/v1/creator/library/cleanup`** body `{ "older_than_days": 7, "dry_run": false }`
- Delete (or list, if `dry_run`) every library video whose `posted` marker is empty (never
  posted) **and** whose `created_at` is older than `older_than_days`.
- Return `{ "deleted": [task_id...], "freed_bytes": <int>, "dry_run": <bool> }`.
- Reuse `list_library_videos()` to enumerate; reuse the delete path logic.

**`POST /api/v1/creator/library/{task_id}/regenerate`** body
`{ "narrator_gender": "" | "male" | "female" }`
- Load the stored `story.json` for `task_id`; 404 if missing.
- Parse it into a `CreatorStory` (`creator_console.story_from_mapping(...)`); override
  `narrator_gender` with the body value if provided.
- Spawn a **new** task exactly like `create_creator_video` does (new `task_id`,
  write its own `story.json`, `sm.state.update_task`, `task_manager.add_task(tm.start, ...,
  stop_at="video")`). Return the new `{task_id, ...}`.
- Factor the task-spawning block in `create_creator_video` into a shared helper
  `def _start_creator_video(story: CreatorStory, request_id: str) -> dict:` and call it from
  both `create_creator_video` and the regenerate endpoint (DRY; avoids divergence).

> Note in code/comment: regenerate re-renders the whole video (TTS timing drives caption
> sync, so audio cannot be swapped in place). It reuses the stored story so nothing is
> re-pasted, and lets the user pick the corrected voice.

---

## Part 4 — Library UI

### 4.1 `resource/public/index.html`
- Add a left-nav item: `<button class="nav-item" type="button" data-section="library" title="Library">LB</button>`
  (matches existing nav-item pattern at lines 30-33).
- Add a `data-section="library"` panel/section containing:
  - A header row: total disk usage text + a cleanup control
    (`<input id="cleanupDays" type="number" value="7" min="1">` + `<button id="cleanupBtn">Delete unposted older than N days</button>`)
    + a `<button id="refreshLibrary">Refresh</button>`.
  - An empty container `<div id="libraryGrid" class="library-grid"></div>` that JS fills with cards.
- On the existing output (line 195), the download link already has `download`; the library
  cards will set their own `download` attribute (see JS).

### 4.2 `resource/public/assets/creator-console.js`
- Add `els` entries for `#libraryGrid`, `#cleanupDays`, `#cleanupBtn`, `#refreshLibrary`.
- `async function loadLibrary()`: `GET /api/v1/creator/library`, render cards into `#libraryGrid`,
  set the disk-usage header (format `total_size_bytes` with a `humanBytes()` helper).
- Card contents per video:
  - `<video controls playsinline src="<video_url>">` (poster frame doubles as thumbnail).
  - Title (`display_name`), relative created time, size.
  - **Status badge** from `posted`: `{}` → "Not posted"; `method==="inbox"` → "Draft sent";
    `method==="direct"` → "Posted" (+ relative `posted_at`).
  - Buttons:
    - **Send to inbox (draft)** → `POST /api/v1/tiktok/upload-inbox {task_id}` (reuse the
      existing call shape from `uploadToTikTokInbox`); on success refresh that card's status.
    - **Publish (Direct Post)** → `POST /api/v1/tiktok/publish {task_id}` (no extra fields
      needed; backend auto-fills caption/hashtags from `story.json`).
    - **Regenerate** → small voice `<select>` (Auto/Male/Female) + button →
      `POST /api/v1/creator/library/<task_id>/regenerate {narrator_gender}`; on success show
      "Regenerating…" and point the user to the Tasks/Create view (or poll the new task_id).
    - **Copy caption** → copies `suggested_description` + ` ` + `#`-joined `suggested_hashtags`
      to clipboard (reuse the clipboard pattern already used by `copyPrompt`).
    - **Delete** → confirm, then `DELETE /api/v1/creator/library/<task_id>`; remove the card.
    - **Download** → `<a href="<video_url>" download="<slug>.mp4">Download</a>`.
- `cleanupBtn` → `POST /api/v1/creator/library/cleanup {older_than_days, dry_run:false}` after a
  confirm dialog; then `loadLibrary()`.
- Wire it up: in `switchTab`/nav handling, call `loadLibrary()` when the Library section is
  shown; also bind `refreshLibrary`, `cleanupBtn` in `bindEvents()`. Refresh the library after
  a successful generate in `pollTask` (state===1) so new videos appear.
- Add small helpers: `humanBytes(n)` and `relativeTime(epochSeconds)`.

Keep styling consistent with existing classes (`primary-button`, `ghost-button`,
`status-message`, card/grid styles already in the stylesheet — add a `.library-grid` /
`.library-card` rule to the existing CSS file if one isn't present).

---

## Part 5 — Tests

Add/extend pytest tests (no network; use `tmp_path` and monkeypatch `utils.storage_dir`/
`task_dir` where needed, following existing test patterns in `test/services/` and
`test/controllers/`).

`test/services/test_creator_console.py`:
- `pick_voice` returns only `-Female` voices when `gender="female"`, only `-Male` when
  `"male"`, and any when `""` (seed `random` or pass a fake rng; assert membership/suffix).
- `pick_voice` falls back to full pool if a gender has no matching voices (temporarily
  monkeypatch `VOICE_POOL`).
- `slugify("AITA for leaving my sister's wedding?")` → `"aita-for-leaving-my-sister-s-wedding"`
  (assert lowercase, hyphenated, no trailing hyphen, length cap).
- `narrator_gender` round-trips through `parse_chatgpt_story_json` / `story_from_mapping`.
- `build_video_params` passes the story's gender into the chosen voice (e.g. set
  `narrator_gender="female"`, assert returned `voice_name` ends with `-Female`).
- `record_publish` then `load_publish_marker` round-trips; `load_publish_marker` returns `{}`
  when absent.
- `list_library_videos` over a temp tasks dir: create two task dirs with `final-1.mp4` +
  `story.json` (one with a `publish.json`), assert ordering by mtime desc, fields present,
  and `posted` reflects the marker.

`test/controllers/test_tiktok.py`:
- After a mocked-successful inbox upload, `publish.json` is written with `method="inbox"`.
- After a mocked-successful direct publish, `publish.json` is written with `method="direct"`.

New `test/controllers/test_creator_library.py` (or extend an existing creator controller test):
- `GET /creator/library` returns the seeded videos.
- `DELETE /creator/library/{task_id}` removes the dir; rejects traversal / unknown id (404).
- `POST /creator/library/cleanup` deletes only unposted videos older than the cutoff;
  `dry_run=true` deletes nothing and reports the would-delete list.
- `POST /creator/library/{task_id}/regenerate` returns a new task_id and writes a new
  `story.json` carrying the overridden `narrator_gender` (mock `task_manager.add_task`).

Run: `pytest test/ -q`. All tests must pass.

---

## Acceptance criteria

1. A story whose narrator is a woman renders with a female voice when `narrator_gender` is
   `"female"` (from the LLM JSON or the Auto/Female dropdown), and male→male. Auto with no
   gender keeps current random behavior.
2. The console has a **Library** tab listing every video in `storage/tasks/*/` with title,
   date, size, and a posted-status badge, newest first.
3. From the library a user can: send to TikTok inbox (draft), Direct Post, regenerate with a
   corrected voice, copy caption+hashtags, download as `<slug>.mp4`, and delete.
4. Publishing (either path) marks the video and the badge updates to "Draft sent"/"Posted".
5. The cleanup control removes only unposted videos older than N days (with a working dry-run).
6. `pytest test/ -q` is green. No TikTok OAuth scope or publish-API behavior changed.

## Out of scope (do not build)

Thumbnails beyond the `<video>` poster frame, auth, pagination, renaming the on-disk
`final-1.mp4` (URL stability depends on it), and any change to TikTok scopes or the
publish/inbox request bodies.
