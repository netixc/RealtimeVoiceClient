// Voice Chat UI - Browser Audio Mode
// This version uses browser microphone/speakers directly

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

// Agent UI elements
const agentList = document.getElementById("agentList");
const createAgentBtn = document.getElementById("createAgentBtn");
const eventStream = document.getElementById("eventStream");

let chatHistory = [];
let typingUser = "";
let typingAssistant = "";
let micEnabled = true;
let agents = [];
let events = [];
let audioClient = null;

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

function addUserMessage(text) {
  chatHistory.push({ role: "user", content: text });
  typingUser = "";
  renderMessages();
}

function addAssistantMessage(text) {
  chatHistory.push({ role: "assistant", content: text });
  typingAssistant = "";
  renderMessages();
}

// Button handlers
startBtn.onclick = async () => {
  try {
    setStatus("Initializing audio...", true);
    startBtn.disabled = true;

    // Get configuration from backend
    const config = await eel.get_config()();
    console.log('Got config:', config);

    // Create browser audio client
    audioClient = new BrowserAudioClient(config.backend_url, config.api_key);

    // Set up callbacks
    audioClient.onStatusChange = (status) => {
      console.log('Status:', status);
      switch (status) {
        case 'connected':
          setStatus("Connected", true);
          break;
        case 'recording':
          setStatus("Listening...", true);
          break;
        case 'speaking':
          setStatus("You are speaking", true);
          break;
        case 'ready':
          setStatus("Ready", true);
          break;
        default:
          setStatus(status, true);
      }
    };

    audioClient.onTranscript = (text) => {
      console.log('Transcript:', text);
      addUserMessage(text);
    };

    audioClient.onResponse = (text, isDone) => {
      if (isDone) {
        addAssistantMessage(text);
      } else {
        typingAssistant = text;
        renderMessages();
      }
    };

    audioClient.onError = (error) => {
      console.error('Audio client error:', error);
      setStatus("Error: " + error, false);
      alert('Error: ' + error);
    };

    // Initialize audio
    const initialized = await audioClient.initialize();
    if (!initialized) {
      throw new Error('Failed to initialize audio');
    }

    // Connect to backend
    await audioClient.connect();

    // Start recording
    await audioClient.startRecording();

    // Update UI
    stopBtn.disabled = false;
    textInput.disabled = false;
    sendBtn.disabled = false;
    setStatus("Listening...", true);

  } catch (error) {
    console.error('Failed to start:', error);
    setStatus("Failed to start: " + error.message, false);
    startBtn.disabled = false;
    alert('Failed to start audio client: ' + error.message);
  }
};

stopBtn.onclick = async () => {
  setStatus("Stopping...", false);
  stopBtn.disabled = true;

  if (audioClient) {
    audioClient.disconnect();
    audioClient = null;
  }

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
};

sendBtn.onclick = async () => {
  const text = textInput.value.trim();
  if (!text) return;

  // Clear input
  textInput.value = "";

  // Add to UI
  addUserMessage(text);

  // Send via audio client if connected
  if (audioClient) {
    audioClient.sendText(text);
  }
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
    if (audioClient) {
      audioClient.setMuted(false);
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
    if (audioClient) {
      audioClient.setMuted(true);
    }
  }
};

// ------------------------------------------------------------------ #
// Tab Management
// ------------------------------------------------------------------ #

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    // Remove active class from all tabs and panels
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));

    // Add active class to clicked tab
    tab.classList.add('active');

    // Show corresponding panel
    const tabName = tab.dataset.tab;
    const panel = document.getElementById(tabName + 'Panel');
    if (panel) {
      panel.classList.add('active');

      // Load agents when switching to agents tab
      if (tabName === 'agents') {
        loadAgents();
      }
    }
  });
});

// ------------------------------------------------------------------ #
// Agent Management
// ------------------------------------------------------------------ #

async function loadAgents() {
  try {
    const result = await eel.ui_list_agents()();
    if (result && result.ok) {
      agents = result.agents || [];
      renderAgents();
    }
  } catch (e) {
    console.error('Failed to load agents:', e);
  }
}

