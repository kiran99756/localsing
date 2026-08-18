/* ===========================================================
   0) PWA - register the service worker so Chrome/Android treats
      this as an installable app (Add to Home Screen). Requires
      a secure context (HTTPS or localhost) for the full standalone
      install experience - works automatically once accessed via
      the Internet Sharing HTTPS link below; on plain LAN http it
      still adds a home-screen shortcut, just without the service
      worker's benefits.
   =========================================================== */
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/service-worker.js").catch(() => {
        // Non-fatal: most likely running on plain http, not a secure context.
    });
}

/* ===========================================================
   HELPERS - reading/writing simple cookies
   =========================================================== */
function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

/* ===========================================================
   1) DEVICE NAME - shown once, so others on the network can
      see who's who without a full login/signup
   =========================================================== */
const nameModal = document.getElementById("nameModal");
const nameInput = document.getElementById("nameInput");
const nameSaveBtn = document.getElementById("nameSaveBtn");
const deviceBadge = document.getElementById("deviceBadge");

if (!getCookie("device_name")) {
    nameModal.style.display = "flex";
}

nameSaveBtn.addEventListener("click", saveDeviceName);
nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveDeviceName(); });

async function saveDeviceName() {
    const name = nameInput.value.trim();
    if (!name) return;
    try {
        const res = await fetch("/set-device-name", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            nameModal.style.display = "none";
            deviceBadge.textContent = name;
            location.reload(); // reload so the server-rendered page knows the name too
        }
    } catch (err) {
        alert("Could not save name: " + err.message);
    }
}

/* ===========================================================
   2) DARK MODE - toggled with a button, remembered per-session
      (kept in memory only, since browser storage APIs aren't
      used here - it just resets if you close the tab)
   =========================================================== */
const darkModeToggle = document.getElementById("darkModeToggle");
darkModeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    darkModeToggle.textContent = document.body.classList.contains("dark") ? "☀️" : "🌙";
});

/* ===========================================================
   3) UPLOAD - drag & drop + click-to-choose, MULTIPLE files.
      Files are uploaded one at a time in sequence (not all at
      once) so the progress bar and status text can clearly show
      "file 2 of 5" instead of several bars fighting for space.
      Uses XMLHttpRequest (not fetch) specifically because it's
      the only way to get real upload progress percentages.
   =========================================================== */
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const progressWrap = document.getElementById("progressWrap");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const uploadStatus = document.getElementById("uploadStatus");

dropZone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) uploadFiles(Array.from(fileInput.files));
});

["dragenter", "dragover"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    })
);
["dragleave", "drop"].forEach(evt =>
    dropZone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
    })
);
dropZone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) uploadFiles(files);
});

function setStatus(text, type) {
    uploadStatus.textContent = text;
    uploadStatus.className = "status-msg" + (type ? " " + type : "");
}

/** Uploads a single file, resolving/rejecting when it finishes. */
function uploadOneFile(file, onProgress) {
    return new Promise((resolve, reject) => {
        const formData = new FormData();
        formData.append("file", file);

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/upload");

        xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
        });

        xhr.onload = () => {
            if (xhr.status === 200) resolve();
            else reject(new Error(`status ${xhr.status}: ${xhr.responseText}`));
        };
        xhr.onerror = () => reject(new Error("network error"));

        xhr.send(formData);
    });
}

/** Uploads a list of files one after another, updating the shared progress UI. */
async function uploadFiles(files) {
    progressWrap.style.display = "block";
    let succeeded = 0;
    const failed = [];

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setStatus(`Uploading ${i + 1} of ${files.length}: ${file.name}`, "");
        progressBar.style.width = "0%";
        progressText.textContent = "0%";

        try {
            await uploadOneFile(file, (percent) => {
                progressBar.style.width = percent + "%";
                progressText.textContent = percent + "%";
            });
            succeeded++;
        } catch (err) {
            failed.push(`${file.name} (${err.message})`);
        }
    }

    progressWrap.style.display = "none";

    if (failed.length === 0) {
        setStatus(`✓ ${succeeded} file${succeeded !== 1 ? "s" : ""} uploaded successfully.`, "success");
    } else if (succeeded === 0) {
        setStatus(
            `Upload failed for all files - if this is a phone, check its 'Local Network' ` +
            `permission, and make sure Wi-Fi Private Relay / VPN / Data Saver are off. ` +
            `Details: ${failed.join(", ")}`,
            "error"
        );
    } else {
        setStatus(`✓ ${succeeded} uploaded, ${failed.length} failed: ${failed.join(", ")}`, "error");
    }

    location.reload();
}

