const MIN_SECONDS = 60; // "story" lane minimum
const GROWTH_MIN_SECONDS = 30; // "growth" lane minimum
const WORDS_PER_MINUTE = 165;
const STORAGE_KEY = "jc-video-factory-draft-v1";
const CREATOR_ACCESS_KEY_STORAGE = "jc-video-factory-creator-access-key-v1";

// Offline safety-net only: the live prompt is fetched from
// GET /api/v1/creator/idea-prompt (served from creator_console.CHATGPT_IDEA_PROMPT).
// This mirrors that prompt minus the backtick-heavy strict-JSON paragraph, which
// cannot live inside a template literal.
const fallbackPrompt = `You are the story scout and scriptwriter for a faceless Reddit-story TikTok account. The account wins on RETENTION, not volume: a strong hook, fast escalation, a reversal, and a verdict question. Find ONE public Reddit story and turn it into a tight spoken script.

Niche — pick EXACTLY ONE territory and make the story clearly belong to it:
1. Family betrayal & inheritance (wills, money, favoritism, hidden paperwork, family duty)
2. Relationship & wedding implosions (cheating, broken engagements, wedding/in-law drama)
3. Workplace revenge & boundaries (unfair bosses, stolen credit, malicious compliance, punished for an emergency)

Retention rules (most important):
- Open AT the moment of conflict. The first sentence is the hook — no backstory.
- Escalate every 5-8 seconds: each beat adds a new fact, stake, secret, or shift in sympathy.
- Include at least one "wait, what?" reversal that recontextualizes the story.
- End on a verdict question, never a generic "what do you think" or "part 2".

Pacing template the narration MUST follow:
- 0-3s Hook: start at the conflict.
- 3-8s Premise: who did what to whom.
- 8-15s Friction: the first complicating fact.
- 15-25s Escalation: a new stake, secret, or contradiction.
- 25-40s Reversal: the "wait, what?" beat.
- Final beat: the verdict question.

Length lane (choose one and write to its word count):
- "growth": 90-130 words (~35-50s read aloud). Tighter, one clean reversal.
- "story": 170-260 words (~60-95s read aloud). Room for a second stake and a deeper reversal.
Default to "story" unless the source is too thin.

Frame one — comment_card_title is the first thing the viewer sees: a 6-10 word punchy line that STATES the conflict.

Safety & ethics:
- Use only public Reddit posts.
- Do not include real names, usernames, locations, workplaces, schools, or identifying details.
- Do not invent a Reddit source URL. If you cannot verify a source, leave it blank.
- Paraphrase into a clean narration script instead of copying the post word-for-word.
- Keep it safe for monetized short-form content.

Return ONE complete JSON object and nothing else (no code fences, no comments, no trailing commas). Use straight double quotes; escape inner quotes; write each value on one line.

Return ONLY this JSON:

{
  "source_url": "",
  "subreddit": "",
  "original_title": "",
  "territory": "",
  "length_lane": "story",
  "comment_card_username": "u/throwaway_aita",
  "comment_card_title": "",
  "comment_card_likes": "99+",
  "video_subject": "",
  "narration_script": "",
  "caption_keywords_to_highlight": [],
  "suggested_hook": "",
  "comment_prompt": "",
  "suggested_description": "",
  "suggested_hashtags": [],
  "content_notes": "",
  "narrator_gender": ""
}

Field rules:
- territory: "family", "relationship", or "workplace".
- length_lane: "growth" (90-130 words) or "story" (170-260 words).
- comment_card_title: 6-10 words that STATE the conflict, like a punchy Reddit title.
- narration_script: first person, follows the pacing template, word count set by length_lane, no markdown.
- caption_keywords_to_highlight: 8-15 short words or phrases to red-highlight in captions.
- suggested_hook: the first narrated sentence — the conflict, in one line.
- comment_prompt: closing verdict question, e.g. "NTA or YTA?", "Who was actually in the wrong?", "What would you do?". Never "part 2".
- suggested_description: caption, max 150 characters, keyworded for search, ending with the comment_prompt question.
- suggested_hashtags: 5-8 hashtags.
- content_notes: note anything softened, anonymized, or sensitive.
- narrator_gender: "male" or "female" inferred from content. Use "" only if genuinely ambiguous.`;

const sampleStory = `AITA for refusing to give up the window seat I paid extra for? I booked a window seat months before my flight because I get motion sick if I cannot look outside. I also paid extra for it, because the airline made that seat an upgrade. When I boarded, a mom and her son were already in my row. She had the middle and aisle seats, and she asked if I would switch so her son could have the window. I said I was sorry, but I needed the seat I paid for because I get sick. She rolled her eyes and said he was only eight and had been excited all week. I still said no. The whole row stared at me while she made passive aggressive comments about people having no kindness anymore. Her son cried a little, and I felt awful, but I stayed in my seat. My girlfriend says I technically did nothing wrong, but I could have been nicer. So am I the asshole?`;

const els = {
    storyText: document.querySelector("#storyText"),
    jsonInput: document.querySelector("#jsonInput"),
    ideaPrompt: document.querySelector("#ideaPrompt"),
    cardTitle: document.querySelector("#cardTitle"),
    cardUsername: document.querySelector("#cardUsername"),
    cardLikes: document.querySelector("#cardLikes"),
    narratorGender: document.querySelector("#narratorGender"),
    highlightInput: document.querySelector("#highlightInput"),
    sourceUrl: document.querySelector("#sourceUrl"),
    subreddit: document.querySelector("#subreddit"),
    hashtags: document.querySelector("#hashtags"),
    contentNotes: document.querySelector("#contentNotes"),
    connectionPill: document.querySelector("#connectionPill"),
    wordCount: document.querySelector("#wordCount"),
    estimatedDuration: document.querySelector("#estimatedDuration"),
    highlightCount: document.querySelector("#highlightCount"),
    validationLabel: document.querySelector("#validationLabel"),
    durationStatus: document.querySelector("#durationStatus"),
    minimumCheck: document.querySelector("#minimumCheck"),
    cardCheck: document.querySelector("#cardCheck"),
    backendCheck: document.querySelector("#backendCheck"),
    previewUsername: document.querySelector("#previewUsername"),
    previewTitle: document.querySelector("#previewTitle"),
    previewLikes: document.querySelector("#previewLikes"),
    previewCaption: document.querySelector("#previewCaption"),
    saveState: document.querySelector("#saveState"),
    statusMessage: document.querySelector("#statusMessage"),
    taskStatus: document.querySelector("#taskStatus"),
    cancelTask: document.querySelector("#cancelTask"),
    progressBar: document.querySelector("#progressBar"),
    outputVideo: document.querySelector("#outputVideo"),
    downloadLink: document.querySelector("#downloadLink"),
    manualUploadPanel: document.querySelector("#manualUploadPanel"),
    manualRevealFile: document.querySelector("#manualRevealFile"),
    manualDownloadFile: document.querySelector("#manualDownloadFile"),
    manualCaption: document.querySelector("#manualCaption"),
    manualFileName: document.querySelector("#manualFileName"),
    copyManualCaption: document.querySelector("#copyManualCaption"),
    tiktokPill: document.querySelector("#tiktokPill"),
    facebookPill: document.querySelector("#facebookPill"),
    publishTikTok: document.querySelector("#publishTikTok"),
    uploadInboxTikTok: document.querySelector("#uploadInboxTikTok"),
    publishFacebook: document.querySelector("#publishFacebook"),
    publishStatus: document.querySelector("#publishStatus"),
    publishSettings: document.querySelector("#publishSettings"),
    tiktokPrivacy: document.querySelector("#tiktokPrivacy"),
    allowComment: document.querySelector("#allowComment"),
    allowDuet: document.querySelector("#allowDuet"),
    allowStitch: document.querySelector("#allowStitch"),
    tiktokAigc: document.querySelector("#tiktokAigc"),
    tiktokConsent: document.querySelector("#tiktokConsent"),
    queueJsonInput: document.querySelector("#queueJsonInput"),
    importQueue: document.querySelector("#importQueue"),
    clearQueueJson: document.querySelector("#clearQueueJson"),
    clearFinishedQueue: document.querySelector("#clearFinishedQueue"),
    startQueue: document.querySelector("#startQueue"),
    pauseQueue: document.querySelector("#pauseQueue"),
    refreshQueue: document.querySelector("#refreshQueue"),
    queueList: document.querySelector("#queueList"),
    queueSummary: document.querySelector("#queueSummary"),
    queueStatus: document.querySelector("#queueStatus"),
    libraryGrid: document.querySelector("#libraryGrid"),
    libraryUsage: document.querySelector("#libraryUsage"),
    cleanupDays: document.querySelector("#cleanupDays"),
    cleanupBtn: document.querySelector("#cleanupBtn"),
    refreshLibrary: document.querySelector("#refreshLibrary"),
};

