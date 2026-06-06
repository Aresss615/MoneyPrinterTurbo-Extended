# Plan: Cancel button + Voice-misgender fix

Branch: `feat/backgrounds-voices-tiktok`. Hand to an implementing agent. Faceless-video
creator console (MoneyPrinterTurbo-Extended). Follow TDD; tests live under
`test/services/` and `test/controllers/` (pytest).

Three asks from the user, in priority order:

1. **Cancel button** — cancel the currently rendering/generating video, both the editor's
   single render and queue items.
2. **Fix voice misgendering** — last several videos all narrated by the opposite gender.
3. **TikTok "send to draft"** — user understands this is a TikTok limitation. **NO CHANGE.**
   Keep the inbox-upload (`video.upload`) flow exactly as-is until TikTok approves the app
   for `video.publish`. Do not touch TikTok publish/inbox logic or OAuth scopes.

User decisions captured during brainstorming:
- Cancel responsiveness: **graceful checkpoint** (not force-kill ffmpeg).
- Canceling a rendering queue item: **mark `canceled`, auto-continue to the next queued item.**
- Partial files on cancel: **delete the task working dir.**
- Queue Cancel button shown for items in status `queued` or `rendering`.

---

## Part 2 — Voice misgender (do this FIRST; highest user pain)

### Root cause (verified 2026-06-06)
Every recent `storage/tasks/*/story.json` has `narrator_gender == ""`. `creator_console.pick_voice`
only filters the mixed-gender `VOICE_POOL` when gender is `"male"`/`"female"`; with `""` it
falls back to `rng.choice(pool)` → **random**, so ~half come out wrong and feel "opposite."
The voice-selection code is otherwise correct (pool labels and `parse_voice_name` are fine).
The gender field simply never gets populated (pasted ChatGPT JSON omits it / leaves it blank).

Examples from the user's last renders (all `gender=''`, random voice):
- "My boyfriend secretly rates every woman..." (narrator female) → got Brian (Male)
- "...wearing a white dress because the bride..." (narrator female) → got Andrew (Male)

### Fix (decided)
All in `app/services/creator_console.py` unless noted.

1. **Prompt hardening** — in `CHATGPT_IDEA_PROMPT`, change the `narrator_gender` field rule
   to require a best-guess `"male"` or `"female"` and discourage `""` (only when truly
   impossible). Keeps future pastes populated.

2. **New `resolve_narrator_gender(story) -> str`** used as a fallback when
   `story.narrator_gender` is blank. Resolution order:
   a. If `story.narrator_gender` already in {`male`,`female`} → return it.
   b. Reddit self-tag regex over `narration_script` + `comment_card_title`:
      patterns like `28F`, `(30m)`, `F23`, `M 41` → `female`/`male`.
   c. Keyword heuristic (weighted vote over the script), strongest first:
      - direct self-ID: "as a woman/man", "i'm a girl/guy/woman/man", "being a mom/dad/mother/father" → that gender.
      - partner cues (heterosexual-assumption fallback, lowest weight, documented as such):
        "my husband"/"my fiancé(e)" → female; "my wife" → male;
        "my boyfriend" → female; "my girlfriend" → male.
      Return the winning gender, or `""` if no signal.
   d. Else `""`.

3. **`build_video_params`** — call `resolve_narrator_gender(story)`, pass the result to
   `pick_voice`, and `logger.info` the resolved gender + chosen voice (so this is debuggable
   next time). Persist the resolved gender onto the params/story dump if cheap.

4. **`pick_voice`** — when gender is still `""`, keep random but `logger.warning` that gender
   was unknown so it surfaces in logs.

5. **Tests** — `test/services/test_creator_console.py`: cover `resolve_narrator_gender`
   (explicit field, self-tags like `28F`/`(30m)`, keyword cases, ambiguous → `""`) and that
   `build_video_params` picks a gender-matched voice when inferable (seed the rng).

Note: the existing per-video **regenerate** endpoint already accepts a `narrator_gender`
override, so the user has a manual escape hatch for any miss.

---

