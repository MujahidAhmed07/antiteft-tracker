let currentSource = "demo3.mp4";
let currentConf = 0.25;
let currentProximity = 0.45;
let isStreaming = false;
let telemetryInterval = null;
let recordedIncidents = [];
let sliderDebounceTimer = null;

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    setupDropZone();
});

// Real-Time Top Clock
function initClock() {
    function update() {
        const now = new Date();
        const timeStr = now.toTimeString().split(" ")[0];
        const clockEl = document.getElementById("liveClock");
        if (clockEl) clockEl.innerText = timeStr;
    }
    update();
    setInterval(update, 1000);
}

// Start Stream
function startStream() {
    const streamImg = document.getElementById("videoStream");
    const placeholder = document.getElementById("videoPlaceholder");
    const feedTitle = document.getElementById("currentFeedName");

    if (!streamImg || !placeholder) return;

    // Stop the previous stream on the backend before starting a new one
    fetch("/api/stop").catch(() => {});

    const streamUrl = `/api/stream?source=${encodeURIComponent(currentSource)}&conf=${currentConf}&proximity=${currentProximity}&t=${Date.now()}`;
    streamImg.src = streamUrl;
    streamImg.classList.remove("hidden");
    placeholder.classList.add("hidden");

    streamImg.onerror = () => {
        if (isStreaming) {
            console.error("Stream connection dropped or source unavailable.");
            updateStatusHUD("ERROR / OFFLINE", true);
        }
    };

    isStreaming = true;
    updateStatusHUD("CONNECTING...", false);

    if (feedTitle) {
        if (currentSource === "0") {
            feedTitle.innerText = "Camera 0 (Default Webcam)";
        } else if (currentSource === "1") {
            feedTitle.innerText = "Camera 1 (Phone / USB Cam)";
        } else if (currentSource === "2") {
            feedTitle.innerText = "Camera 2 (Auxiliary Cam)";
        } else if (currentSource.startsWith("http")) {
            feedTitle.innerText = "Phone IP Stream: " + currentSource;
        } else {
            feedTitle.innerText = currentSource.split("/").pop().split("\\").pop();
        }
    }

    if (telemetryInterval) clearInterval(telemetryInterval);
    telemetryInterval = setInterval(fetchTelemetry, 600);
}

// Stop Stream
function stopStream() {
    const streamImg = document.getElementById("videoStream");
    const placeholder = document.getElementById("videoPlaceholder");

    // Tell the backend to stop the stream
    fetch("/api/stop").catch(() => {});

    if (streamImg) {
        streamImg.src = "";
        streamImg.classList.add("hidden");
    }
    if (placeholder) placeholder.classList.remove("hidden");

    isStreaming = false;
    updateStatusHUD("STANDBY", false);

    if (telemetryInterval) {
        clearInterval(telemetryInterval);
        telemetryInterval = null;
    }

    document.getElementById("kpiFps").innerHTML = `0.0 <small>FPS</small>`;
}

// Select Demo Video
function selectDemo(demoPath, el) {
    document.querySelectorAll(".btn-demo").forEach(btn => btn.classList.remove("active"));
    if (el) el.classList.add("active");

    currentSource = demoPath;
    startStream();
}

// Select Camera by Index (Cam 0, Cam 1, Cam 2)
function selectCamera(camIndex, el) {
    document.querySelectorAll(".btn-demo").forEach(btn => btn.classList.remove("active"));
    if (el) el.classList.add("active");

    currentSource = String(camIndex);
    startStream();
}

// Select Webcam (Backwards compatibility)
function selectWebcam(el) {
    selectCamera("0", el);
}

// Connect Phone IP Camera Stream
function connectIpCamera() {
    const urlInput = document.getElementById("ipCamUrl");
    if (!urlInput || !urlInput.value.trim()) {
        alert("Please enter a valid Phone/IP Camera stream URL (e.g. http://192.168.1.50:8080/video)");
        return;
    }
    const url = urlInput.value.trim();
    document.querySelectorAll(".btn-demo").forEach(btn => btn.classList.remove("active"));

    currentSource = url;
    startStream();
}

// Load Default
function loadDefaultFeed() {
    const demo3Btn = document.querySelector(".btn-demo");
    selectDemo("demo3.mp4", demo3Btn);
}