let pollTimer = null;
let saveTimer = null;
let connectionTimer = null;
let tiktokTimer = null;
let facebookTimer = null;
let queueTimer = null;
let facebookConnected = false;
let currentTaskId = null;
let tiktokCreatorInfo = {};
let currentSuggestedDescription = "";
let currentLengthLane = "story";
let currentCommentPrompt = "";
let currentTerritory = "";
let currentNarratorGender = "";

function minSecondsForLane(lane) {
    return lane === "growth" ? GROWTH_MIN_SECONDS : MIN_SECONDS;
}

function words(text) {
    return (text || "").match(/\b[\w'-]+\b/g) || [];
}

function estimateSeconds(text) {
    const count = words(text).length;
    return count === 0 ? 0 : Math.ceil((count * 60) / WORDS_PER_MINUTE);
}

function cleanText(value) {
    return String(value || "").trim().replace(/\s+/g, " ");
}

function truncateText(value, maxLength) {
    const cleaned = cleanText(value);
    if (cleaned.length <= maxLength) return cleaned;
    const trimmed = cleaned.slice(0, maxLength).replace(/\s+\S*$/, "");
    return `${trimmed || cleaned.slice(0, maxLength - 3)}...`;
}

function deriveTitle(text) {
    const cleaned = cleanText(text);
    if (!cleaned) return "";
    const indexes = ["?", ".", "!"]
        .map((mark) => cleaned.indexOf(mark))
        .filter((index) => index >= 0);
    const end = indexes.length ? Math.min(...indexes) + 1 : cleaned.length;
    return truncateText(cleaned.slice(0, end), 120);
}

function splitList(value) {
    return cleanText(value)
        .split(/[,;\n]/)
        .map((item) => cleanText(item))
        .filter(Boolean);
}

function hashtagsFromInput(value) {
    return splitList(value).map((tag) => `#${tag.replace(/^#/, "").replace(/\s+/g, "")}`);
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function buildPreviewCaption(text, highlights) {
    const firstWords = words(text).slice(0, 11).join(" ");
    let caption = escapeHtml(firstWords || "Paste a story to preview the opening caption.");
    highlights.slice(0, 4).forEach((keyword) => {
        const escaped = escapeHtml(keyword);
        if (!escaped) return;
        caption = caption.replace(
            new RegExp(`\\b(${escapeRegExp(escaped)})\\b`, "i"),
            "<mark>$1</mark>"
        );
    });
    return caption;
}

function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function collectStory() {
    const script = cleanText(els.storyText.value);
    const title = cleanText(els.cardTitle.value) || deriveTitle(script);
    const highlights = splitList(els.highlightInput.value);

    return {
        source_url: cleanText(els.sourceUrl.value),
        subreddit: cleanText(els.subreddit.value),
        original_title: "",
        territory: currentTerritory,
        length_lane: currentLengthLane,
        comment_card_username: cleanText(els.cardUsername.value) || "u/throwaway_aita",
        comment_card_title: title,
        comment_card_likes: cleanText(els.cardLikes.value) || "99+",
        video_subject: title || "AITA story",
        narration_script: script,
        caption_keywords_to_highlight: highlights,
        suggested_hook: "",
        comment_prompt: currentCommentPrompt,
        suggested_description: currentSuggestedDescription,
        suggested_hashtags: hashtagsFromInput(els.hashtags.value),
        content_notes: cleanText(els.contentNotes.value),
        narrator_gender: currentNarratorGender,
        narrator_gender_override: els.narratorGender.value,
    };
}

function fillFromStory(story) {
    const script = cleanText(story.narration_script);
    els.storyText.value = script;
    els.cardTitle.value = cleanText(story.comment_card_title) || deriveTitle(script);
    els.cardUsername.value = cleanText(story.comment_card_username) || "u/throwaway_aita";
    els.cardLikes.value = cleanText(story.comment_card_likes) || "99+";
    els.highlightInput.value = (story.caption_keywords_to_highlight || []).join(", ");
    els.sourceUrl.value = cleanText(story.source_url);
    els.subreddit.value = cleanText(story.subreddit);
    els.hashtags.value = (story.suggested_hashtags || []).join(", ");
    els.contentNotes.value = cleanText(story.content_notes);
    currentNarratorGender = ["male", "female"].includes(cleanText(story.narrator_gender).toLowerCase())
        ? cleanText(story.narrator_gender).toLowerCase()
        : "";
    els.narratorGender.value = story.narrator_gender_override || "";
    currentSuggestedDescription = cleanText(story.suggested_description);
    currentLengthLane = (cleanText(story.length_lane).toLowerCase() === "growth") ? "growth" : "story";
    currentCommentPrompt = cleanText(story.comment_prompt);
    currentTerritory = cleanText(story.territory).toLowerCase();
    updateAll();
    scheduleSave();
}

function updateAll() {
    const story = collectStory();
    const wordCount = words(story.narration_script).length;
    const seconds = estimateSeconds(story.narration_script);
    const highlights = story.caption_keywords_to_highlight;
    const minSeconds = minSecondsForLane(story.length_lane);
    const meetsMinimum = seconds >= minSeconds;
    const hasTitle = Boolean(story.comment_card_title);

    els.wordCount.textContent = String(wordCount);
    els.estimatedDuration.textContent = `${seconds}s`;
    els.highlightCount.textContent = String(highlights.length);
    els.validationLabel.textContent = meetsMinimum && hasTitle ? "Ready" : "Draft";

    els.durationStatus.textContent = meetsMinimum ? `${seconds}s ready` : `${seconds}s / ${minSeconds}s min`;
    els.durationStatus.classList.toggle("good", meetsMinimum);
    els.durationStatus.classList.toggle("bad", wordCount > 0 && !meetsMinimum);

    els.minimumCheck.textContent = wordCount ? (meetsMinimum ? `${seconds}s` : `${seconds}s`) : "Needs script";
    els.minimumCheck.className = meetsMinimum ? "good" : wordCount ? "bad" : "warn";
    els.cardCheck.textContent = hasTitle ? "Ready" : "Needs title";
    els.cardCheck.className = hasTitle ? "good" : "warn";

    els.previewUsername.textContent = story.comment_card_username;
    els.previewTitle.textContent = story.comment_card_title || "AITA for refusing to switch seats?";
    els.previewLikes.textContent = `${story.comment_card_likes || "99+"} likes`;
    els.previewCaption.innerHTML = buildPreviewCaption(story.narration_script, highlights);
}

function scheduleSave() {
    window.clearTimeout(saveTimer);
    els.saveState.textContent = "Saving draft";
    saveTimer = window.setTimeout(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(collectStory()));
        els.saveState.textContent = "Draft saved locally";
    }, 220);
}

function restoreDraft() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
        fillFromStory({
            narration_script: sampleStory,
            comment_card_username: "u/throwaway_aita",
            comment_card_title: deriveTitle(sampleStory),
            comment_card_likes: "99+",
            caption_keywords_to_highlight: ["window seat", "paid extra", "motion sick", "stared", "comments"],
            suggested_hashtags: ["#aita", "#redditstories", "#storytime", "#travel"],
            suggested_description: "A window seat conflict turned the whole row against me.",
        });
        return;
    }

    try {
        fillFromStory(JSON.parse(stored));
    } catch (error) {
        localStorage.removeItem(STORAGE_KEY);
        fillFromStory({ narration_script: sampleStory });
    }
}

function setStatus(message, type = "") {
    els.statusMessage.textContent = message;
    els.statusMessage.className = `status-message ${type}`.trim();
}