/* ===========================================================
   3b) IMAGE / VIDEO PREVIEW - clicking a previewable file's icon
       or name opens a lightbox that streams /preview/<filename>
       (server decrypts on the fly) instead of downloading it.
   =========================================================== */
const previewOverlay = document.getElementById("previewOverlay");
const previewContent = document.getElementById("previewContent");
const previewCaption = document.getElementById("previewCaption");
const previewClose = document.getElementById("previewClose");

function openPreview(filename, kind) {
    previewContent.innerHTML = "";
    const url = `/preview/${encodeURIComponent(filename)}`;
    if (kind === "image") {
        const img = document.createElement("img");
        img.src = url;
        img.alt = filename;
        previewContent.appendChild(img);
    } else {
        const video = document.createElement("video");
        video.src = url;
        video.controls = true;
        video.autoplay = true;
        previewContent.appendChild(video);
    }
    previewCaption.textContent = filename;
    previewOverlay.style.display = "flex";
}

function closePreview() {
    previewOverlay.style.display = "none";
    previewContent.innerHTML = ""; // stops video playback/downloading
}

document.querySelectorAll("[data-preview]").forEach((el) => {
    el.style.cursor = "pointer";
    el.addEventListener("click", () => openPreview(el.dataset.preview, el.dataset.kind));
});
previewClose.addEventListener("click", closePreview);
previewOverlay.addEventListener("click", (e) => { if (e.target === previewOverlay) closePreview(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePreview(); });

/* ===========================================================
   3c) RENAME - turns the filename into an inline text input
   =========================================================== */
document.querySelectorAll(".rename-btn").forEach((btn) => {
    btn.addEventListener("click", function () {
        const filename = this.dataset.filename;
        const row = this.closest(".file-row");
        const nameSpan = row.querySelector(".file-name");
        if (row.querySelector(".rename-input")) return; // already editing

        const dot = filename.lastIndexOf(".");
        const base = dot > 0 ? filename.slice(0, dot) : filename;
        const ext = dot > 0 ? filename.slice(dot) : "";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "rename-input";
        input.value = base;
        nameSpan.replaceWith(input);
        input.focus();
        input.select();

        const finish = async (commit) => {
            if (!commit) { location.reload(); return; }
            const newBase = input.value.trim();
            if (!newBase || newBase === base) { location.reload(); return; }
            try {
                const res = await fetch(`/rename/${encodeURIComponent(filename)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest" },
                    body: "new_name=" + encodeURIComponent(newBase + ext),
                });
                if (res.status === 401) { window.location.href = "/login"; return; }
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    alert("Rename failed: " + (err.detail || res.status));
                }
            } catch (err) {
                alert("Rename request failed: " + err.message);
            }
            location.reload();
        };

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") finish(true);
            if (e.key === "Escape") finish(false);
        });
        input.addEventListener("blur", () => finish(true));
    });
});

/* ===========================================================
   3d) INTERNET SHARING - optional public link via a Cloudflare
       quick tunnel (see tunnel.py). Polls /internet-share/status
       every 2s while starting up, since the public URL takes a
       few seconds to be assigned.
   =========================================================== */
const internetShareOff = document.getElementById("internetShareOff");
const internetShareOn = document.getElementById("internetShareOn");
const internetShareStartBtn = document.getElementById("internetShareStartBtn");
const internetShareStopBtn = document.getElementById("internetShareStopBtn");
const internetShareUrl = document.getElementById("internetShareUrl");
const internetShareQr = document.getElementById("internetShareQr");
const internetShareError = document.getElementById("internetShareError");
let internetSharePoll = null;

function showInternetShareError(msg) {
    internetShareError.textContent = msg;
    internetShareError.style.display = "block";
}

async function pollInternetShareStatus() {
    try {
        const res = await fetch("/internet-share/status", { headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (res.status === 401) { window.location.href = "/login"; return; }
        const data = await res.json();
        if (data.active && data.url) {
            clearInterval(internetSharePoll);
            internetSharePoll = null;
            internetShareOff.style.display = "none";
            internetShareOn.style.display = "block";
            internetShareUrl.textContent = data.url;
            internetShareQr.src = "/internet-qr.png?t=" + Date.now();
            internetShareQr.style.display = "inline-block";
        } else if (data.active) {
            internetShareUrl.textContent = "Starting… (usually takes a few seconds)";
        } else {
            clearInterval(internetSharePoll);
            internetSharePoll = null;
            internetShareOff.style.display = "block";
            internetShareOn.style.display = "none";
        }
    } catch (err) {
        // network hiccup while polling - try again on the next tick
    }
}

if (internetShareStartBtn) {
    internetShareStartBtn.addEventListener("click", async () => {
        internetShareError.style.display = "none";
        internetShareOff.style.display = "none";
        internetShareOn.style.display = "block";
        internetShareUrl.textContent = "Starting…";
        try {
            const res = await fetch("/internet-share/start", {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (res.status === 401) { window.location.href = "/login"; return; }
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                internetShareOff.style.display = "block";
                internetShareOn.style.display = "none";
                showInternetShareError(err.detail || "Could not start internet sharing.");
                return;
            }
            internetSharePoll = setInterval(pollInternetShareStatus, 2000);
            pollInternetShareStatus();
        } catch (err) {
            internetShareOff.style.display = "block";
            internetShareOn.style.display = "none";
            showInternetShareError("Request failed: " + err.message);
        }
    });
}

if (internetShareStopBtn) {
    internetShareStopBtn.addEventListener("click", async () => {
        try {
            await fetch("/internet-share/stop", {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
        } catch (err) {
            // ignore - UI resets below regardless
        }
        if (internetSharePoll) clearInterval(internetSharePoll);
        internetShareOff.style.display = "block";
        internetShareOn.style.display = "none";
        internetShareQr.style.display = "none";
    });
}

// If sharing was already on (e.g. page reload while active), reflect that on load.
if (internetShareStartBtn) {
    pollInternetShareStatus();
}

/* ===========================================================
   4) DELETE
   =========================================================== */
document.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.addEventListener("click", async function () {
        const filename = this.dataset.filename;
        if (!confirm(`Delete "${filename}"?`)) return;
        try {
            const res = await fetch(`/delete/${encodeURIComponent(filename)}`, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (res.status === 401) { window.location.href = "/login"; return; }
            if (res.ok) location.reload();
            else alert("Delete failed (status " + res.status + ")");
        } catch (err) {
            alert("Delete request failed: " + err.message);
        }
    });
});

/* ===========================================================
   5) SEARCH - filters files by re-loading the page with a
      ?search= query param (server does the actual filtering)
   =========================================================== */
const searchBox = document.getElementById("searchBox");
let searchTimeout;
searchBox.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const params = new URLSearchParams(window.location.search);
        if (searchBox.value) params.set("search", searchBox.value);
        else params.delete("search");
        window.location.search = params.toString();
    }, 500); // wait 500ms after typing stops, so we don't reload on every keystroke
});

/* ===========================================================
   6) LIVE CHAT - JSON-based protocol over WebSocket:
      {type: "chat"}, {type: "system"}, {type: "refresh"}, {type: "presence"}
   =========================================================== */
const messagesBox = document.getElementById("messages");
const onlineCount = document.getElementById("onlineCount");
const messageInput = document.getElementById("message");
const sendBtn = document.getElementById("sendBtn");

let ws;
try {
    const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(wsProtocol + window.location.host + "/ws");

    ws.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.type === "refresh") {
            setTimeout(() => location.reload(), 800);
            return;
        }

        if (data.type === "presence") {
            onlineCount.textContent = `● ${data.users.length} online`;
            return;
        }

        const p = document.createElement("p");
        if (data.type === "chat") {
            p.innerHTML = `<span class="chat-msg-user">${escapeHtml(data.user)}:</span> ${escapeHtml(data.text)}`;
        } else if (data.type === "system") {
            p.className = "chat-msg-system";
            p.textContent = data.text;
        }
        messagesBox.appendChild(p);
        messagesBox.scrollTop = messagesBox.scrollHeight;
    };

    ws.onerror = () => {
        const p = document.createElement("p");
        p.className = "chat-msg-system";
        p.textContent = "Chat connection error (file sharing still works without it).";
        messagesBox.appendChild(p);
    };
} catch (err) {
    console.log("WebSocket unavailable:", err.message);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Chat isn't connected yet - try again in a moment.");
        return;
    }
    ws.send(text);
    messageInput.value = "";
}



sendBtn.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });
