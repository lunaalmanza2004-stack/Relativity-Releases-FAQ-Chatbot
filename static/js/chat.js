let CURRENT_VERSION = (window.APP_VERSION || "RelativityOne");
let CURRENT_MODE = "quick";
let LAST_ANSWER = "";
let CONVERSATION = [];

const chatWindow = document.getElementById("chatWindow");
const msgInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const typingIndicator = document.getElementById("typingIndicator");
const modeSelect = document.getElementById("modeSelect");
const downloadConvoBtn = document.getElementById("downloadConvo");
const shareGmail = document.getElementById("shareGmail");
const shareWhatsApp = document.getElementById("shareWhatsApp");
const shareTelegram = document.getElementById("shareTelegram");
const sndUser = document.getElementById("sndUser");
const sndBot = document.getElementById("sndBot");
const changeAvatarBtn = document.getElementById("changeAvatarBtn");
const avatarInput = document.getElementById("avatarInput");
const userAvatarImg = document.getElementById("userAvatar");
const downloadPDFBtn = document.getElementById("downloadPDF");
const refreshHistoryBtn = document.getElementById("refreshHistory");
const historyList = document.getElementById("historyList");
const micBtn = document.getElementById("micBtn");
const voiceStatusInline = document.getElementById("voiceStatusInline");
const guidedSuggestions = document.getElementById("guidedSuggestions");
const versionSelect = document.getElementById("versionSelect");
const configBtn = document.getElementById("configBtn");
const configMenu = document.getElementById("configMenu");
const themeSelect = document.getElementById("themeSelect");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");
const closeAccountBtn = document.getElementById("closeAccountBtn");

function toast(html) {
  const div = document.createElement("div");
  div.className = "tiny toast";
  div.innerHTML = html;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

// Version navigation
versionSelect && versionSelect.addEventListener("change", () => {
  const slug = versionSelect.value;
  window.location.href = `/v/${slug}`;
});

// Config gear toggle
if (configBtn && configMenu) {
  configBtn.addEventListener("click", () => {
    const opened = configMenu.classList.toggle("open");
    configBtn.setAttribute("aria-expanded", opened ? "true" : "false");
  });
  document.addEventListener("click", (e) => {
    if (!configMenu.contains(e.target) && e.target !== configBtn) {
      configMenu.classList.remove("open");
      configBtn.setAttribute("aria-expanded", "false");
    }
  });
}

// Theme
if (themeSelect) {
  const saved = localStorage.getItem("chatTheme") || "theme-purple";
  document.body.className = saved;
  themeSelect.value = saved;
  themeSelect.addEventListener("change", () => {
    document.body.className = themeSelect.value;
    localStorage.setItem("chatTheme", themeSelect.value);
  });
}

// Avatar upload
changeAvatarBtn && changeAvatarBtn.addEventListener("click", () => avatarInput.click());
avatarInput && avatarInput.addEventListener("change", async () => {
  if (!avatarInput.files || !avatarInput.files[0]) return;
  const formData = new FormData();
  formData.append("avatar", avatarInput.files[0]);
  try {
    const r = await fetch("/api/upload_avatar", { method: "POST", body: formData });
    const j = await r.json();
    if (j.ok && j.url) {
      userAvatarImg.src = j.url;
      localStorage.setItem("userAvatarUrl", j.url);
      toast("Photo updated.");
    } else {
      toast(j.error || "Could not update photo.");
    }
  } catch {
    toast("Upload failed.");
  }
});

// Clear chat history (this version)
clearHistoryBtn && clearHistoryBtn.addEventListener("click", async () => {
  if (!confirm("Clear chat history for this version?")) return;
  try {
    const r = await fetch("/api/clear_history", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ version: CURRENT_VERSION })
    });
    const j = await r.json();
    if (j.ok) {
      historyList.innerHTML = `<div class="tiny">History cleared.</div>`;
      CONVERSATION = [];
      const nodes = chatWindow.querySelectorAll(".msg, .toast");
      nodes.forEach(n => n.remove());
      toast("Chat reset.");
    } else {
      toast(j.error || "Could not clear history.");
    }
  } catch {
    toast("Failed to clear history.");
  }
});