## Part 1 — Cancel button

### Architecture (graceful, cooperative cancellation)
Renders run via `tm.start(task_id, params)` inside a daemon **thread**
(`InMemoryTaskManager`); moviepy runs ffmpeg **in-process**. Python threads can't be
force-killed, so we cancel cooperatively at pipeline checkpoints. Known limitation
(accepted): a cancel pressed during the final `write_videofile` encode only takes effect
when that step returns (up to ~a minute on a 60s+ video); during that lag the queue may
start the next item, so two encodes can briefly overlap.

### 2.1 New `app/services/task_control.py`
Tiny, dependency-free, thread-safe cancellation registry shared by the pipeline, queue,
and controller (separate module to avoid circular imports):
```
request_cancel(task_id)   # add to a Lock-guarded set
is_canceled(task_id) -> bool
clear(task_id)            # discard once a task ends
```

### 2.2 `app/models/const.py`
Add `TASK_STATE_CANCELED = -2`.

### 2.3 `app/services/task.py` — `start()`
- Add `_abort_if_canceled(task_id) -> bool` helper. Call it after each checkpoint
  (post script / audio / subtitle / materials / each encode iteration in
  `generate_final_videos`, and at the top of `start`).
- On cancel: `sm.state.update_task(task_id, state=const.TASK_STATE_CANCELED)`,
  `shutil.rmtree(utils.task_dir(task_id), ignore_errors=True)`, `task_control.clear(task_id)`,
  then return early.
- Also `task_control.clear(task_id)` on normal completion/failure to avoid leaks.

### 2.4 `app/services/creator_queue.py`
- New `cancel_queue_item(queue_id)`:
  - `dispatching` → raise `ValueError` (mirror the existing delete guard; never interrupt a
    TikTok upload).
  - `rendering` → `task_control.request_cancel(item.task_id)`; set `item.status = "canceled"`.
    Existing `start_next_queued_render` (blocks only while something is `"rendering"`) then
    auto-starts the next queued item → "mark canceled, continue."
  - `queued` / `rendered` / `scheduled` / `failed` → just set `status = "canceled"`.
- `sync_render_statuses` — if a `rendering` item's task is in `TASK_STATE_CANCELED`, set the
  item to `"canceled"` (covers the self-cancel race). `"canceled"` is already a valid
  `QUEUE_STATUSES` value.

### 2.5 `app/controllers/v1/creator.py`
- `POST /creator/videos/{task_id}/cancel` → `task_control.request_cancel(task_id)`; return 200.
- `POST /creator/queue/{queue_id}/cancel` → `creator_queue.cancel_queue_item(queue_id)`;
  404 on `FileNotFoundError`, 400 on `ValueError` (dispatching).

### 2.6 Frontend — `resource/public/index.html`, `assets/creator-console.js`, `assets/creator-console.css`
- **Editor:** add a **Cancel** button by the progress bar; show only while generating
  (toggle in `setGenerating`). Click → POST the editor cancel endpoint, set status
  "Canceling…". Extend `pollTask` to handle state `-2` → clear timer, `setGenerating(false)`,
  status "Video canceled."
- **Queue cards (`renderQueue`):** add a **Cancel** button when status is `queued` or
  `rendering`. Click → `window.confirm` → POST the queue cancel endpoint → `loadQueue()`.
  `queueStatusClass` already maps `"canceled"` to the failed/grey style.

### 2.7 Tests
- `test/services/test_task_control.py` — request/is/clear.
- `test/services/test_creator_queue.py` — `cancel_queue_item` per status + dispatching guard
  + canceled-task `sync_render_statuses` mapping.
- `test/controllers/test_creator_*.py` — both endpoints (success + 404/400).
- `test/services/test_task.py` (or extend) — monkeypatch the pipeline step fns to no-ops,
  pre-set the cancel flag, assert `start()` yields `TASK_STATE_CANCELED` and removes the
  task dir.

---

## Out of scope
- TikTok draft/publish behavior — leave as-is (TikTok limitation; revisit after app approval).
- No OAuth scope changes.
