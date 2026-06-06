const MIN_SECONDS = 60;
const WORDS_PER_MINUTE = 165;
const STORAGE_KEY = "jc-video-factory-draft-v1";

const fallbackPrompt = `Browse Reddit for a strong short-form story suitable for a faceless TikTok/Reels video.

Target style:
- AITA, relationship drama, entitled people, workplace drama, family conflict, travel/airplane conflict, or roommate conflict
- Clear conflict in the first 2 seconds
- Strong moral dilemma or rage-bait hook
- 60-75 seconds when read aloud
- First-person narration
- Easy to understand without Reddit context
- Safe for monetized short-form content

Rules:
- Use only public Reddit posts.
- Do not include real names, usernames, locations, workplaces, or identifying details.
- Do not invent a Reddit source URL. If you cannot verify a source, say so.
- Paraphrase the story into a clean narration script instead of copying the post word-for-word.
- Keep the emotional conflict, but remove rambling, edits, updates, and unnecessary details.
- Make it sound natural when spoken by TTS.
- End with a question that invites comments.

Return ONLY this JSON:

{
  "source_url": "",
  "subreddit": "",
  "original_title": "",
  "comment_card_username": "u/throwaway_aita",
  "comment_card_title": "",
  "comment_card_likes": "99+",
  "video_subject": "",
  "narration_script": "",
  "caption_keywords_to_highlight": [],
  "suggested_hook": "",
  "suggested_description": "",
  "suggested_hashtags": [],
  "content_notes": ""
}

Field rules:
- comment_card_title: max 120 characters, written like a Reddit post title.
- narration_script: 170-230 words, first person, no markdown, no bullet points.
- caption_keywords_to_highlight: 8-15 short words or phrases that should be red-highlighted in captions.
- suggested_hook: one short sentence for the first 2 seconds.
- suggested_description: TikTok/Reels caption, max 150 characters.
- suggested_hashtags: 5-8 hashtags.
- content_notes: mention if anything was softened, anonymized, or potentially sensitive.`;

const sampleStory = `AITA for refusing to give up the window seat I paid extra for? I booked a window seat months before my flight because I get motion sick if I cannot look outside. I also paid extra for it, because the airline made that seat an upgrade. When I boarded, a mom and her son were already in my row. She had the middle and aisle seats, and she asked if I would switch so her son could have the window. I said I was sorry, but I needed the seat I paid for because I get sick. She rolled her eyes and said he was only eight and had been excited all week. I still said no. The whole row stared at me while she made passive aggressive comments about people having no kindness anymore. Her son cried a little, and I felt awful, but I stayed in my seat. My girlfriend says I technically did nothing wrong, but I could have been nicer. So am I the asshole?`;

const els = {
    storyText: document.querySelector("#storyText"),
    jsonInput: document.querySelector("#jsonInput"),
    ideaPrompt: document.querySelector("#ideaPrompt"),
    cardTitle: document.querySelector("#cardTitle"),
    cardUsername: document.querySelector("#cardUsername"),
    cardLikes: document.querySelector("#cardLikes"),
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
    progressBar: document.querySelector("#progressBar"),
    outputVideo: document.querySelector("#outputVideo"),
    downloadLink: document.querySelector("#downloadLink"),
    tiktokPill: document.querySelector("#tiktokPill"),
    publishTikTok: document.querySelector("#publishTikTok"),
    uploadInboxTikTok: document.querySelector("#uploadInboxTikTok"),
    publishStatus: document.querySelector("#publishStatus"),
    publishSettings: document.querySelector("#publishSettings"),
    tiktokPrivacy: document.querySelector("#tiktokPrivacy"),
    allowComment: document.querySelector("#allowComment"),
    allowDuet: document.querySelector("#allowDuet"),
    allowStitch: document.querySelector("#allowStitch"),
    tiktokAigc: document.querySelector("#tiktokAigc"),
    tiktokConsent: document.querySelector("#tiktokConsent"),
};

let pollTimer = null;
let saveTimer = null;
let connectionTimer = null;
let tiktokTimer = null;
let currentTaskId = null;
let tiktokCreatorInfo = {};

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
        comment_card_username: cleanText(els.cardUsername.value) || "u/throwaway_aita",
        comment_card_title: title,
        comment_card_likes: cleanText(els.cardLikes.value) || "99+",
        video_subject: title || "AITA story",
        narration_script: script,
        caption_keywords_to_highlight: highlights,
        suggested_hook: "",
        suggested_description: "",
        suggested_hashtags: hashtagsFromInput(els.hashtags.value),
        content_notes: cleanText(els.contentNotes.value),
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
    updateAll();
    scheduleSave();
}