// Close account
closeAccountBtn && closeAccountBtn.addEventListener("click", async () => {
  if (!confirm("This will permanently delete your account and history. Continue?")) return;
  try {
    const r = await fetch("/api/delete_account", { method: "POST" });
    const j = await r.json();
    if (j.ok) window.location.href = "/login";
    else toast(j.error || "Could not close account.");
  } catch {
    toast("Request failed.");
  }
});

// Modes
modeSelect.addEventListener("change", () => {
  CURRENT_MODE = modeSelect.value;
  if (CURRENT_MODE === "guided") {
    msgInput.placeholder = "Search sections (Guided)…";
    preloadSections();
  } else {
    guidedSuggestions.classList.add("hidden");
    msgInput.placeholder = "Ask about Relativity release notes...";
  }
});

// Messages
function addMessage(role, text, citations=[]) {
  const tpl = document.getElementById(role === "user" ? "msgUserTpl" : "msgBotTpl");
  const node = tpl.content.cloneNode(true);
  if (role === "user") node.querySelector(".avatar").src = userAvatarImg.src;
  const bubble = node.querySelector(".bubble");
  bubble.querySelector(".text").innerHTML = text.replace(/\n/g, "<br/>");

  // Citations
  if (role === "bot" && citations && citations.length) {
    const ctn = bubble.querySelector(".citations");
    ctn.innerHTML = "";
    citations.forEach(c => {
      const a = document.createElement("a");
      a.href = c.url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = "Source";
      ctn.appendChild(a);
    });
  }

  // ✅ Bocina TTS en cada mensaje del bot
  if (role === "bot") {
    const btn = document.createElement("button");
    btn.className = "speak-btn";
    btn.title = "Read aloud";
    btn.innerHTML = `<img src="/static/img/speaker.svg" alt="Read aloud">`;
    btn.addEventListener("click", () => speakText(stripTags(text)));
    bubble.appendChild(btn);
  }

  chatWindow.appendChild(node);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function startTyping() {
  typingIndicator.classList.remove("hidden");
  sndBot && sndBot.play && sndBot.play().catch(()=>{});
}
function stopTyping() {
  typingIndicator.classList.add("hidden");
  if (sndBot) { try { sndBot.pause(); sndBot.currentTime = 0; } catch {} }
}

sendBtn.addEventListener("click", sendMessage);
msgInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;
  addMessage("user", text);
  CONVERSATION.push({ role:"user", content:text, version: CURRENT_VERSION });
  msgInput.value = "";
  sndUser && sndUser.play && sndUser.play().catch(()=>{});
  startTyping();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, version: CURRENT_VERSION, mode: CURRENT_MODE })
    });
    const data = await res.json();
    stopTyping();
    if (data.error) { addMessage("bot", "Sorry, something went wrong. Please try again."); return; }
    LAST_ANSWER = data.answer || "";
    addMessage("bot", sanitize(data.answer || ""), data.citations || []);
    CONVERSATION.push({ role:"assistant", content:data.answer || "", citations:data.citations || [], confidence:data.confidence });
    if (data.should_collect_contact) {
      addMessage("bot", `If you'd like deeper help, share your contact info (name, email, organization). We'll follow up.`, []);
    }
    fetchHistory();
  } catch (e) {
    stopTyping();
    addMessage("bot", "Network error. Please try again.");
  }
}

function sanitize(s){
  return s.replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll("&lt;br/&gt;","<br/>");
}
function stripTags(s){ return (s||"").replace(/<[^>]+>/g," ").replace(/\s+/g," ").trim(); }

// Guided suggestions
let ALL_SECTIONS = [];
msgInput.addEventListener("focus", () => {
  if (CURRENT_MODE === "guided") {
    renderSuggestions("");
    guidedSuggestions.classList.remove("hidden");
  }
});
msgInput.addEventListener("input", () => {
  if (CURRENT_MODE !== "guided") return;
  const q = msgInput.value.trim().toLowerCase();
  renderSuggestions(q);
});
document.addEventListener("click", (e) => {
  if (!guidedSuggestions.contains(e.target) && e.target !== msgInput) {
    guidedSuggestions.classList.add("hidden");
  }
});