function getCreatorAccessKey() {
    try {
        return localStorage.getItem(CREATOR_ACCESS_KEY_STORAGE) || "";
    } catch (error) {
        return "";
    }
}

function setCreatorAccessKey(value) {
    try {
        localStorage.setItem(CREATOR_ACCESS_KEY_STORAGE, value);
    } catch (error) {
        // Ignore private-mode storage failures; the current request will still retry.
    }
}

function creatorAccessHeaders(headers = {}) {
    const nextHeaders = { ...headers };
    const accessKey = getCreatorAccessKey();
    if (accessKey) {
        nextHeaders["X-Creator-Access-Key"] = accessKey;
    }
    return nextHeaders;
}

function promptCreatorAccessKey() {
    const value = window.prompt("Owner access key");
    if (value === null) return false;
    const accessKey = cleanText(value);
    if (!accessKey) return false;
    setCreatorAccessKey(accessKey);
    return true;
}

async function fetchWithCreatorAccess(url, options = {}, retryOnUnauthorized = true) {
    const requestOptions = {
        ...options,
        headers: creatorAccessHeaders(options.headers || {}),
    };
    const response = await fetch(url, requestOptions);
    let payload = {};
    try {
        payload = await response.json();
    } catch (error) {
        payload = {};
    }
    if (response.status === 401 && retryOnUnauthorized && promptCreatorAccessKey()) {
        return fetchWithCreatorAccess(url, options, false);
    }
    return { response, payload };
}

function humanBytes(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let size = value / 1024;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function relativeTime(epochSeconds) {
    const timestamp = Number(epochSeconds || 0);
    if (!timestamp) return "";
    const diff = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
    const units = [
        ["year", 31536000],
        ["month", 2592000],
        ["day", 86400],
        ["hour", 3600],
        ["minute", 60],
    ];
    for (const [label, seconds] of units) {
        const count = Math.floor(diff / seconds);
        if (count >= 1) return `${count} ${label}${count === 1 ? "" : "s"} ago`;
    }
    return "just now";
}

function platformStatusLabel(platform, status) {
    if (!status || !Object.keys(status).length) {
        return platform === "tiktok" ? "Not posted" : null;
    }
    const age = status.posted_at ? ` ${relativeTime(status.posted_at)}` : "";
    if (platform === "tiktok") {
        if (status.method === "inbox") return `TT draft${age}`;
        if (status.method === "direct") return `TT posted${age}`;
        return `TT sent${age}`;
    }
    if (platform === "facebook") return `FB posted${age}`;
    if (platform === "instagram") return `IG posted${age}`;
    if (platform === "youtube") return `YT posted${age}`;
    return `Sent${age}`;
}

function libraryStatusLabel(posted) {
    if (!posted || !Object.keys(posted).length) return "Not posted";
    const age = posted.posted_at ? ` ${relativeTime(posted.posted_at)}` : "";
    if (posted.method === "inbox") return `TT draft${age}`;
    if (posted.method === "direct") return `TT posted${age}`;
    return `Sent${age}`;
}

function facebookStatusLabel(fbPosted) {
    if (!fbPosted || !Object.keys(fbPosted).length) return null;
    const age = fbPosted.posted_at ? ` ${relativeTime(fbPosted.posted_at)}` : "";
    return `FB posted${age}`;
}

function captionForVideo(video) {
    const hashtags = Array.isArray(video.suggested_hashtags)
        ? video.suggested_hashtags.map((tag) => {
            const text = cleanText(tag);
            return text.startsWith("#") ? text : `#${text}`;
        })
        : [];
    return cleanText([video.suggested_description, hashtags.join(" ")]
        .filter(Boolean)
        .join(" "));
}

function captionForStory(story) {
    const hashtags = Array.isArray(story.suggested_hashtags)
        ? story.suggested_hashtags.map((tag) => {
            const text = cleanText(tag);
            return text.startsWith("#") ? text : `#${text}`;
        })
        : [];
    return cleanText([story.suggested_description, hashtags.join(" ")]
        .filter(Boolean)
        .join(" ")) || cleanText(story.comment_card_title || story.video_subject);
}

function slugifyFilename(value) {
    const slug = cleanText(value)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 60)
        .replace(/-+$/g, "");
    return slug || "jc-video-factory";
}

function manualDownloadName(story) {
    return `${slugifyFilename(story.comment_card_title || story.video_subject)}.mp4`;
}

function hideManualUpload() {
    els.manualUploadPanel.hidden = true;
    els.manualRevealFile.disabled = true;
    els.manualDownloadFile.href = "#";
    els.manualCaption.value = "";
    els.manualFileName.textContent = "MP4 file";
    els.downloadLink.style.display = "none";
}

function showManualUpload(videoUrl) {
    if (!videoUrl) return;
    const story = collectStory();
    const filename = manualDownloadName(story);
    els.manualUploadPanel.hidden = false;
    els.manualRevealFile.disabled = false;
    els.manualDownloadFile.href = videoUrl;
    els.manualDownloadFile.setAttribute("download", filename);
    els.manualCaption.value = captionForStory(story);
    els.manualFileName.textContent = filename;
}

async function revealVideoFile(taskId, statusEl = null) {
    if (!taskId) {
        setPublishStatus("Generate a video first.", "error");
        return;
    }
    const setRevealStatus = (message, type = "") => {
        if (statusEl) {
            setCardStatus(statusEl, message, type);
        } else {
            setPublishStatus(message, type);
        }
    };

    setRevealStatus("Opening file location.");
    try {
        const response = await fetch(`/api/v1/creator/library/${encodeURIComponent(taskId)}/reveal`, {
            method: "POST",
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Could not open file location.");
        }
        setRevealStatus("File location opened.", "good");
    } catch (error) {
        setRevealStatus(error.message || "Could not open file location.", "error");
    }
}

async function copyManualCaption() {
    const caption = els.manualCaption.value.trim();
    if (!caption) {
        setPublishStatus("Add a caption first.", "error");
        return;
    }
    try {
        await navigator.clipboard.writeText(caption);
        setPublishStatus("Caption copied.", "good");
    } catch (error) {
        els.manualCaption.focus();
        els.manualCaption.select();
        setPublishStatus("Caption selected. Use your copy shortcut.", "");
    }
}

function formatScheduleTime(epochSeconds) {
    const timestamp = Number(epochSeconds || 0);
    if (!timestamp) return "";
    return new Date(timestamp * 1000).toLocaleString();
}

function defaultScheduleValue(minutesFromNow = 10) {
    const date = new Date(Date.now() + minutesFromNow * 60000);
    date.setSeconds(0, 0);
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - offset * 60000);
    return local.toISOString().slice(0, 16);
}

function localDateTimeToEpoch(value) {
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return 0;
    return Math.floor(timestamp / 1000);
}

function scheduleSummary(item) {
    const schedule = item.schedule || {};
    if (!schedule.action) return "";
    const action = schedule.action === "direct" ? "Direct" : "Draft";
    const when = formatScheduleTime(schedule.run_at_epoch);
    if (item.status === "sent") return `${action} sent`;
    if (item.status === "dispatching") return `${action} dispatching`;
    if (item.status === "failed") return `${action} failed`;
    return `${action} scheduled${when ? ` for ${when}` : ""}`;
}

function latestActiveSchedule(video) {
    const schedules = Array.isArray(video.schedules) ? video.schedules : [];
    return schedules.find((item) => ["scheduled", "dispatching"].includes(item.status))
        || schedules.find((item) => item.status === "sent")
        || schedules[0];
}

function privacyOptionsHtml(selected = "") {
    const options = Array.isArray(tiktokCreatorInfo.privacy_level_options)
        ? tiktokCreatorInfo.privacy_level_options
        : [];
    const values = options.length ? options : [els.tiktokPrivacy.value || "SELF_ONLY"];
    const unique = [...new Set(values.filter(Boolean))];
    return [
        '<option value="">Privacy</option>',
        ...unique.map((privacy) => `<option value="${escapeHtml(privacy)}" ${privacy === selected ? "selected" : ""}>${escapeHtml(privacyLabel(privacy))}</option>`),
    ].join("");
}