// Update Confidence (debounced to avoid excessive stream restarts)
function updateConf(val) {
    currentConf = parseFloat(val);
    document.getElementById("confSliderValue").innerText = currentConf.toFixed(2);
    document.getElementById("kpiConf").innerText = currentConf.toFixed(2);

    if (isStreaming) {
        clearTimeout(sliderDebounceTimer);
        sliderDebounceTimer = setTimeout(() => startStream(), 800);
    }
}

// Update Proximity Gap Ratio (debounced to avoid excessive stream restarts)
function updateProximity(val) {
    currentProximity = parseFloat(val);
    document.getElementById("proxSliderValue").innerText = currentProximity.toFixed(2);

    if (isStreaming) {
        clearTimeout(sliderDebounceTimer);
        sliderDebounceTimer = setTimeout(() => startStream(), 800);
    }
}

// Fetch Telemetry from Backend
async function fetchTelemetry() {
    if (!isStreaming) return;

    try {
        const res = await fetch("/api/telemetry");
        if (!res.ok) return;
        const data = await res.json();

        // Update KPIs
        document.getElementById("kpiFps").innerHTML = `${data.fps || 0.0} <small>FPS</small>`;
        document.getElementById("kpiAlerts").innerText = data.alerts_count || 0;
        document.getElementById("incidentCounter").innerText = `${data.alerts_count || 0} Events`;

        const totalFrames = data.frame_total || 0;
        const currFrame = data.frame_current || 0;
        if (totalFrames > 0) {
            document.getElementById("kpiFrames").innerText = `${currFrame} / ${totalFrames}`;
        } else {
            document.getElementById("kpiFrames").innerText = `Live (${currFrame})`;
        }
        document.getElementById("frameWatermark").innerText = `FRM: ${currFrame}`;

        if (data.status && data.status.startsWith("Error")) {
            updateStatusHUD("ERROR / OFFLINE", true);
        } else if (data.active_alert) {
            updateStatusHUD("ALERT", true);
        } else if (data.is_processing) {
            updateStatusHUD("MONITORING", false);
        }

        // Update Incident Log & Snapshot Evidence Gallery
        if (data.incidents && data.incidents.length > 0) {
            renderIncidents(data.incidents);
            renderSnapshotGallery(data.incidents);
        }

        // Check if stream completed
        if (!data.is_processing && totalFrames > 0 && currFrame >= totalFrames - 2) {
            updateStatusHUD("COMPLETED", false);
        }
    } catch (e) {
        console.warn("Telemetry fetch error:", e);
    }
}

function updateStatusHUD(status, isAlert) {
    const pill = document.getElementById("hudStatusBadge");
    if (!pill) return;

    pill.innerText = status;
    if (isAlert) {
        pill.classList.add("alert");
    } else {
        pill.classList.remove("alert");
    }
}

function renderIncidents(incidents) {
    const container = document.getElementById("incidentFeed");
    const emptyState = document.getElementById("emptyLogState");

    if (!container) return;
    if (emptyState) emptyState.style.display = "none";

    container.innerHTML = "";
    incidents.slice(-20).reverse().forEach(item => {
        const div = document.createElement("div");
        div.className = "incident-item";
        div.innerHTML = `
            <div class="incident-item-header">
                <span class="incident-title">🚨 ${item.type}</span>
                <span class="incident-time">${item.timestamp}</span>
            </div>
            <div class="incident-item-footer">
                <span>Frame #${item.frame}</span>
                <span style="color: var(--accent-cyan);">Conf: ${item.confidence}</span>
            </div>
        `;
        container.appendChild(div);
    });
}

let lastRenderedSnapshotCount = -1;