async function preloadSections() {
  if (CURRENT_MODE !== "guided") return;
  try {
    const r = await fetch(`/api/sections?version=${encodeURIComponent(CURRENT_VERSION)}`);
    const j = await r.json();
    ALL_SECTIONS = j.sections || [];
  } catch { ALL_SECTIONS = []; }
}
function renderSuggestions(filterText) {
  const q = (filterText || "").toLowerCase();
  const list = q ? ALL_SECTIONS.filter(s => (s.heading || "").toLowerCase().includes(q)) : ALL_SECTIONS.slice();
  const limited = list.slice(0, 60);
  guidedSuggestions.innerHTML = limited.map(s => `
    <button class="sugg-item" role="option" data-h="${escapeAttr(s.heading)}" title="${escapeAttr(s.heading)}">
      <span class="sugg-dot"></span>${escapeHtml(s.heading)}
    </button>
  `).join("");
  guidedSuggestions.querySelectorAll(".sugg-item").forEach(btn => {
    btn.addEventListener("click", () => {
      const h = btn.getAttribute("data-h");
      msgInput.value = `Summarize the "${h}" section.`;
      guidedSuggestions.classList.add("hidden");
      msgInput.focus();
    });
  });
}

// Save JSON / PDF
downloadConvoBtn && downloadConvoBtn.addEventListener("click", async () => {
  const stamp = new Date().toISOString().replace(/[:.]/g,"-");
  const payload = { conversation: CONVERSATION, version: CURRENT_VERSION, timestamp: stamp };
  try {
    await fetch("/api/save_conversation", {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)
    });
  } catch {}
  const blob = new Blob([JSON.stringify(CONVERSATION, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `conversation_${CURRENT_VERSION}_${stamp}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
});
downloadPDFBtn && downloadPDFBtn.addEventListener("click", async () => {
  try {
    const r = await fetch("/api/save_conversation_pdf", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation: CONVERSATION, version: CURRENT_VERSION })
    });
    if (!r.ok) { addMessage("bot", "Could not generate PDF."); return; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `conversation_${CURRENT_VERSION}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch { addMessage("bot", "PDF export failed."); }
});

// Share
function urlEncode(s){ return encodeURIComponent(s); }
shareGmail && shareGmail.addEventListener("click", () => {
  const subject = `Relativity Release Notes — Shared Answer`;
  const body = LAST_ANSWER || "No answer to share yet.";
  window.open(`mailto:?subject=${urlEncode(subject)}&body=${urlEncode(body)}`,"_blank");
});
shareWhatsApp && shareWhatsApp.addEventListener("click", () => {
  const text = LAST_ANSWER || "No answer yet.";
  window.open(`https://wa.me/?text=${urlEncode(text)}`,"_blank");
});
shareTelegram && shareTelegram.addEventListener("click", () => {
  const text = LAST_ANSWER || "No answer yet.";
  window.open(`https://t.me/share/url?url=&text=${urlEncode(text)}`,"_blank");
});

// History banner
async function fetchHistory(fromButton=false) {
  if (!historyList) return;
  historyList.innerHTML = fromButton ? `<div class="tiny">Refreshing…</div>` : `<div class="tiny">Loading…</div>`;
  try {
    const r = await fetch(`/api/history?version=${encodeURIComponent(CURRENT_VERSION)}`);
    const j = await r.json();
    const items = j.items || [];
    if (!items.length) {
      historyList.innerHTML = `<div class="empty-history">
        <div class="eh-title">No messages yet</div>
        <div class="eh-sub">Your conversation will appear here.</div>
      </div>`;
      return;
    }
    historyList.innerHTML = items.slice(-60).map((it) => {
      const who = it.role === "user" ? "You" : "Bot";
      const content = escapeHtml((it.content || "").slice(0, 160)).replace(/\n/g," ");
      const ts = escapeHtml(it.ts || "");
      return `
        <div class="hb-row">
          <div class="hb-badge ${it.role}">${who}</div>
          <div class="hb-text">${content}</div>
          <div class="hb-time">${ts}</div>
        </div>
      `;
    }).join("");
  } catch {
    historyList.innerHTML = `<div class="tiny">Could not load history.</div>`;
  }
}
refreshHistoryBtn && refreshHistoryBtn.addEventListener("click", (e) => {
  e.preventDefault();
  refreshHistoryBtn.disabled = true;
  fetchHistory(true).finally(() => { refreshHistoryBtn.disabled = false; });
});

// ===== Voice (record) =====
let recognition, isListening = false;
let mediaStream = null, mediaRecorder = null, audioChunks = [];
const isSecure = () => window.isSecureContext || ["localhost","127.0.0.1"].includes(location.hostname);

// Web Speech Recognition (si está disponible)
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.continuous = false;

  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    msgInput.value = text;
    voiceStatusInline.textContent = "Recognized: " + text;
    sendMessage();
  };
  recognition.onerror = (e) => { voiceStatusInline.textContent = "Speech error: " + e.error; };
  recognition.onend = () => { isListening = false; micBtn.classList.remove("on"); setTimeout(()=>voiceStatusInline.textContent = "", 1200); };

  micBtn.addEventListener("click", async () => {
    if (isListening) { recognition.stop(); return; }
    try {
      recognition.start();
      isListening = true;
      micBtn.classList.add("on");
      voiceStatusInline.textContent = "Listening…";
    } catch (e) {
      if (!isSecure()) {
        voiceStatusInline.textContent = "Use HTTPS or localhost to enable microphone access.";
        return;
      }
      voiceStatusInline.textContent = "Speech recognition not available in this browser.";
    }
  });
} else {
  // Fallback recorder -> /api/stt (HTTPS/localhost requerido)
  micBtn.addEventListener("click", async () => {
    if (!isSecure()) { voiceStatusInline.textContent = "Use HTTPS or localhost to enable microphone access."; return; }
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      voiceStatusInline.textContent = "Recording is not supported by this browser.";
      return;
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop(); return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      try { mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" }); }
      catch { mediaRecorder = new MediaRecorder(mediaStream); }
    } catch {
      voiceStatusInline.textContent = "Microphone permission denied.";
      return;
    }
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      const fd = new FormData();
      const ext = blob.type.includes("ogg") ? "ogg" : (blob.type.includes("wav") ? "wav" : "webm");
      fd.append("audio", blob, `question.${ext}`);
      voiceStatusInline.textContent = "Transcribing...";
      try {
        const r = await fetch("/api/stt", { method: "POST", body: fd });
        const j = await r.json();
        if (j.ok) {
          msgInput.value = j.text || "";
          voiceStatusInline.textContent = "Recognized. Sending…";
          if (msgInput.value.trim()) sendMessage();
        } else {
          voiceStatusInline.textContent = j.error || "Speech-to-text failed.";
        }
      } catch {
        voiceStatusInline.textContent = "STT request failed.";
      } finally {
        if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
        micBtn.classList.remove("on");
        setTimeout(()=>voiceStatusInline.textContent="", 1500);
      }
    };
    mediaRecorder.start();
    micBtn.classList.add("on");
    voiceStatusInline.textContent = "Recording… click again to stop";
  });
}

// ===== Text-to-Speech (leer en voz alta) =====
let currentUtterance = null;
function speakText(text) {
  if (!("speechSynthesis" in window)) { toast("Text-to-Speech not supported in this browser."); return; }
  // Si ya está hablando, parar y volver a comenzar con el nuevo
  window.speechSynthesis.cancel();
  currentUtterance = new SpeechSynthesisUtterance(text);
  currentUtterance.lang = "en-US";
  currentUtterance.rate = 1;
  currentUtterance.pitch = 1;
  window.speechSynthesis.speak(currentUtterance);
}

// Utils
function escapeHtml(s){ return s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"); }
function escapeAttr(s){ return (s||"").replaceAll('"','&quot;'); }

// Init
(function init(){
  const cachedAvatar = localStorage.getItem("userAvatarUrl");
  if (cachedAvatar) userAvatarImg.src = cachedAvatar;
  fetchHistory();
})();