function scheduleControlsHtml(caption, schedule = null) {
    const action = schedule?.action || "draft";
    const runAt = schedule?.run_at_epoch
        ? defaultInputFromEpoch(schedule.run_at_epoch)
        : defaultScheduleValue();
    return `
        <div class="schedule-box">
            <div class="schedule-grid">
                <label class="settings-field">
                    <span>Action</span>
                    <select data-action="schedule-action">
                        <option value="draft" ${action === "draft" ? "selected" : ""}>Draft</option>
                        <option value="direct" ${action === "direct" ? "selected" : ""}>Direct</option>
                    </select>
                </label>
                <label class="settings-field">
                    <span>Run at</span>
                    <input type="datetime-local" data-action="schedule-time" value="${escapeHtml(runAt)}">
                </label>
                <label class="settings-field">
                    <span>Privacy</span>
                    <select data-action="schedule-privacy">${privacyOptionsHtml(schedule?.privacy || "")}</select>
                </label>
            </div>
            <label class="settings-field wide">
                <span>Caption</span>
                <textarea data-action="schedule-caption" rows="3">${escapeHtml(caption)}</textarea>
            </label>
            <div class="schedule-toggles">
                <label class="toggle-row"><input type="checkbox" data-action="schedule-comment" ${schedule?.disable_comment ? "" : "checked"}><span>Allow comments</span></label>
                <label class="toggle-row"><input type="checkbox" data-action="schedule-duet" ${schedule?.disable_duet ? "" : "checked"}><span>Allow duet</span></label>
                <label class="toggle-row"><input type="checkbox" data-action="schedule-stitch" ${schedule?.disable_stitch ? "" : "checked"}><span>Allow stitch</span></label>
                <label class="toggle-row"><input type="checkbox" data-action="schedule-aigc" ${schedule?.is_aigc ? "checked" : ""}><span>AI-generated</span></label>
                <label class="toggle-row consent"><input type="checkbox" data-action="schedule-consent" ${schedule?.consent_confirmed ? "checked" : ""}><span>TikTok music usage consent</span></label>
            </div>
            <div class="library-actions schedule-actions">
                <button class="primary-button" type="button" data-action="save-schedule">Save schedule</button>
                <button class="ghost-button" type="button" data-action="copy-schedule-caption">Copy caption</button>
            </div>
        </div>
    `;
}

function defaultInputFromEpoch(epochSeconds) {
    const date = new Date(Number(epochSeconds || 0) * 1000);
    if (!Number.isFinite(date.getTime())) return defaultScheduleValue();
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16);
}

function collectSchedulePayload(container) {
    const action = container.querySelector('[data-action="schedule-action"]').value;
    const runAtEpoch = localDateTimeToEpoch(container.querySelector('[data-action="schedule-time"]').value);
    const privacy = container.querySelector('[data-action="schedule-privacy"]').value;
    const consent = container.querySelector('[data-action="schedule-consent"]').checked;
    if (!runAtEpoch) throw new Error("Choose a schedule time.");
    if (action === "direct" && !privacy) throw new Error("Choose privacy for Direct Post.");
    if (action === "direct" && !consent) throw new Error("Confirm TikTok music usage for Direct Post.");
    return {
        caption_text: cleanText(container.querySelector('[data-action="schedule-caption"]').value),
        schedule: {
            run_at_epoch: runAtEpoch,
            action,
            timezone_label: Intl.DateTimeFormat().resolvedOptions().timeZone || "local",
            privacy,
            disable_comment: !container.querySelector('[data-action="schedule-comment"]').checked,
            disable_duet: !container.querySelector('[data-action="schedule-duet"]').checked,
            disable_stitch: !container.querySelector('[data-action="schedule-stitch"]').checked,
            is_aigc: container.querySelector('[data-action="schedule-aigc"]').checked,
            consent_confirmed: consent,
        },
    };
}

async function copyScheduleCaption(container, statusEl) {
    try {
        const caption = container.querySelector('[data-action="schedule-caption"]').value;
        await navigator.clipboard.writeText(caption);
        setCardStatus(statusEl, "Caption copied.", "good");
    } catch (error) {
        setCardStatus(statusEl, "Copy failed.", "error");
    }
}

function setCardStatus(statusEl, message, type = "") {
    statusEl.textContent = message;
    statusEl.className = `status-message library-action-status ${type}`.trim();
}