function renderAgents() {
  if (agents.length === 0) {
    agentList.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
        </svg>
        <p>No agents created yet</p>
        <p style="font-size: 14px; margin-top: 8px;">Create an agent to get started</p>
      </div>
    `;
    return;
  }

  agentList.innerHTML = agents.map(agent => `
    <div class="agent-card">
      <div class="agent-header">
        <span class="agent-name">${escapeHtml(agent.name)}</span>
        <span class="agent-status ${agent.status}">${agent.status || 'active'}</span>
      </div>
      <div class="agent-meta">
        <strong>Type:</strong> ${agent.tool} - ${agent.type}<br>
        <strong>Created:</strong> ${new Date(agent.created_at).toLocaleString()}<br>
        ${agent.expires_at ? `<strong>Expires:</strong> ${new Date(agent.expires_at).toLocaleString()}` : ''}
      </div>
      <div class="agent-actions">
        <button class="agent-btn command" onclick="commandAgent('${agent.name}')">📝 Command</button>
        <button class="agent-btn delete" onclick="deleteAgent('${agent.name}')">🗑️ Delete</button>
      </div>
    </div>
  `).join('');
}

async function commandAgent(agentName) {
  const prompt = window.prompt(`Enter command for ${agentName}:`);
  if (!prompt) return;

  try {
    const result = await eel.ui_command_agent(agentName, prompt)();
    if (result.ok) {
      alert(`Command sent to ${agentName}!\nOperator file: ${result.operator_file || 'N/A'}`);
      addObservabilityEvent({
        type: 'agent_command',
        agent_name: agentName,
        prompt: prompt.substring(0, 100),
        timestamp: new Date().toISOString()
      });
    } else {
      alert(`Error: ${result.error}`);
    }
  } catch (e) {
    console.error('Failed to command agent:', e);
    alert('Failed to send command');
  }
}

async function deleteAgent(agentName) {
  if (!confirm(`Delete agent "${agentName}"?`)) return;

  try {
    const result = await eel.ui_delete_agent(agentName)();
    if (result.ok) {
      loadAgents();
      addObservabilityEvent({
        type: 'agent_deleted',
        agent_name: agentName,
        timestamp: new Date().toISOString()
      });
    } else {
      alert(`Error: ${result.error}`);
    }
  } catch (e) {
    console.error('Failed to delete agent:', e);
    alert('Failed to delete agent');
  }
}

createAgentBtn.onclick = async () => {
  const tool = prompt('Agent tool (claude_code, gemini, agent_zero):');
  if (!tool) return;

  const agentType = prompt('Agent type (agentic_coding, agentic_browsing, agentic_general):');
  if (!agentType) return;

  const agentName = prompt('Agent name:');
  if (!agentName) return;

  try {
    const result = await eel.ui_create_agent(tool, agentType, agentName, 24)();
    if (result.ok) {
      loadAgents();
      addObservabilityEvent({
        type: 'agent_created',
        agent_name: agentName,
        tool: tool,
        agent_type: agentType,
        timestamp: new Date().toISOString()
      });
    } else {
      alert(`Error: ${result.error}`);
    }
  } catch (e) {
    console.error('Failed to create agent:', e);
    alert('Failed to create agent');
  }
};

// ------------------------------------------------------------------ #
// Observability Events
// ------------------------------------------------------------------ #

function addObservabilityEvent(event) {
  events.unshift(event);
  if (events.length > 100) events.pop(); // Keep last 100 events
  renderEvents();
}

function renderEvents() {
  if (events.length === 0) {
    eventStream.innerHTML = `
      <div class="empty-state" style="color: #888;">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
        </svg>
        <p>No events yet</p>
        <p style="font-size: 12px; margin-top: 8px;">Events will appear here when agents are active</p>
      </div>
    `;
    return;
  }

  eventStream.innerHTML = events.map(event => {
    const timestamp = new Date(event.timestamp).toLocaleTimeString();
    const eventClass = event.type || 'info';
    return `
      <div class="event ${eventClass}">
        <div class="event-type">${event.type || 'event'}</div>
        <div class="event-timestamp">${timestamp}</div>
        <div class="event-data">${JSON.stringify(event, null, 2)}</div>
      </div>
    `;
  }).join('');

  // Scroll to bottom
  eventStream.scrollTop = eventStream.scrollHeight;
}

// Initial render
renderMessages();
setStatus("Ready - Click Start to begin", false);