function updateAll() {
    const story = collectStory();
    const wordCount = words(story.narration_script).length;
    const seconds = estimateSeconds(story.narration_script);
    const highlights = story.caption_keywords_to_highlight;
    const meetsMinimum = seconds >= MIN_SECONDS;
    const hasTitle = Boolean(story.comment_card_title);

    els.wordCount.textContent = String(wordCount);
    els.estimatedDuration.textContent = `${seconds}s`;
    els.highlightCount.textContent = String(highlights.length);
    els.validationLabel.textContent = meetsMinimum && hasTitle ? "Ready" : "Draft";

    els.durationStatus.textContent = meetsMinimum ? `${seconds}s ready` : `${seconds}s / ${MIN_SECONDS}s min`;
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

async function generateVideo() {
    const story = collectStory();
    const seconds = estimateSeconds(story.narration_script);
    if (!story.narration_script) {
        setStatus("Add a narration script first.", "error");
        return;
    }
    if (seconds < MIN_SECONDS) {
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
            } else if (task.state === -1) {
                window.clearInterval(pollTimer);
                setGenerating(false);
                els.taskStatus.textContent = "Task failed";
                setStatus("Video generation failed.", "error");
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
    els.downloadLink.href = videoUrl;
    els.downloadLink.style.display = "inline-block";
}

function setPublishStatus(message, type = "") {
    els.publishStatus.textContent = message;
    els.publishStatus.className = `status-message ${type}`.trim();
}

function setTikTokPill(state, message, href) {
    els.tiktokPill.textContent = message;
    els.tiktokPill.className = `connection-pill ${state}`;
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
        const response = await fetch("/api/v1/tiktok/status", { cache: "no-store" });
        const payload = await response.json();
        const data = payload.data || {};
        if (!data.configured) {
            setTikTokPill("disconnected", "TikTok: not set up", null);
            updateTikTokPublishSettings({ privacy_level: "SELF_ONLY" });
            return;
        }
        updateTikTokPublishSettings(data);
        if (data.connected) {
            setTikTokPill("connected", `TikTok: ${data.nickname || "connected"}`, null);
            return;
        }
        let authUrl = "#";
        try {
            const authResponse = await fetch("/api/v1/tiktok/auth-url");
            const authPayload = await authResponse.json();
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
        const response = await fetch("/api/v1/tiktok/publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                task_id: currentTaskId,
                description: story.comment_card_title || story.video_subject,
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
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Publish failed.");
        }
        const data = payload.data || {};
        setPublishStatus(`TikTok: ${data.status || "submitted"}.`, "good");
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
        const response = await fetch("/api/v1/tiktok/upload-inbox", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_id: currentTaskId }),
        });
        const payload = await response.json();
        if (!response.ok || payload.status >= 400) {
            throw new Error(payload.message || "Inbox upload failed.");
        }
        const data = payload.data || {};
        setPublishStatus(
            `TikTok inbox: ${data.status || "submitted"}. Open TikTok notifications to finish the post.`,
            "good"
        );
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
        });
    });

    [
        els.storyText,
        els.cardTitle,
        els.cardUsername,
        els.cardLikes,
        els.highlightInput,
        els.sourceUrl,
        els.subreddit,
        els.hashtags,
        els.contentNotes,
    ].forEach((input) => {
        input.addEventListener("input", () => {
            if (input === els.storyText && !els.cardTitle.value.trim()) {
                els.cardTitle.value = deriveTitle(input.value);
            }
            updateAll();
            scheduleSave();
        });
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
    els.publishTikTok.addEventListener("click", publishToTikTok);
    els.uploadInboxTikTok.addEventListener("click", uploadToTikTokInbox);
    els.tiktokPill.addEventListener("click", (event) => {
        if (els.tiktokPill.getAttribute("href") === "#") event.preventDefault();
    });
}

loadPrompt();
bindEvents();
restoreDraft();
updateAll();
startConnectionMonitor();
startTikTokMonitor();