function renderLibrary(videos) {
    els.libraryGrid.innerHTML = "";
    if (!videos.length) {
        els.libraryGrid.innerHTML = '<p class="status-message">No generated videos found.</p>';
        return;
    }

    videos.forEach((video) => {
        const card = document.createElement("article");
        card.className = "library-card";
        const title = escapeHtml(video.display_name || video.task_id);
        const created = relativeTime(video.created_at);
        const size = humanBytes(video.size_bytes);
        const publishStatus = video.publish_status || {};
        const tiktokStatus = publishStatus.tiktok || video.posted || {};
        const facebookStatus = publishStatus.facebook || video.facebook_posted || {};
        const statusLabel = escapeHtml(platformStatusLabel("tiktok", tiktokStatus) || libraryStatusLabel(video.posted));
        const statusClass = tiktokStatus && Object.keys(tiktokStatus).length ? "posted" : "pending";
        const fbLabel = platformStatusLabel("facebook", facebookStatus) || facebookStatusLabel(video.facebook_posted);
        const fbBadge = fbLabel ? `<span class="library-badge fb-badge">${escapeHtml(fbLabel)}</span>` : "";
        const activeSchedule = latestActiveSchedule(video);
        const scheduleBadge = activeSchedule
            ? `<span class="library-badge ${queueStatusClass(activeSchedule.status)}">${escapeHtml(scheduleSummary(activeSchedule))}</span>`
            : "";
        const caption = captionForVideo(video);
        card.innerHTML = `
            <video controls playsinline src="${escapeHtml(video.video_url || "")}"></video>
            <div class="library-card-body">
                <div class="library-card-title-row">
                    <h3>${title}</h3>
                    <span class="library-badge ${statusClass}">${statusLabel}</span>
                    ${fbBadge}
                    ${scheduleBadge}
                </div>
                <p>${escapeHtml(created)} · ${escapeHtml(size)}</p>
                <div class="library-actions">
                    <button class="ghost-button" type="button" data-action="inbox">TT draft</button>
                    <button class="ghost-button" type="button" data-action="publish">TT post</button>
                    <button class="ghost-button fb-button" type="button" data-action="publish-facebook">Post to FB</button>
                    <button class="ghost-button" type="button" data-action="reveal">Show in Finder</button>
                    <a class="ghost-button" href="${escapeHtml(video.video_url || "#")}" download="${escapeHtml(video.slug || "video")}.mp4">Download MP4</a>
                    <button class="ghost-button" type="button" data-action="copy">Copy caption</button>
                    <button class="ghost-button danger" type="button" data-action="delete">Delete</button>
                </div>
                <div class="library-regenerate">
                    <label class="settings-field">
                        <span>Voice</span>
                        <select data-action="voice">
                            <option value="">Auto</option>
                            <option value="male">Male</option>
                            <option value="female">Female</option>
                        </select>
                    </label>
                    <button class="primary-button" type="button" data-action="regenerate">Regenerate</button>
                </div>
                ${scheduleControlsHtml(caption, activeSchedule?.schedule || null)}
                <p class="status-message library-action-status"></p>
            </div>
        `;

        const statusEl = card.querySelector(".library-action-status");
        card.querySelector('[data-action="inbox"]').addEventListener("click", async () => {
            setCardStatus(statusEl, "Sending draft.");
            try {
                const { response, payload } = await fetchWithCreatorAccess("/api/v1/tiktok/upload-inbox", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ task_id: video.task_id }),
                });
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Inbox upload failed.");
                }
                setCardStatus(statusEl, "Draft sent.", "good");
                loadLibrary();
            } catch (error) {
                setCardStatus(statusEl, error.message || "Inbox upload failed.", "error");
            }
        });

        card.querySelector('[data-action="publish"]').addEventListener("click", async () => {
            setCardStatus(statusEl, "Publishing to TikTok.");
            try {
                const { response, payload } = await fetchWithCreatorAccess("/api/v1/tiktok/publish", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ task_id: video.task_id }),
                });
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Publish failed.");
                }
                setCardStatus(statusEl, "Posted to TikTok.", "good");
                loadLibrary();
            } catch (error) {
                setCardStatus(statusEl, error.message || "Publish failed.", "error");
            }
        });

        card.querySelector('[data-action="publish-facebook"]').addEventListener("click", async () => {
            setCardStatus(statusEl, "Uploading to Facebook. This can take a few minutes.");
            const btn = card.querySelector('[data-action="publish-facebook"]');
            btn.disabled = true;
            try {
                const response = await fetch("/api/v1/facebook/publish", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        task_id: video.task_id,
                        description: caption,
                        published: true,
                    }),
                });
                const payload = await response.json();
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Facebook publish failed.");
                }
                setCardStatus(statusEl, "Posted to Facebook.", "good");
                loadLibrary();
            } catch (error) {
                setCardStatus(statusEl, error.message || "Facebook publish failed.", "error");
            } finally {
                btn.disabled = false;
            }
        });

        card.querySelector('[data-action="copy"]').addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(caption);
                setCardStatus(statusEl, "Caption copied.", "good");
            } catch (error) {
                setCardStatus(statusEl, "Copy failed.", "error");
            }
        });

        card.querySelector('[data-action="reveal"]').addEventListener("click", () => {
            revealVideoFile(video.task_id, statusEl);
        });

        card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
            if (!window.confirm(`Delete ${video.display_name || video.task_id}?`)) return;
            setCardStatus(statusEl, "Deleting.");
            try {
                const response = await fetch(`/api/v1/creator/library/${encodeURIComponent(video.task_id)}`, {
                    method: "DELETE",
                });
                const payload = await response.json();
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Delete failed.");
                }
                card.remove();
                loadLibrary();
            } catch (error) {
                setCardStatus(statusEl, error.message || "Delete failed.", "error");
            }
        });

        card.querySelector('[data-action="regenerate"]').addEventListener("click", async () => {
            const voice = card.querySelector('[data-action="voice"]').value;
            setCardStatus(statusEl, "Regenerating.");
            try {
                const response = await fetch(`/api/v1/creator/library/${encodeURIComponent(video.task_id)}/regenerate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ narrator_gender: voice }),
                });
                const payload = await response.json();
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Regenerate failed.");
                }
                const taskId = payload.data.task_id;
                currentTaskId = taskId;
                els.publishTikTok.style.display = "none";
                els.uploadInboxTikTok.style.display = "none";
                els.publishFacebook.style.display = "none";
                hideManualUpload();
                els.taskStatus.textContent = `Task ${taskId}`;
                els.progressBar.style.width = "5%";
                setStatus("Regeneration task running.");
                setCardStatus(statusEl, "Regeneration started.", "good");
                pollTask(taskId);
                document.querySelector("#tasks")?.scrollIntoView({ behavior: "smooth", block: "start" });
            } catch (error) {
                setCardStatus(statusEl, error.message || "Regenerate failed.", "error");
            }
        });

        card.querySelector('[data-action="save-schedule"]').addEventListener("click", async () => {
            setCardStatus(statusEl, "Saving schedule.");
            try {
                const payloadBody = collectSchedulePayload(card);
                const { response, payload } = await fetchWithCreatorAccess(`/api/v1/creator/library/${encodeURIComponent(video.task_id)}/schedule`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payloadBody),
                });
                if (!response.ok || payload.status >= 400) {
                    throw new Error(payload.message || "Schedule failed.");
                }
                setCardStatus(statusEl, "Schedule saved.", "good");
                loadLibrary();
                loadQueue();
            } catch (error) {
                setCardStatus(statusEl, error.message || "Schedule failed.", "error");
            }
        });

        card.querySelector('[data-action="copy-schedule-caption"]').addEventListener("click", () => {
            copyScheduleCaption(card, statusEl);
        });

        els.libraryGrid.appendChild(card);
    });
}

async function loadLibrary() {
    if (!els.libraryGrid) return;
    els.libraryGrid.innerHTML = '<p class="status-message">Loading videos.</p>';
    try {
        const response = await fetch("/api/v1/creator/library", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Could not load library.");
        }
        const data = payload.data || {};
        const videos = data.videos || [];
        els.libraryUsage.textContent = `${videos.length} video${videos.length === 1 ? "" : "s"} · ${humanBytes(data.total_size_bytes)}`;
        renderLibrary(videos);
    } catch (error) {
        els.libraryUsage.textContent = "Library unavailable";
        els.libraryGrid.innerHTML = `<p class="status-message error">${escapeHtml(error.message || "Could not load library.")}</p>`;
    }
}

async function cleanupLibrary() {
    const days = Math.max(1, Number(els.cleanupDays.value || 7));
    if (!window.confirm(`Delete unposted videos older than ${days} day${days === 1 ? "" : "s"}?`)) {
        return;
    }
    els.cleanupBtn.disabled = true;
    els.cleanupBtn.textContent = "Deleting...";
    try {
        const response = await fetch("/api/v1/creator/library/cleanup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ older_than_days: days, dry_run: false }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Cleanup failed.");
        }
        const data = payload.data || {};
        setStatus(`Deleted ${data.deleted.length} videos and freed ${humanBytes(data.freed_bytes)}.`, "good");
        loadLibrary();
    } catch (error) {
        setStatus(error.message || "Cleanup failed.", "error");
    } finally {
        els.cleanupBtn.disabled = false;
        els.cleanupBtn.textContent = "Delete unposted";
    }
}

function setQueueStatus(message, type = "") {
    els.queueStatus.textContent = message;
    els.queueStatus.className = `status-message ${type}`.trim();
}

function queueStatusClass(status) {
    if (["rendered", "sent"].includes(status)) return "posted";
    if (["failed", "canceled"].includes(status)) return "failed";
    if (["rendering", "dispatching", "scheduled"].includes(status)) return "scheduled";
    return "pending";
}

function renderQueue(items, processingEnabled) {
    els.queueSummary.textContent = `${items.length} item${items.length === 1 ? "" : "s"} · ${processingEnabled ? "running" : "paused"}`;
    if (els.clearFinishedQueue) {
        els.clearFinishedQueue.disabled = !items.some((item) =>
            ["rendered", "sent", "failed", "canceled"].includes(item.status)
        );
    }
    els.queueList.innerHTML = "";
    if (!items.length) {
        els.queueList.innerHTML = '<p class="status-message">No queued stories.</p>';
        return;
    }

    items.forEach((item, index) => {
        const card = document.createElement("article");
        card.className = "queue-card";
        const title = item.story?.comment_card_title || item.story?.video_subject || item.queue_id;
        const caption = item.caption_text || captionForStory(item.story || {});
        const status = item.status || "queued";
        const scheduleText = scheduleSummary(item);
        const rendered = ["rendered", "scheduled", "dispatching", "sent", "failed"].includes(status) && item.task_id;
        card.innerHTML = `
            <div class="queue-card-main">
                <div>
                    <div class="library-card-title-row">
                        <h3>${escapeHtml(item.position)}. ${escapeHtml(title)}</h3>
                        <span class="library-badge ${queueStatusClass(status)}">${escapeHtml(status)}</span>
                    </div>
                    <p>${escapeHtml(caption || "No caption")}</p>
                    ${item.task_id ? `<p>Task ${escapeHtml(item.task_id)}${scheduleText ? ` · ${escapeHtml(scheduleText)}` : ""}</p>` : ""}
                    ${item.error ? `<p class="status-message error">${escapeHtml(item.error)}</p>` : ""}
                </div>
                <div class="library-actions queue-actions">
                    <button class="ghost-button" type="button" data-action="load-story">Load</button>
                    <button class="ghost-button" type="button" data-action="move-up" ${index === 0 ? "disabled" : ""}>Up</button>
                    <button class="ghost-button" type="button" data-action="move-down" ${index === items.length - 1 ? "disabled" : ""}>Down</button>
                    ${rendered ? '<button class="ghost-button" type="button" data-action="reveal-queue">Show in Finder</button>' : ""}
                    ${["queued", "rendering"].includes(status) ? `<button class="ghost-button danger" type="button" data-action="cancel-queue">Cancel</button>` : ""}
                    <button class="ghost-button danger" type="button" data-action="delete-queue">Remove</button>
                </div>
            </div>
            ${rendered ? scheduleControlsHtml(caption, item.schedule) : ""}
            <p class="status-message library-action-status"></p>
        `;
        const statusEl = card.querySelector(".library-action-status");

        card.querySelector('[data-action="load-story"]').addEventListener("click", () => {
            fillFromStory(item.story || {});
            document.querySelector("#story")?.scrollIntoView({ behavior: "smooth", block: "start" });
            setQueueStatus("Story loaded into editor.", "good");
        });

        card.querySelector('[data-action="move-up"]')?.addEventListener("click", async () => {
            await updateQueuePosition(item.queue_id, item.position - 1);
        });
        card.querySelector('[data-action="move-down"]')?.addEventListener("click", async () => {
            await updateQueuePosition(item.queue_id, item.position + 1);
        });
        card.querySelector('[data-action="cancel-queue"]')?.addEventListener("click", async () => {
            if (!window.confirm(`Cancel ${title}?`)) return;
            try {
                const response = await fetch(`/api/v1/creator/queue/${encodeURIComponent(item.queue_id)}/cancel`, { method: "POST" });
                const payload = await response.json();
                if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Cancel failed.");
                setQueueStatus("Queue item canceled.", "good");
                loadQueue();
            } catch (error) {
                setQueueStatus(error.message || "Cancel failed.", "error");
            }
        });

        card.querySelector('[data-action="delete-queue"]').addEventListener("click", async () => {
            if (!window.confirm(`Remove ${title}?`)) return;
            try {
                const response = await fetch(`/api/v1/creator/queue/${encodeURIComponent(item.queue_id)}`, { method: "DELETE" });
                const payload = await response.json();
                if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Remove failed.");
                setQueueStatus("Queue item removed.", "good");
                loadQueue();
            } catch (error) {
                setQueueStatus(error.message || "Remove failed.", "error");
            }
        });

        card.querySelector('[data-action="reveal-queue"]')?.addEventListener("click", () => {
            revealVideoFile(item.task_id, statusEl);
        });

        const saveSchedule = card.querySelector('[data-action="save-schedule"]');
        if (saveSchedule) {
            saveSchedule.addEventListener("click", async () => {
                setCardStatus(statusEl, "Saving schedule.");
                try {
                    const payloadBody = collectSchedulePayload(card);
                    const { response, payload } = await fetchWithCreatorAccess(`/api/v1/creator/queue/${encodeURIComponent(item.queue_id)}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payloadBody),
                    });
                    if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Schedule failed.");
                    setCardStatus(statusEl, "Schedule saved.", "good");
                    loadQueue();
                } catch (error) {
                    setCardStatus(statusEl, error.message || "Schedule failed.", "error");
                }
            });
            card.querySelector('[data-action="copy-schedule-caption"]').addEventListener("click", () => {
                copyScheduleCaption(card, statusEl);
            });
        }

        els.queueList.appendChild(card);
    });
}

