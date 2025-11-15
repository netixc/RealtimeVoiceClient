// Voice Chat UI - Eel Integration

const statusDiv = document.getElementById("statusText");
const statusDot = document.getElementById("statusDot");
const messagesDiv = document.getElementById("messages");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const clearBtn = document.getElementById("clearBtn");

let chatHistory = [];
let typingUser = "";
let typingAssistant = "";

// Update status display
function setStatus(text, active = false) {
  statusDiv.textContent = text;
  if (active) {
    statusDot.classList.add('active');
  } else {
    statusDot.classList.remove('active');
  }
}

// Render messages
function renderMessages() {
  messagesDiv.innerHTML = "";
  chatHistory.forEach(msg => {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${msg.role}`;
    bubble.textContent = msg.content;
    messagesDiv.appendChild(bubble);
  });

  if (typingUser) {
    const typing = document.createElement("div");
    typing.className = "bubble user typing";
    typing.innerHTML = escapeHtml(typingUser) + ' <span style="opacity:.6;">✏️</span>';
    messagesDiv.appendChild(typing);
  }

  if (typingAssistant) {
    const typing = document.createElement("div");
    typing.className = "bubble assistant typing";
    typing.innerHTML = escapeHtml(typingAssistant) + ' <span style="opacity:.6;">✏️</span>';
    messagesDiv.appendChild(typing);
  }

  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function escapeHtml(str) {
  return (str ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Exposed functions that Python can call
eel.expose(add_user_message);
function add_user_message(text) {
  chatHistory.push({ role: "user", content: text });
  typingUser = "";
  renderMessages();
}

eel.expose(add_assistant_message);
function add_assistant_message(text) {
  chatHistory.push({ role: "assistant", content: text });
  typingAssistant = "";
  renderMessages();
}

eel.expose(set_user_typing);
function set_user_typing(text) {
  typingUser = text || "";
  renderMessages();
}

eel.expose(set_assistant_typing);
function set_assistant_typing(text) {
  typingAssistant = text || "";
  renderMessages();
}

eel.expose(update_status);
function update_status(text, active) {
  setStatus(text, active);
}

eel.expose(enable_controls);
function enable_controls(enabled) {
  startBtn.disabled = !enabled;
  stopBtn.disabled = enabled;
}

// Button handlers
startBtn.onclick = async () => {
  setStatus("Starting...", true);
  startBtn.disabled = true;
  stopBtn.disabled = false;

  // Call Python function
  await eel.start_voice_chat()();
};

stopBtn.onclick = async () => {
  setStatus("Stopping...", false);
  stopBtn.disabled = true;

  // Call Python function
  await eel.stop_voice_chat()();

  startBtn.disabled = false;
  setStatus("Stopped", false);
};

clearBtn.onclick = () => {
  chatHistory = [];
  typingUser = "";
  typingAssistant = "";
  renderMessages();

  // Optionally notify Python
  eel.clear_conversation();
};

// Initial render
renderMessages();
setStatus("Ready", false);
