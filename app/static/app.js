let currentThreadId = "session_" + Date.now();

document.addEventListener("DOMContentLoaded", () => {
    fetchActiveModel();
    setupEventListeners();
    loadCorpusDocs();
    loadThreads();
});

function setupEventListeners() {
    // Chat Input Submit
    const chatInput = document.getElementById("chatInput");
    const btnSendChat = document.getElementById("btnSendChat");
    const chatForm = document.getElementById("chatInputForm");

    chatInput.addEventListener("input", function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        btnSendChat.disabled = this.value.trim() === "";
    });

    function handleChatSubmit() {
        const query = chatInput.value.trim();
        if (query) {
            submitChatMessage(query);
            chatInput.value = "";
            chatInput.style.height = 'auto';
            btnSendChat.disabled = true;
        }
    }

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault(); // Prevent newline in textarea
            if (chatInput.value.trim() !== "") {
                handleChatSubmit();
            }
        }
    });

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault(); // Prevent page reload
        handleChatSubmit();
    });

    // File Upload Input
    document.getElementById("pdfFileInput").addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            uploadPdfFile(e.target.files[0]);
        }
    });

    // Admin Modal
    document.getElementById("openAdminBtn").addEventListener("click", openAdminModal);
    document.getElementById("adminUploadForm").addEventListener("submit", submitAdminUpload);
}

// --- Chat Core ---
function appendUserMessage(text, metadataHtml = "") {
    const feed = document.getElementById("chatFeed");
    const div = document.createElement("div");
    div.className = "message user-message";
    
    // User avatar
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-user"></i></div>
        <div class="message-content">
            <p>${text}</p>
            ${metadataHtml}
        </div>
    `;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function appendAssistantMessage(htmlContent) {
    const feed = document.getElementById("chatFeed");
    const div = document.createElement("div");
    div.className = "message assistant-message";
    
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-scale-balanced"></i></div>
        <div class="message-content">
            ${htmlContent}
        </div>
    `;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
    return div;
}

function showTypingIndicator() {
    const feed = document.getElementById("chatFeed");
    const div = document.createElement("div");
    div.id = "typingIndicator";
    div.className = "message assistant-message";
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-scale-balanced"></i></div>
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function removeTypingIndicator() {
    const el = document.getElementById("typingIndicator");
    if (el) el.remove();
}

function clearChat() {
    currentThreadId = "session_" + Date.now();
    const feed = document.getElementById("chatFeed");
    // Keep only the first welcome message
    const firstMsg = feed.firstElementChild;
    feed.innerHTML = "";
    if (firstMsg) feed.appendChild(firstMsg);
}

// --- API Interactions ---
async function fetchActiveModel() {
    try {
        const res = await fetch("/api/models");
        if (res.ok) {
            const data = await res.json();
            document.getElementById("activeModelLabel").innerText = `${data.current_provider.toUpperCase()}`;
        }
    } catch (e) {
        console.warn("Could not fetch models:", e);
    }
}

async function loadThreads() {
    try {
        const res = await fetch("/api/threads");
        if (res.ok) {
            const threads = await res.json();
            const container = document.getElementById("threadList");
            if (!container) return;
            container.innerHTML = "";
            if (threads.length === 0) {
                container.innerHTML = "<p style='color:var(--text-muted); font-size: 0.9em;'>No past conversations.</p>";
                return;
            }
            threads.forEach((t) => {
                const item = document.createElement("div");
                item.className = "thread-item";
                if (t.thread_id === currentThreadId) item.classList.add("active");
                item.innerHTML = `
                    <div class="thread-title">${t.title}</div>
                    <div class="thread-date">${new Date(t.updated_at).toLocaleDateString()}</div>
                `;
                item.addEventListener("click", () => loadThreadHistory(t.thread_id));
                container.appendChild(item);
            });
        }
    } catch (e) {
        console.warn("Could not load threads:", e);
    }
}

async function loadThreadHistory(threadId) {
    currentThreadId = threadId;
    document.getElementById("chatFeed").innerHTML = "";
    loadThreads(); // update active state
    
    try {
        const res = await fetch(`/api/threads/${threadId}`);
        if (res.ok) {
            const data = await res.json();
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    if (msg.role === 'user') {
                        appendUserMessage(msg.content);
                    } else {
                        // Minimal rendering for history
                        appendAssistantMessage(`<div class="markdown-body">${marked.parse(msg.content)}</div>`);
                    }
                });
            } else {
                appendAssistantMessage("<p>No messages found in this thread.</p>");
            }
        }
    } catch (e) {
        console.warn("Could not load thread history:", e);
    }
}