async function updateQueuePosition(queueId, position) {
    try {
        const response = await fetch(`/api/v1/creator/queue/${encodeURIComponent(queueId)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Reorder failed.");
        loadQueue();
    } catch (error) {
        setQueueStatus(error.message || "Reorder failed.", "error");
    }
}

async function loadQueue() {
    if (!els.queueList) return;
    try {
        const response = await fetch("/api/v1/creator/queue", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Could not load queue.");
        const data = payload.data || {};
        const items = data.items || [];
        renderQueue(items, data.processing_enabled);
        const active = data.processing_enabled || items.some((item) => ["rendering", "scheduled", "dispatching"].includes(item.status));
        startQueuePolling(active);
    } catch (error) {
        els.queueSummary.textContent = "Queue unavailable";
        els.queueList.innerHTML = `<p class="status-message error">${escapeHtml(error.message || "Could not load queue.")}</p>`;
    }
}

function startQueuePolling(active) {
    window.clearInterval(queueTimer);
    if (active) {
        queueTimer = window.setInterval(loadQueue, 8000);
    }
}

async function importQueue() {
    const rawJson = els.queueJsonInput.value.trim();
    if (!rawJson) {
        setQueueStatus("Paste queue JSON first.", "error");
        return;
    }
    els.importQueue.disabled = true;
    try {
        const count = await importRawJsonToQueue(rawJson);
        setQueueStatus(`Imported ${count} queued ${count === 1 ? "story" : "stories"}.`, "good");
        els.queueJsonInput.value = "";
        loadQueue();
    } catch (error) {
        setQueueStatus(error.message || "Queue import failed.", "error");
    } finally {
        els.importQueue.disabled = false;
    }
}

async function importRawJsonToQueue(rawJson) {
    const response = await fetch("/api/v1/creator/queue/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_json: rawJson }),
    });
    const payload = await response.json();
    if (!response.ok || payload.status >= 400) {
        throw new Error(payload.message || "Queue import failed.");
    }
    return (payload.data?.items || []).length;
}

async function setQueueProcessing(enabled) {
    const button = enabled ? els.startQueue : els.pauseQueue;
    button.disabled = true;
    try {
        const response = await fetch("/api/v1/creator/queue/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Queue update failed.");
        setQueueStatus(enabled ? "Queue rendering started." : "Queue paused.", "good");
        loadQueue();
    } catch (error) {
        setQueueStatus(error.message || "Queue update failed.", "error");
    } finally {
        button.disabled = false;
    }
}

async function clearFinishedQueue() {
    if (!window.confirm("Clear finished queue items?")) return;
    els.clearFinishedQueue.disabled = true;
    try {
        const response = await fetch("/api/v1/creator/queue/finished", {
            method: "DELETE",
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) throw new Error(payload.message || "Clear failed.");
        const deleted = Number(payload.data?.deleted || 0);
        setQueueStatus(`Cleared ${deleted} finished ${deleted === 1 ? "item" : "items"}.`, "good");
        loadQueue();
    } catch (error) {
        setQueueStatus(error.message || "Clear failed.", "error");
    } finally {
        els.clearFinishedQueue.disabled = false;
    }
}

function setConnectionState(state, message) {
    els.connectionPill.textContent = message;
    els.connectionPill.className = `connection-pill ${state}`;
}

async function checkConnection() {
    try {
        const response = await fetch("/api/v1/creator/status", { cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "status unavailable");
        }

        const data = payload.data || {};
        if (data.webserver_connected && data.bot_connected) {
            setConnectionState("connected", "Bot connected");
            els.backendCheck.textContent = "Connected";
            els.backendCheck.className = "good";
        } else if (data.webserver_connected) {
            setConnectionState("disconnected", "Bot not ready");
            els.backendCheck.textContent = "Bot not ready";
            els.backendCheck.className = "bad";
        } else {
            setConnectionState("disconnected", "Webserver offline");
            els.backendCheck.textContent = "Offline";
            els.backendCheck.className = "bad";
        }
    } catch (error) {
        setConnectionState("disconnected", "Webserver offline");
        els.backendCheck.textContent = "Offline";
        els.backendCheck.className = "bad";
    }
}

function startConnectionMonitor() {
    window.clearInterval(connectionTimer);
    setConnectionState("checking", "Checking connection");
    checkConnection();
    connectionTimer = window.setInterval(checkConnection, 10000);
}

async function copyPrompt() {
    const prompt = els.ideaPrompt.value || fallbackPrompt;
    try {
        await navigator.clipboard.writeText(prompt);
        setStatus("Idea prompt copied.", "good");
    } catch (error) {
        els.ideaPrompt.focus();
        els.ideaPrompt.select();
        setStatus("Prompt selected. Use your copy shortcut.", "");
    }
}

async function loadPrompt() {
    try {
        const response = await fetch("/api/v1/creator/idea-prompt");
        const payload = await response.json();
        els.ideaPrompt.value = payload?.data?.prompt || fallbackPrompt;
    } catch (error) {
        els.ideaPrompt.value = fallbackPrompt;
    }
}

async function importJson() {
    const rawJson = els.jsonInput.value.trim();
    if (!rawJson) {
        setStatus("Paste JSON first.", "error");
        return;
    }

    try {
        if (looksLikeQueueImport(rawJson)) {
            const count = await importRawJsonToQueue(rawJson);
            els.jsonInput.value = "";
            setStatus(`Imported ${count} ${count === 1 ? "story" : "stories"} into the queue.`, "good");
            setQueueStatus(`Imported ${count} queued ${count === 1 ? "story" : "stories"}.`, "good");
            loadQueue();
            document.querySelector("#queue")?.scrollIntoView({ behavior: "smooth", block: "start" });
            return;
        }
        const response = await fetch("/api/v1/creator/import-chatgpt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ raw_json: rawJson }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Could not import JSON.");
        }
        fillFromStory(payload.data.story);
        switchTab("write");
        setStatus("Story imported.", "good");
    } catch (error) {
        setStatus(error.message || "Could not import JSON.", "error");
    }
}

function looksLikeQueueImport(rawJson) {
    const text = rawJson.trim();
    return text.startsWith("[") || /}\s*{/.test(text);
}

async function generateVideo() {
    const story = collectStory();
    const seconds = estimateSeconds(story.narration_script);
    if (!story.narration_script) {
        setStatus("Add a narration script first.", "error");
        return;
    }
    const minSeconds = minSecondsForLane(story.length_lane);
    if (seconds < minSeconds) {
        setStatus(`Script is ${seconds}s. Add more story before generating.`, "error");
        return;
    }

    setGenerating(true);
    setStatus("Submitting video task.");
    els.taskStatus.textContent = "Submitting task";

    try {
        const response = await fetch("/api/v1/creator/videos", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(story),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Video task failed to start.");
        }
        const taskId = payload.data.task_id;
        currentTaskId = taskId;
        els.publishTikTok.style.display = "none";
        els.uploadInboxTikTok.style.display = "none";
        els.publishFacebook.style.display = "none";
        hideManualUpload();
        setPublishStatus("");
        els.taskStatus.textContent = `Task ${taskId}`;
        els.progressBar.style.width = "5%";
        setStatus("Video task running.");
        pollTask(taskId);
    } catch (error) {
        setGenerating(false);
        els.taskStatus.textContent = "Task failed to start";
        setStatus(error.message || "Video task failed to start.", "error");
    }
}

function setGenerating(isGenerating) {
    document.querySelectorAll("#generateTop, #generateMain").forEach((button) => {
        button.disabled = isGenerating;
        button.textContent = isGenerating ? "Generating..." : "Generate Video";
    });
    if (els.cancelTask) {
        els.cancelTask.style.display = isGenerating ? "inline-flex" : "none";
        els.cancelTask.disabled = false;
    }
}

async function cancelCurrentTask() {
    if (!currentTaskId) return;
    if (els.cancelTask) els.cancelTask.disabled = true;
    els.taskStatus.textContent = "Canceling...";
    setStatus("Canceling video.");
    try {
        const response = await fetch(`/api/v1/creator/videos/${encodeURIComponent(currentTaskId)}/cancel`, {
            method: "POST",
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Cancel failed.");
        }
    } catch (error) {
        if (els.cancelTask) els.cancelTask.disabled = false;
        setStatus(error.message || "Cancel failed.", "error");
    }
}

function pollTask(taskId) {
    window.clearInterval(pollTimer);
    pollTimer = window.setInterval(async () => {
        try {
            const response = await fetch(`/api/v1/tasks/${taskId}`);
            const payload = await response.json();
            if (!response.ok || payload.status >= 400) {
                throw new Error(payload.message || "Task status unavailable.");
            }
            const task = payload.data;
            const progress = Number(task.progress || 0);
            els.progressBar.style.width = `${Math.max(5, progress)}%`;

            if (task.state === 1) {
                window.clearInterval(pollTimer);
                setGenerating(false);
                els.taskStatus.textContent = "Video complete";
                setStatus("Video complete.", "good");
                showOutput(task.videos && task.videos[0]);
                els.publishTikTok.style.display = "block";
                els.uploadInboxTikTok.style.display = "block";
                if (facebookConnected) els.publishFacebook.style.display = "block";
                loadLibrary();
            } else if (task.state === -1) {
                window.clearInterval(pollTimer);
                setGenerating(false);
                els.taskStatus.textContent = "Task failed";
                setStatus("Video generation failed.", "error");
            } else if (task.state === -2) {
                window.clearInterval(pollTimer);
                setGenerating(false);
                els.taskStatus.textContent = "Video canceled";
                setStatus("Video canceled.", "good");
            } else {
                els.taskStatus.textContent = `Running: ${progress}%`;
            }
        } catch (error) {
            window.clearInterval(pollTimer);
            setGenerating(false);
            els.taskStatus.textContent = "Task polling failed";
            setStatus(error.message || "Could not poll task.", "error");
        }
    }, 2500);
}

function showOutput(videoUrl) {
    if (!videoUrl) return;
    els.outputVideo.src = videoUrl;
    els.outputVideo.style.display = "block";
    els.downloadLink.style.display = "inline-flex";
    showManualUpload(videoUrl);
}

function setPublishStatus(message, type = "") {
    els.publishStatus.textContent = message;
    els.publishStatus.className = `status-message ${type}`.trim();
}

function setTikTokPill(state, message, href) {
    els.tiktokPill.textContent = message;
    els.tiktokPill.className = `connection-pill ${state}`;
    els.tiktokPill.dataset.action = state === "locked" ? "unlock" : "";
    if (href) {
        els.tiktokPill.href = href;
        els.tiktokPill.style.pointerEvents = "auto";
    } else {
        els.tiktokPill.href = "#";
        els.tiktokPill.style.pointerEvents = state === "connected" ? "none" : "auto";
    }
}

function privacyLabel(value) {
    const labels = {
        PUBLIC_TO_EVERYONE: "Public",
        MUTUAL_FOLLOW_FRIENDS: "Friends",
        FOLLOWER_OF_CREATOR: "Followers",
        SELF_ONLY: "Only me",
    };
    return labels[value] || value.replace(/_/g, " ").toLowerCase();
}

function setInteractionControl(input, disabledByTikTok) {
    input.disabled = Boolean(disabledByTikTok);
    if (input.disabled) input.checked = false;
}

function updateTikTokPublishSettings(data) {
    tiktokCreatorInfo = data.creator_info || {};
    const options = Array.isArray(tiktokCreatorInfo.privacy_level_options)
        ? tiktokCreatorInfo.privacy_level_options
        : [];
    const privacyOptions = options.length ? options : [data.privacy_level || "SELF_ONLY"];
    const previousPrivacy = els.tiktokPrivacy.value;

    els.tiktokPrivacy.innerHTML = '<option value="">Choose privacy</option>';
    privacyOptions.forEach((privacy) => {
        if (!privacy) return;
        const option = document.createElement("option");
        option.value = privacy;
        option.textContent = privacyLabel(privacy);
        els.tiktokPrivacy.appendChild(option);
    });
    if (privacyOptions.includes(previousPrivacy)) {
        els.tiktokPrivacy.value = previousPrivacy;
    }

    setInteractionControl(els.allowComment, tiktokCreatorInfo.comment_disabled);
    setInteractionControl(els.allowDuet, tiktokCreatorInfo.duet_disabled);
    setInteractionControl(els.allowStitch, tiktokCreatorInfo.stitch_disabled);
}

async function checkTikTokStatus() {
    try {
        const { response, payload } = await fetchWithCreatorAccess(
            "/api/v1/tiktok/status",
            { cache: "no-store" },
            false
        );
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "status unavailable");
        }
        const data = payload.data || {};
        if (!data.configured) {
            setTikTokPill("disconnected", "TikTok: not set up", null);
            updateTikTokPublishSettings({ privacy_level: "SELF_ONLY" });
            return;
        }
        updateTikTokPublishSettings(data);
        if (data.locked) {
            setTikTokPill("locked", "TikTok: unlock", null);
            return;
        }
        if (data.connected) {
            setTikTokPill("connected", `TikTok: ${data.nickname || "connected"}`, null);
            return;
        }
        let authUrl = "#";
        try {
            const { response: authResponse, payload: authPayload } =
                await fetchWithCreatorAccess("/api/v1/tiktok/auth-url");
            if (!authResponse.ok || authPayload.status >= 400) {
                throw new Error(authPayload.message || "auth unavailable");
            }
            authUrl = authPayload?.data?.auth_url || "#";
        } catch (error) {
            authUrl = "#";
        }
        setTikTokPill("disconnected", "TikTok: connect", authUrl);
    } catch (error) {
        setTikTokPill("disconnected", "TikTok: offline", null);
    }
}

function startTikTokMonitor() {
    window.clearInterval(tiktokTimer);
    setTikTokPill("checking", "TikTok: checking", null);
    checkTikTokStatus();
    tiktokTimer = window.setInterval(checkTikTokStatus, 15000);
}

function setFacebookPill(state, message) {
    els.facebookPill.textContent = message;
    els.facebookPill.className = `connection-pill ${state}`;
}

async function checkFacebookStatus() {
    try {
        const response = await fetch("/api/v1/facebook/status", { cache: "no-store" });
        const payload = await response.json();
        const data = payload.data || {};
        facebookConnected = Boolean(data.connected);
        if (facebookConnected) {
            const name = data.page_name || "connected";
            setFacebookPill("connected", `FB: ${name}`);
        } else {
            setFacebookPill("disconnected", "FB: not connected");
        }
    } catch (error) {
        facebookConnected = false;
        setFacebookPill("disconnected", "FB: offline");
    }
}

function startFacebookMonitor() {
    window.clearInterval(facebookTimer);
    setFacebookPill("checking", "FB: checking");
    checkFacebookStatus();
    facebookTimer = window.setInterval(checkFacebookStatus, 30000);
}

async function publishToFacebook() {
    if (!currentTaskId) {
        setPublishStatus("Generate a video first.", "error");
        return;
    }
    const story = collectStory();
    const description = [
        story.suggested_description || story.comment_card_title || story.video_subject,
        (story.suggested_hashtags || []).join(" "),
    ].filter(Boolean).join(" ");

    els.publishFacebook.disabled = true;
    els.publishFacebook.textContent = "Uploading to Facebook...";
    setPublishStatus("Uploading to Facebook. This can take a few minutes for large videos.");

    try {
        const response = await fetch("/api/v1/facebook/publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                task_id: currentTaskId,
                description: description,
                published: true,
            }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Facebook publish failed.");
        }
        setPublishStatus("Posted to Facebook.", "good");
        loadLibrary();
    } catch (error) {
        setPublishStatus(error.message || "Facebook publish failed.", "error");
    } finally {
        els.publishFacebook.disabled = false;
        els.publishFacebook.textContent = "Post to Facebook Page";
    }
}

async function publishToTikTok() {
    if (!currentTaskId) {
        setPublishStatus("Generate a video first.", "error");
        return;
    }
    const story = collectStory();
    const maxDuration = Number(tiktokCreatorInfo.max_video_post_duration_sec || 0);
    const estimatedDuration = estimateSeconds(story.narration_script);
    if (!els.tiktokPrivacy.value) {
        setPublishStatus("Choose a TikTok privacy setting first.", "error");
        return;
    }
    if (!els.tiktokConsent.checked) {
        setPublishStatus("Confirm TikTok music usage before posting.", "error");
        return;
    }
    if (maxDuration > 0 && estimatedDuration > maxDuration) {
        setPublishStatus(`TikTok allows up to ${maxDuration}s for this account.`, "error");
        return;
    }
    els.publishTikTok.disabled = true;
    els.publishTikTok.textContent = "Publishing...";
    setPublishStatus("Uploading to TikTok. This can take a minute.");

    try {
        const { response, payload } = await fetchWithCreatorAccess("/api/v1/tiktok/publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                task_id: currentTaskId,
                description: story.suggested_description || story.comment_card_title || story.video_subject,
                hashtags: story.suggested_hashtags,
                privacy: els.tiktokPrivacy.value,
                disable_comment: !els.allowComment.checked,
                disable_duet: !els.allowDuet.checked,
                disable_stitch: !els.allowStitch.checked,
                brand_content_toggle: false,
                brand_organic_toggle: false,
                is_aigc: els.tiktokAigc.checked,
            }),
        });
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Publish failed.");
        }
        const data = payload.data || {};
        setPublishStatus(`TikTok: ${data.status || "submitted"}.`, "good");
        loadLibrary();
    } catch (error) {
        setPublishStatus(error.message || "Publish failed.", "error");
    } finally {
        els.publishTikTok.disabled = false;
        els.publishTikTok.textContent = "Publish to TikTok (Direct Post)";
    }
}

async function uploadToTikTokInbox() {
    if (!currentTaskId) {
        setPublishStatus("Generate a video first.", "error");
        return;
    }
    els.uploadInboxTikTok.disabled = true;
    els.uploadInboxTikTok.textContent = "Sending...";
    setPublishStatus("Uploading draft to your TikTok inbox. This can take a minute.");

    try {
        const { response, payload } = await fetchWithCreatorAccess("/api/v1/tiktok/upload-inbox", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: currentTaskId }),
        });
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Inbox upload failed.");
        }
        const data = payload.data || {};
        setPublishStatus(
            `TikTok inbox: ${data.status || "submitted"}. Open TikTok notifications to finish the post.`,
            "good"
        );
        loadLibrary();
    } catch (error) {
        setPublishStatus(error.message || "Inbox upload failed.", "error");
    } finally {
        els.uploadInboxTikTok.disabled = false;
        els.uploadInboxTikTok.textContent = "Send to TikTok inbox (draft)";
    }
}

function switchTab(tabName) {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.panel === tabName);
    });
}

function bindEvents() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach((nav) => nav.classList.remove("active"));
            item.classList.add("active");
            const target = document.querySelector(`#${item.dataset.section}`);
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
            if (item.dataset.section === "library") loadLibrary();
            if (item.dataset.section === "queue") loadQueue();
        });
    });

    [
        els.storyText,
        els.cardTitle,
        els.cardUsername,
        els.cardLikes,
        els.narratorGender,
        els.highlightInput,
        els.sourceUrl,
        els.subreddit,
        els.hashtags,
        els.contentNotes,
    ].forEach((input) => {
        const handler = () => {
            if (input === els.storyText && !els.cardTitle.value.trim()) {
                els.cardTitle.value = deriveTitle(input.value);
            }
            updateAll();
            scheduleSave();
        };
        input.addEventListener("input", handler);
        if (input.tagName === "SELECT") input.addEventListener("change", handler);
    });

    document.querySelector("#importJson").addEventListener("click", importJson);
    document.querySelector("#clearJson").addEventListener("click", () => {
        els.jsonInput.value = "";
        setStatus("");
    });
    document.querySelector("#copyPrompt").addEventListener("click", copyPrompt);
    document.querySelector("#copyPromptTop").addEventListener("click", copyPrompt);
    document.querySelector("#generateTop").addEventListener("click", generateVideo);
    document.querySelector("#generateMain").addEventListener("click", generateVideo);
    els.cancelTask.addEventListener("click", cancelCurrentTask);
    els.importQueue.addEventListener("click", importQueue);
    els.clearQueueJson.addEventListener("click", () => {
        els.queueJsonInput.value = "";
        setQueueStatus("");
    });
    els.clearFinishedQueue.addEventListener("click", clearFinishedQueue);
    els.startQueue.addEventListener("click", () => setQueueProcessing(true));
    els.pauseQueue.addEventListener("click", () => setQueueProcessing(false));
    els.refreshQueue.addEventListener("click", loadQueue);
    els.refreshLibrary.addEventListener("click", loadLibrary);
    els.cleanupBtn.addEventListener("click", cleanupLibrary);
    els.copyManualCaption.addEventListener("click", copyManualCaption);
    els.downloadLink.addEventListener("click", () => revealVideoFile(currentTaskId));
    els.manualRevealFile.addEventListener("click", () => revealVideoFile(currentTaskId));
    els.publishTikTok.addEventListener("click", publishToTikTok);
    els.uploadInboxTikTok.addEventListener("click", uploadToTikTokInbox);
    els.publishFacebook.addEventListener("click", publishToFacebook);
    els.tiktokPill.addEventListener("click", (event) => {
        if (els.tiktokPill.getAttribute("href") === "#") event.preventDefault();
        if (els.tiktokPill.dataset.action === "unlock" && promptCreatorAccessKey()) {
            checkTikTokStatus();
        }
    });
}

loadPrompt();
bindEvents();
restoreDraft();
updateAll();
startConnectionMonitor();
startTikTokMonitor();
startFacebookMonitor();
loadQueue();
