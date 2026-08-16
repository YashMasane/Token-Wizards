let currentThreadId = "session_" + Date.now();

// ─── Demo credentials (prototype only — no backend auth) ───
const DEMO_USERS = [
    { id: "admin_yash", password: "lsgd@2024", name: "Yash Masane", role: "Admin" },
    { id: "officer01",  password: "officer@123", name: "Legal Officer", role: "Officer" },
];
let currentUser = null;

// ─── Boot ───
function initApp() {
    const saved = sessionStorage.getItem("tw_user");
    if (saved) {
        currentUser = JSON.parse(saved);
        document.getElementById("loginOverlay").style.display = "none";
        bootApp();
    } else {
        setupLoginForm();
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
} else {
    initApp();
}

function setupLoginForm() {
    document.getElementById("loginForm").addEventListener("submit", (e) => {
        e.preventDefault();
        const userId   = document.getElementById("loginUserId").value.trim();
        const password = document.getElementById("loginPassword").value;
        const user = DEMO_USERS.find(u => u.id === userId && u.password === password);
        if (user) {
            currentUser = user;
            sessionStorage.setItem("tw_user", JSON.stringify(user));
            // Fade out login
            const overlay = document.getElementById("loginOverlay");
            overlay.style.transition = "opacity 0.4s ease";
            overlay.style.opacity = "0";
            setTimeout(() => {
                overlay.style.display = "none";
                bootApp();
            }, 400);
        } else {
            document.getElementById("loginError").style.display = "flex";
            document.getElementById("loginErrorMsg").textContent = "Invalid User ID or password.";
        }
    });
}

function bootApp() {
    document.getElementById("appRoot").style.display = "flex";
    // Populate profile info
    const initial = (currentUser.name || "?")[0].toUpperCase();
    ["profileInitial","profileInitialLg","settingsInitial"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = initial;
    });
    document.getElementById("profileName").textContent = currentUser.name;
    document.getElementById("profileRole").textContent = currentUser.role;
    document.getElementById("pdName").textContent = currentUser.name;
    document.getElementById("pdRole").innerHTML = `<i class="fa-solid fa-shield-halved"></i> ${currentUser.role}`;
    document.getElementById("pdId").textContent = `ID: ${currentUser.id}`;
    document.getElementById("settingsName").textContent = currentUser.name;
    document.getElementById("settingsFullName").value = currentUser.name;
    // Show Admin-only items
    if (currentUser.role === "Admin") {
        const addUserBtn = document.getElementById("openAddUserBtn");
        if (addUserBtn) addUserBtn.style.display = "flex";
    } else {
        const adminBtn = document.getElementById("openAdminBtn");
        if (adminBtn) adminBtn.style.display = "none";
    }
    // Wire sidebar & profile
    setupSidebar();
    fetchActiveModel();
    setupEventListeners();
    loadCorpusDocs();
    loadThreads();
    // Close profile dropdown on outside click
    document.addEventListener("click", (e) => {
        if (!document.getElementById("profileMenuWrap")?.contains(e.target)) {
            closeProfileMenu();
        }
    });
}

function logout() {
    sessionStorage.removeItem("tw_user");
    currentUser = null;
    location.reload();
}

function togglePwd() {
    const input = document.getElementById("loginPassword");
    const icon  = document.getElementById("pwdEyeIcon");
    if (input.type === "password") {
        input.type = "text";
        icon.className = "fa-solid fa-eye-slash";
    } else {
        input.type = "password";
        icon.className = "fa-solid fa-eye";
    }
}

// ─── Sidebar toggle ───
function setupSidebar() {
    document.getElementById("hideSidebarBtn").addEventListener("click", () => {
        document.getElementById("mainSidebar").classList.add("collapsed");
        document.getElementById("expandSidebarBtn").style.display = "flex";
    });
    document.getElementById("expandSidebarBtn").addEventListener("click", () => {
        document.getElementById("mainSidebar").classList.remove("collapsed");
        document.getElementById("expandSidebarBtn").style.display = "none";
    });
}