async function submitChatMessage(query) {
    appendUserMessage(query);
    showTypingIndicator();

    // Check if we are responding to a clarification by checking if there's a recent banner in the UI state
    // (This is simplified; ideally server tracks it but we can set is_clarification_response based on previous AI msg)
    const isClarification = document.body.dataset.pendingClarification === "true";
    document.body.dataset.pendingClarification = "false"; // reset

    try {
        const res = await fetch("/api/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query: query,
                thread_id: currentThreadId,
                is_clarification_response: isClarification
            })
        });

        const data = await res.json();
        removeTypingIndicator();
        renderApiResponse(data);
    } catch (e) {
        removeTypingIndicator();
        appendAssistantMessage(`<p style="color:var(--danger)">Error: ${e.message}</p>`);
    }
}

async function uploadPdfFile(file) {
    appendUserMessage(`Uploaded Document: <strong>${file.name}</strong>`);
    showTypingIndicator();
    
    const formData = new FormData();
    formData.append("file", file);
    formData.append("thread_id", currentThreadId);

    try {
        const res = await fetch("/api/upload-pdf", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        removeTypingIndicator();
        renderApiResponse(data);
    } catch (e) {
        removeTypingIndicator();
        appendAssistantMessage(`<p style="color:var(--danger)">Error uploading PDF: ${e.message}</p>`);
    }
}

function renderApiResponse(data) {
    let html = "";

    // 1. Clarification Request
    if (data.requires_user_clarification) {
        document.body.dataset.pendingClarification = "true";
        html += `<p><i class="fa-solid fa-triangle-exclamation" style="color:var(--warning)"></i> <strong>Clarification Required</strong></p>`;
        html += `<p>${data.clarification_prompt}</p>`;
        appendAssistantMessage(html);
        return; // Stop here, wait for user reply
    }

    // 2. Reason Trace Block (Prominent)
    if (data.reasoning_plan && data.reasoning_plan.length > 0) {
        html += `
            <div class="agent-execution-plan card-glass" style="margin-bottom: 16px; padding: 12px; background: rgba(0, 255, 136, 0.05); border-left: 3px solid var(--success);">
                <div style="font-weight: 600; font-size: 0.9em; margin-bottom: 8px; color: var(--success); text-transform: uppercase; letter-spacing: 0.5px;">
                    <i class="fa-solid fa-microchip"></i> Agent Execution Trace
                </div>
                <ul style="list-style: none; padding: 0; margin: 0; font-size: 0.85em; color: var(--text-muted);">
                    ${data.reasoning_plan.map(step => `<li style="margin-bottom: 4px;"><i class="fa-solid fa-check" style="color:var(--success); margin-right: 6px;"></i> ${step}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // 3. Compliance Risk Badges
    if (data.compliance_risk_flags && data.compliance_risk_flags.length > 0) {
        html += `<div style="margin: 12px 0;">`;
        data.compliance_risk_flags.forEach((r) => {
            html += `<div class="risk-badge ${r.severity}">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <span>${r.message}</span>
            </div>`;
        });
        html += `</div>`;
    }

    // 4. Main Markdown Content
    const md = data.markdown_output || data.final_markdown_output || "";
    if (md) {
        html += `<div class="markdown-body">${marked.parse(md)}</div>`;
    }

    appendAssistantMessage(html);
}

// --- Admin Modal Functions ---
function openAdminModal() {
    document.getElementById("adminModal").style.display = "flex";
    loadCorpusDocs();
}

function closeAdminModal() {
    document.getElementById("adminModal").style.display = "none";
}

async function loadCorpusDocs() {
    try {
        const res = await fetch("/api/documents");
        if (res.ok) {
            const docs = await res.json();
            const container = document.getElementById("corpusDocList");
            if (!container) return;
            container.innerHTML = "";
            docs.forEach((d) => {
                const item = document.createElement("div");
                item.className = "corpus-item";
                item.innerHTML = `
                    <div><strong>${d.document_name}</strong> <span class="badge" style="margin-left:4px">${d.doc_type}</span></div>
                    <div><a href="${d.download_url}" target="_blank"><i class="fa-solid fa-code"></i></a></div>
                `;
                container.appendChild(item);
            });
        }
    } catch (e) {
        console.warn("Could not load corpus docs:", e);
    }
}

async function submitAdminUpload(e) {
    e.preventDefault();
    const formData = new FormData();
    formData.append("doc_id", document.getElementById("adminDocId").value);
    formData.append("document_name", document.getElementById("adminDocName").value);
    formData.append("doc_type", document.getElementById("adminDocType").value);
    formData.append("issuing_authority", document.getElementById("adminAuthority").value);
    formData.append("file", document.getElementById("adminFile").files[0]);

    try {
        const res = await fetch("/api/admin/corpus/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        alert(data.message);
        loadCorpusDocs();
    } catch (err) {
        alert("Upload failed: " + err.message);
    }
}

async function triggerReindex() {
    try {
        const res = await fetch("/api/admin/corpus/reindex", { method: "POST" });
        const data = await res.json();
        alert(data.message);
        loadCorpusDocs();
    } catch (e) {
        alert("Re-index failed: " + e.message);
    }
}