function renderSnapshotGallery(incidents) {
    const grid = document.getElementById("snapshotGrid");
    const counter = document.getElementById("galleryCounter");
    if (!grid) return;

    // Filter only incidents that have snapshots
    const snapshots = incidents.filter(item => item.snapshot);

    if (counter) {
        counter.innerText = `${snapshots.length} Snapshot${snapshots.length === 1 ? '' : 's'}`;
    }

    if (snapshots.length === 0) {
        return;
    }

    // Only re-render if count changed to prevent DOM thrashing
    if (snapshots.length === lastRenderedSnapshotCount) {
        return;
    }
    lastRenderedSnapshotCount = snapshots.length;

    grid.innerHTML = "";

    // Show latest snapshots first in responsive grid covering full width
    [...snapshots].reverse().forEach((item, idx) => {
        const card = document.createElement("div");
        card.className = "gallery-item-card";
        card.onclick = () => openSnapshotModal(item.snapshot, item.timestamp, item.frame, item.confidence);
        card.innerHTML = `
            <div class="gallery-img-wrapper">
                <img src="${item.snapshot}" alt="Crime scene snapshot frame ${item.frame}" loading="lazy">
                <div class="gallery-overlay">
                    <span class="overlay-icon">🔍</span>
                    <span class="overlay-text">Click to View Popup</span>
                </div>
                <span class="gallery-tag-alert">🚨 ALERT #${item.id || (snapshots.length - idx)}</span>
            </div>
            <div class="gallery-item-info">
                <div class="gallery-item-top">
                    <span class="gallery-time">⏱️ ${item.timestamp}</span>
                    <span class="gallery-conf">${item.confidence}</span>
                </div>
                <div class="gallery-item-bot">
                    <span>Frame #${item.frame}</span>
                    <span class="gallery-inspect-btn">Open Popup ↗</span>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

function clearGallery() {
    const grid = document.getElementById("snapshotGrid");
    if (grid) {
        grid.innerHTML = `
            <div class="empty-gallery-state" id="emptyGalleryState">
                <div class="empty-icon">📷</div>
                <h4>No Crime Scene Images Captured Yet</h4>
                <p>When shoplifting or suspicious proximity is detected during video playback, evidence scene images will appear here in a full-width grid automatically.</p>
            </div>
        `;
    }
    lastRenderedSnapshotCount = -1;
    const counter = document.getElementById("galleryCounter");
    if (counter) counter.innerText = "0 Snapshots";
}

function openSnapshotModal(imgUrl, timestamp, frame, conf) {
    const modal = document.getElementById("snapshotModal");
    const img = document.getElementById("modalSnapshotImg");
    const title = document.getElementById("modalSnapshotTitle");
    const meta = document.getElementById("modalSnapshotMeta");
    const dlBtn = document.getElementById("modalDownloadBtn");

    if (!modal || !img) return;

    img.src = imgUrl;
    title.innerText = `Theft Evidence Capture: Frame #${frame}`;
    meta.innerHTML = `<span><strong>Timestamp:</strong> ${timestamp}</span> • <span><strong>Frame:</strong> #${frame}</span> • <span style="color: var(--accent-cyan);"><strong>Confidence:</strong> ${conf}</span>`;
    dlBtn.href = imgUrl;
    dlBtn.download = `theft_evidence_frame_${frame}.jpg`;

    modal.classList.remove("hidden");
}

function closeSnapshotModal() {
    const modal = document.getElementById("snapshotModal");
    if (modal) modal.classList.add("hidden");
}

// Close popup modal on ESC key
window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeSnapshotModal();
    }
});

function clearIncidentLog() {
    const container = document.getElementById("incidentFeed");
    if (container) {
        container.innerHTML = `
            <div class="empty-feed" id="emptyLogState">
                <span>🛡️</span>
                <p>No active incidents detected.</p>
                <small>System is continuously monitoring for suspicious theft behaviors.</small>
            </div>
        `;
    }
    document.getElementById("incidentCounter").innerText = "0 Events";
    clearGallery();
}

// Download Output
function downloadRecording() {
    window.location.href = "/api/download";
}

// Drag & Drop Upload
function setupDropZone() {
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("videoFileInput");

    if (!dropZone || !fileInput) return;

    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("dragover");
        });
    });

    dropZone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files[0]);
        }
    });
}

async function handleFileUpload(file) {
    const progressContainer = document.getElementById("uploadProgress");
    const progressBar = document.getElementById("progressBar");
    const statusText = document.getElementById("uploadStatusText");

    if (!progressContainer || !progressBar || !statusText) return;

    progressContainer.classList.remove("hidden");
    progressBar.style.width = "40%";
    statusText.innerText = `Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/upload", {
            method: "POST",
            body: formData,
        });

        if (!res.ok) {
            const err = await res.json();
            alert(`Upload failed: ${err.detail || "Error uploading file"}`);
            progressContainer.classList.add("hidden");
            return;
        }

        const data = await res.json();
        progressBar.style.width = "100%";
        statusText.innerText = `Uploaded (${data.size_mb} MB)! Starting AI Detection...`;

        setTimeout(() => {
            progressContainer.classList.add("hidden");
            document.querySelectorAll(".btn-demo").forEach(btn => btn.classList.remove("active"));
            currentSource = data.path;
            startStream();
        }, 800);
    } catch (e) {
        alert(`Upload error: ${e.message}`);
        progressContainer.classList.add("hidden");
    }
}