function newChat() {
    clearChat();
    loadThreads();
}

// ─── Profile dropdown ───
function toggleProfileMenu() {
    const dd    = document.getElementById("profileDropdown");
    const caret = document.getElementById("profileCaret");
    const open  = dd.classList.toggle("open");
    caret.classList.toggle("open", open);
}

function closeProfileMenu() {
    document.getElementById("profileDropdown")?.classList.remove("open");
    document.getElementById("profileCaret")?.classList.remove("open");
}

function openProfileSettings() {
    closeProfileMenu();
    document.getElementById("profileSettingsModal").style.display = "flex";
}

function closeProfileSettings() {
    document.getElementById("profileSettingsModal").style.display = "none";
}

function openAddUserModal() {
    closeProfileMenu();
    document.getElementById("addUserForm").reset();
    document.getElementById("addUserSuccess").style.display = "none";
    const btn = document.getElementById("addUserForm").querySelector("button[type=submit]");
    btn.disabled = false;
    btn.style.display = "block";
    btn.innerHTML = '<i class="fa-solid fa-check"></i> Create User';
    document.getElementById("addUserModal").style.display = "flex";
}

function closeAddUserModal() {
    document.getElementById("addUserModal").style.display = "none";
}


function setupEventListeners() {
    // Chat Input Submit
    const chatInput = document.getElementById("chatInput");
    const btnSendChat = document.getElementById("btnSendChat");
    const chatForm = document.getElementById("chatInputForm");

    // Auto-grow textarea: overflow must be hidden while measuring scrollHeight,
    // otherwise the browser shows a scrollbar instead of reporting the true content height.
    function autoGrow(el) {
        el.style.overflow = 'hidden';          
        el.style.height = '1px';              // Force collapse so scrollHeight calculates true content size
        const newH = Math.min(el.scrollHeight, 200);
        el.style.height = newH + 'px';
        // Only show scrollbar once the cap (200px) is exceeded
        el.style.overflowY = el.scrollHeight > 200 ? 'auto' : 'hidden';
    }

    chatInput.addEventListener("input", function() {
        autoGrow(this);
        btnSendChat.disabled = this.value.trim() === "";
    });

    function handleChatSubmit() {
        const query = chatInput.value.trim();
        // Allow submission if there is text OR if a document is attached
        if (query || currentDocFilename) {
            submitChatMessage(query);
            chatInput.value = "";
            autoGrow(chatInput);   // snap back to single-line height
            btnSendChat.disabled = true;
            document.getElementById("attachmentContainer").style.display = "none";
            document.getElementById("attachmentContainer").innerHTML = "";
            document.getElementById('pdfFileInput').value = "";
        }
    }

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault(); // Prevent newline in textarea
            if (chatInput.value.trim() !== "" || currentDocFilename) {
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

    // Add User Modal
    document.getElementById("addUserForm")?.addEventListener("submit", (e) => {
        e.preventDefault();
        const btn = e.target.querySelector("button[type=submit]");
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        
        // Simulate API call
        setTimeout(() => {
            document.getElementById("addUserSuccess").style.display = "block";
            btn.style.display = "none";
            setTimeout(() => {
                closeAddUserModal();
            }, 1500);
        }, 800);
    });
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
            <div class="msg-text">${text}</div>
            ${metadataHtml}
            <button class="copy-btn user-copy" onclick="copyToClipboard(this)" title="Copy prompt"><i class="fa-regular fa-copy"></i></button>
        </div>
    `;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
    return div;
}

function appendAssistantMessage(htmlContent) {
    const feed = document.getElementById("chatFeed");
    const div = document.createElement("div");
    div.className = "message assistant-message";
    
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-scale-balanced"></i></div>
        <div class="message-content">
            ${htmlContent}
            <button class="copy-btn assistant-copy" onclick="copyToClipboard(this)" title="Copy response"><i class="fa-regular fa-copy"></i></button>
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
    document.getElementById("chatFeed").innerHTML = "";
}

window.copyToClipboard = function(btn) {
    const msgContent = btn.parentElement;
    let textToCopy = "";
    if (btn.classList.contains("user-copy")) {
        const p = msgContent.querySelector(".msg-text");
        if (p) textToCopy = p.innerText;
    } else {
        const mdBody = msgContent.querySelector(".markdown-body");
        if (mdBody) {
            textToCopy = mdBody.innerText;
        } else {
            textToCopy = msgContent.innerText;
        }
    }
    
    if (textToCopy) {
        navigator.clipboard.writeText(textToCopy).then(() => {
            const icon = btn.querySelector("i");
            icon.className = "fa-solid fa-check";
            btn.style.color = "var(--success)";
            setTimeout(() => {
                icon.className = "fa-regular fa-copy";
                btn.style.color = "";
            }, 2000);
        });
    }
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

let currentDocContext = null;
let currentDocFilename = null;

async function submitChatMessage(query) {
    let attachmentHtml = "";
    if (currentDocFilename) {
        attachmentHtml = `
            <div style="margin-top: 8px; padding: 6px 12px; background: rgba(0,0,0,0.15); border-radius: 6px; font-size: 0.85rem; display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--border-glass);">
                <i class="fa-solid fa-file-pdf" style="color:var(--danger)"></i> 
                <strong>${currentDocFilename}</strong>
            </div>
        `;
    }
    
    appendUserMessage(query, attachmentHtml);
    showTypingIndicator();

    const isClarification = document.body.dataset.pendingClarification === "true";
    document.body.dataset.pendingClarification = "false"; 

    try {
        const payload = {
            query: query,
            thread_id: currentThreadId,
            is_clarification_response: isClarification
        };
        if (currentDocContext) {
            payload.document_context = currentDocContext;
            payload.document_filename = currentDocFilename;
            currentDocContext = null; // Consume it once
            currentDocFilename = null;
        }

        const res = await fetch("/api/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        await handleStreamResponse(res);
    } catch (e) {
        removeTypingIndicator();
        appendAssistantMessage(`<p style="color:var(--danger)">Error: ${e.message}</p>`);
    }
}

async function uploadPdfFile(file) {
    const attachmentContainer = document.getElementById("attachmentContainer");
    attachmentContainer.style.display = "flex";
    attachmentContainer.innerHTML = `<i class="fa-solid fa-file-pdf" style="color:var(--danger)"></i> <strong>${file.name}</strong> <i class="fa-solid fa-spinner fa-spin" style="margin-left:8px;"></i> Extracting...`;
    
    const formData = new FormData();
    formData.append("file", file);
    formData.append("thread_id", currentThreadId);

    try {
        const res = await fetch("/api/upload-pdf", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        
        if (res.ok && data.success) {
            currentDocContext = data.extracted_text;
            currentDocFilename = data.filename;
            
            attachmentContainer.innerHTML = `
                <i class="fa-solid fa-file-circle-check" style="color:var(--success)"></i> 
                <strong>${data.filename}</strong>
                <button type="button" onclick="clearAttachment()" style="background:none; border:none; color:var(--text-muted); cursor:pointer; margin-left:8px;"><i class="fa-solid fa-times"></i></button>
            `;
            // Enable the send button since a document is attached
            document.getElementById("btnSendChat").disabled = false;
        } else {
            throw new Error(data.detail || "Upload failed");
        }
    } catch (e) {
        attachmentContainer.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="color:var(--danger)"></i> <strong>Upload Error</strong>: ${e.message}`;
    }
}

