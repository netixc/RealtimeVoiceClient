// Voice Chat UI - Eel Integration

const statusDiv = document.getElementById("statusText");
const statusDot = document.getElementById("statusDot");
const messagesDiv = document.getElementById("messages");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const clearBtn = document.getElementById("clearBtn");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const toggleMicBtn = document.getElementById("toggleMicBtn");
const micText = document.getElementById("micText");
const micIcon = document.getElementById("micIcon");

let chatHistory = [];
let typingUser = "";
let typingAssistant = "";
let micEnabled = true;

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
  textInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
  // toggleMicBtn stays enabled always
}

// Button handlers
startBtn.onclick = async () => {
  setStatus("Starting...", true);
  startBtn.disabled = true;
  stopBtn.disabled = false;
  textInput.disabled = false;
  sendBtn.disabled = false;

  // Call Python function with current mic state
  await eel.start_voice_chat(micEnabled)();
};

stopBtn.onclick = async () => {
  setStatus("Stopping...", false);
  stopBtn.disabled = true;

  // Call Python function
  await eel.stop_voice_chat()();

  startBtn.disabled = false;
  textInput.disabled = true;
  sendBtn.disabled = true;
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

sendBtn.onclick = async () => {
  const text = textInput.value.trim();
  if (!text) return;

  // Clear input
  textInput.value = "";

  // Send to Python backend (it will be added to UI when server confirms)
  await eel.send_text_message(text)();
};

// Handle Enter key in text input
textInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter' && !textInput.disabled) {
    sendBtn.onclick();
  }
});

toggleMicBtn.onclick = () => {
  micEnabled = !micEnabled;

  if (micEnabled) {
    // Enable mic
    toggleMicBtn.classList.remove('muted');
    micText.textContent = 'Mic On';
    micIcon.innerHTML = `
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" fill="currentColor"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <path d="M12 19v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    `;
    // Only call backend if client is running
    if (stopBtn.disabled === false) {
      eel.toggle_microphone(true)();
    }
  } else {
    // Disable mic (muted)
    toggleMicBtn.classList.add('muted');
    micText.textContent = 'Mic Off';
    micIcon.innerHTML = `
      <path d="M2 2l20 20M15 9.34V5a3 3 0 0 0-5.94-.6M9 9v3a3 3 0 0 0 5.12 2.12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <path d="M12 19v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    `;
    // Only call backend if client is running
    if (stopBtn.disabled === false) {
      eel.toggle_microphone(false)();
    }
  }
};

// Initial render
renderMessages();
setStatus("Ready", false);