function clearAttachment() {
    currentDocContext = null;
    currentDocFilename = null;
    const attachmentContainer = document.getElementById("attachmentContainer");
    attachmentContainer.style.display = "none";
    attachmentContainer.innerHTML = "";
    document.getElementById('pdfFileInput').value = "";
    
    // Disable send button if chat input is empty
    const chatInput = document.getElementById("chatInput");
    document.getElementById("btnSendChat").disabled = chatInput.value.trim() === "";
}

async function handleStreamResponse(res) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    
    removeTypingIndicator();
    const msgDiv = appendAssistantMessage("");
    const msgContent = msgDiv.querySelector(".message-content");
    
    let mdText = "";
    let planSteps = [];
    let legalPlanData = null;   // structured LegalReasoningPlan dict
    let flagsHtml = "";
    let sourcesHtml = "";
    let liveNodes = new Set();
    let isDone = false;

    function buildSourcesHtml(sources) {
        if (!sources || sources.length === 0) return "";
        const rows = sources.map((s, i) => {
            const url = s.url || "";
            const nameCell = url
                ? `<a href="${url}" target="_blank" rel="noopener noreferrer" class="src-link">
                     <i class="fa-solid fa-file-arrow-down"></i> ${s.name}
                   </a>`
                : `<span>${s.name}</span>`;
            return `<tr>
                <td class="src-num">${i + 1}</td>
                <td class="src-name">${nameCell}</td>
                <td><span class="src-badge">${s.type}</span></td>
                <td class="src-clause">${s.clause || '-'}</td>
                <td class="src-page">p.${s.page}</td>
            </tr>`;
        }).join("");
        return `<div class="sources-card">
            <div class="sources-card-header">
                <i class="fa-solid fa-book-bookmark"></i> Sources Referenced
                <span class="sources-count">${sources.length} document${sources.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="sources-table-wrap">
                <table class="sources-table">
                    <thead>
                        <tr><th>#</th><th>Document</th><th>Type</th><th>Clause / Rule</th><th>Page</th></tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    // Map of node names to display info
    const NODE_META = {
        "security_guardrail": { icon: "fa-shield-halved", label: "Security Check", color: "#6366F1" },
        "router":             { icon: "fa-code-branch",   label: "Intent Router",  color: "#06B6D4" },
        "planner":            { icon: "fa-brain",          label: "Query Planning", color: "#8B5CF6" },
        "retrieval":          { icon: "fa-magnifying-glass",label: "Retrieving Docs",color: "#F59E0B" },
        "sufficiency_check":  { icon: "fa-filter",         label: "Sufficiency Check",color: "#14B8A6" },
        "multi_agent_eval":   { icon: "fa-robot",          label: "Multi-Agent Eval",color: "#EC4899" },
        "synthesis":          { icon: "fa-pen-nib",         label: "Writing Draft",color: "#10B981" },
        "critic":             { icon: "fa-user-check",     label: "Auditing Draft", color: "#DC2626" },
        "chitchat":           { icon: "fa-comments",       label: "Responding",     color: "#06B6D4" },
    };
    
    function buildPipelineHtml() {
        if (liveNodes.size === 0) return "";
        let items = "";
        [...liveNodes].forEach((n, idx) => {
            const meta = NODE_META[n] || { icon: "fa-gear", label: n, color: "var(--success)" };
            const isLast = idx === liveNodes.size - 1 && !isDone;
            items += `
            <div class="exec-step">
                <div class="exec-step-icon" style="background: ${meta.color}22; border-color: ${meta.color};">
                    ${isLast
                        ? `<i class="fa-solid fa-spinner fa-spin" style="color:${meta.color}"></i>`
                        : `<i class="fa-solid ${meta.icon}" style="color:${meta.color}"></i>`}
                </div>
                <div class="exec-step-content">
                    <span class="exec-step-label" style="color:${meta.color}">${meta.label}</span>
                    ${!isLast ? '<span class="exec-step-done"><i class="fa-solid fa-check"></i> Done</span>' : '<span class="exec-step-running">Running…</span>'}
                </div>
            </div>`;
        });
        return `<div class="exec-pipeline">${items}</div>`;
    }

    const QUERY_TYPE_LABELS = {
        permit_evaluation:   { icon: "fa-building",        label: "Permit Evaluation" },
        legal_question:      { icon: "fa-scale-balanced",  label: "Legal Question" },
        compliance_audit:    { icon: "fa-clipboard-check", label: "Compliance Audit" },
        precedent_research:  { icon: "fa-gavel",           label: "Precedent Research" },
        document_review:     { icon: "fa-file-magnifying-glass", label: "Document Review" },
        noc_clearance:       { icon: "fa-stamp",           label: "NOC / Clearance" },
        setback_zone_query:  { icon: "fa-ruler-combined",  label: "Setback / Zone Query" },
        go_interpretation:   { icon: "fa-scroll",          label: "GO Interpretation" },
        appeal_or_challenge: { icon: "fa-triangle-exclamation", label: "Appeal / Challenge" },
        general:             { icon: "fa-circle-question", label: "General Query" },
    };

    function buildPlanHtml() {
        // ── Rich plan card (structured LegalReasoningPlan) ────────────────────
        if (legalPlanData && legalPlanData.steps && legalPlanData.steps.length > 0) {
            const qt  = legalPlanData.query_type || "general";
            const qm  = QUERY_TYPE_LABELS[qt] || QUERY_TYPE_LABELS.general;
            const complexity = legalPlanData.estimated_complexity || "medium";
            const complexityColor = { low: "#10B981", medium: "#F59E0B", high: "#EF4444" }[complexity] || "#8B5CF6";

            // Applicable laws pills
            const lawsPills = (legalPlanData.applicable_laws || []).map(law =>
                `<span class="plan-law-pill"><i class="fa-solid fa-book-open-reader"></i> ${law}</span>`
            ).join("");

            // Strategy badge
            const strategyLabel = {
                statutory_first: "📜 Statutory First",
                go_focused:      "📋 GO Focused",
                precedent_led:   "⚖️ Precedent Led",
                balanced:        "🔄 Balanced",
            }[legalPlanData.retrieval_strategy] || legalPlanData.retrieval_strategy;

            // Step cards
            const stepCards = legalPlanData.steps.map(step => `
                <div class="plan-step-card">
                    <div class="plan-step-card-header">
                        <span class="plan-step-num">${step.step_id}</span>
                        <span class="plan-step-action">${step.action}</span>
                    </div>
                    ${step.legal_focus ? `<div class="plan-step-focus"><i class="fa-solid fa-bookmark" style="color:#8B5CF6"></i> ${step.legal_focus}</div>` : ""}
                    ${step.target_sources && step.target_sources.length ? `<div class="plan-step-sources">${step.target_sources.map(s => `<span class="plan-source-tag">${s}</span>`).join("")}</div>` : ""}
                    ${step.expected_output ? `<div class="plan-step-output"><i class="fa-solid fa-arrow-right" style="color:#10B981; font-size:0.75rem;"></i> ${step.expected_output}</div>` : ""}
                </div>
            `).join("");

            return `<div class="plan-trace plan-trace-rich">
                <div class="plan-trace-header">
                    <i class="fa-solid fa-${qm.icon}"></i> ${qm.label}
                    <span class="plan-complexity-badge" style="background:${complexityColor}22; color:${complexityColor}; border-color:${complexityColor}44">${complexity.toUpperCase()} COMPLEXITY</span>
                </div>
                ${legalPlanData.summary ? `<div class="plan-summary">${legalPlanData.summary}</div>` : ""}
                ${lawsPills ? `<div class="plan-laws-row">${lawsPills}</div>` : ""}
                <div class="plan-strategy"><i class="fa-solid fa-route"></i> Strategy: ${strategyLabel}</div>
                <div class="plan-steps-grid">${stepCards}</div>
            </div>`;
        }

        // ── Fallback: flat list (legacy / clarification pending) ──────────────
        if (planSteps.length === 0) return "";
        const items = planSteps.map((step, i) =>
            `<li class="plan-step"><span class="plan-step-num">${i + 1}</span><span class="plan-step-text">${step}</span></li>`
        ).join("");
        return `<div class="plan-trace">
            <div class="plan-trace-header"><i class="fa-solid fa-list-check"></i> Reasoning Plan</div>
            <ol class="plan-step-list">${items}</ol>
        </div>`;
    }
    
    function updateDisplay() {
        const streamHtml = buildPipelineHtml() + buildPlanHtml() + flagsHtml;
        let finalHtml = "";
        
        if (streamHtml) {
            const isStreamExpanded = !isDone;
            const toggleIcon = isStreamExpanded ? "fa-chevron-up" : "fa-chevron-down";
            const displayStyle = isStreamExpanded ? "block" : "none";
            
            finalHtml += `
            <div class="stream-accordion">
                <div class="stream-accordion-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'; const i = this.querySelector('i.fa-solid:last-child'); if(i.classList.contains('fa-chevron-down')) { i.classList.replace('fa-chevron-down', 'fa-chevron-up'); } else { i.classList.replace('fa-chevron-up', 'fa-chevron-down'); }">
                    <span><i class="fa-solid fa-bolt"></i> Execution Stream</span>
                    <i class="fa-solid ${toggleIcon}"></i>
                </div>
                <div class="stream-accordion-body" style="display: ${displayStyle};">
                    ${streamHtml}
                </div>
            </div>`;
        }

        if (mdText) {
            finalHtml += `<div class="markdown-body">${marked.parse(mdText)}</div>`;
        }
        if (sourcesHtml) {
            finalHtml += sourcesHtml;
        }
        
        // Add copy button
        finalHtml += `<button class="copy-btn assistant-copy" onclick="copyToClipboard(this)" title="Copy response"><i class="fa-regular fa-copy"></i></button>`;
        
        msgContent.innerHTML = finalHtml;
        const feed = document.getElementById("chatFeed");
        feed.scrollTop = feed.scrollHeight;
    }

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        
        for (let line of lines) {
            if (line.startsWith("data: ")) {
                const dataStr = line.replace("data: ", "").trim();
                if (!dataStr) continue;
                try {
                    const data = JSON.parse(dataStr);
                    if (data.type === "node_status") {
                        liveNodes.add(data.node);
                        updateDisplay();
                    } else if (data.type === "plan") {
                        planSteps = data.content;
                        updateDisplay();
                    } else if (data.type === "legal_plan") {
                        legalPlanData = data.content;
                        updateDisplay();
                    } else if (data.type === "clarification") {
                        document.body.dataset.pendingClarification = "true";
                        isDone = true;
                        let html = `<p><i class="fa-solid fa-triangle-exclamation" style="color:var(--warning)"></i> <strong>Clarification Required</strong></p>`;
                        html += `<p>${data.content}</p>`;
                        msgContent.innerHTML = html;
                    } else if (data.type === "flags") {
                        flagsHtml = `<div style="margin: 12px 0;">`;
                        data.content.forEach((r) => {
                            flagsHtml += `<div class="risk-badge ${r.severity}">
                                <i class="fa-solid fa-triangle-exclamation"></i>
                                <span>${r.message}</span>
                            </div>`;
                        });
                        flagsHtml += `</div>`;
                        updateDisplay();
                    } else if (data.type === "sources") {
                        sourcesHtml = buildSourcesHtml(data.content);
                        // Don't call updateDisplay here — it renders after tokens start
                    } else if (data.type === "token") {
                        mdText += data.content;
                        updateDisplay();
                    } else if (data.type === "done") {
                        isDone = true;
                        updateDisplay();
                        loadThreads();
                    } else if (data.type === "error") {
                        isDone = true;
                        msgContent.innerHTML += `<p style="color:var(--danger)">Error: ${data.content}</p>`;
                    }
                } catch(e) {
                    console.error("Error parsing stream JSON", e, dataStr);
                }
            }
        }
    }
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
