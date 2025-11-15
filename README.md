# Multi-Agent Voice Orchestrator

A real-time voice chat orchestrator for OpenAI Realtime API with multi-agent management, DTLN-aec echo cancellation, and integrated observability.

**Voice-control multiple AI agents** (Claude Code, Gemini Browser, Agent Zero) through natural conversation or text, with real-time monitoring and a beautiful desktop UI.

This client is designed to work with the [RealtimeVoiceChat](https://github.com/netixc/RealtimeVoiceChat) backend server.

## Features

### 🎙️ Voice & Communication
- **Real-time voice conversation** with AI assistant using OpenAI Realtime API
- **DTLN-aec echo cancellation** - Deep learning based acoustic echo cancellation
- **Full-duplex communication** - Interrupt the AI anytime while it's speaking
- **Voice OR Text input** - Speak or type your commands
- **Client-side VAD** - Voice activity detection for accurate speech recognition
- **Microphone toggle** - Mute/unmute before or during sessions
- **Low latency** - ~30ms audio processing

### 🤖 Multi-Agent Orchestration
- **Claude Code Agents** - Software development using Claude CLI (subscription-based)
- **Gemini Browser Agents** - Web automation with Playwright + Gemini AI
- **Agent Zero Agents** - General-purpose AI tasks via API
- **Function Calling** - AI automatically creates and manages agents via tools
- **Agent Registry** - Persistent agent tracking with metadata
- **Background Execution** - Async agent task processing
- **Operator Logs** - Detailed execution logs for each agent command

### 🖥️ Desktop UI
- **3-Tab Interface** - Chat, Agents, Events
- **Agent Management Panel** - Create, command, delete agents with visual cards
- **Observability Dashboard** - Real-time event stream with color-coded logs
- **Beautiful Design** - Modern UI with Inter font and smooth animations
- **Empty States** - Helpful guidance when no agents or events exist

## Requirements

### Core
- Python 3.9 or higher
- [Astral uv](https://docs.astral.sh/uv/) - Fast Python package manager
- macOS (tested) or Linux
- Microphone and speakers
- Backend server: [RealtimeVoiceChat](https://github.com/netixc/RealtimeVoiceChat) or any OpenAI Realtime API compatible server

### Agent-Specific (Optional)
- **Claude Code**: Claude CLI (`npm install -g @anthropic-ai/claude-code`) + subscription
- **Gemini Browser**: `pip install google-generativeai playwright` + `playwright install` + GEMINI_API_KEY
- **Agent Zero**: `pip install requests` + Agent Zero API endpoint

## Installation

### Quick Start (npm)

```bash
# Clone the repository
git clone --recurse-submodules https://github.com/netixc/RealtimeVoiceClient.git
cd RealtimeVoiceClient

# Install dependencies (automatically installs uv and Python packages)
npm install

# Configure environment variables
cp .env.sample .env
# Edit .env with your API keys

# Start the desktop app
npm run dev
```

### Alternative Installation (using uv directly)

If you prefer to use `uv` directly:

```bash
# 1. Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the repository with submodules
git clone --recurse-submodules https://github.com/netixc/RealtimeVoiceClient.git
cd RealtimeVoiceClient

# 3. Install dependencies
uv sync

# 4. Initialize submodules if needed
git submodule update --init --recursive
```

### 4. Configure environment variables

Copy `.env.sample` to `.env` and configure:

```bash
cp .env.sample .env
# Edit .env with your values
```

**Required:**
```bash
OPENAI_API_KEY=sk-...  # Your OpenAI API key
BACKEND_URL=ws://YOUR_SERVER_IP:PORT/v1/realtime?model=gpt-realtime
```

**Optional (for specific agents):**
```bash
GEMINI_API_KEY=...  # For Gemini browser automation
AGENT_ZERO_API_URL=http://localhost:5000  # For Agent Zero
```

### 5. Set up backend server

Run the [RealtimeVoiceChat](https://github.com/netixc/RealtimeVoiceChat) backend server on your network or locally.

## Usage

### Web Interface (Recommended)

Start the web server:

```bash
npm run dev
# or
npm start
```

Alternatively, using uv directly:
```bash
uv run voice_chat_desktop.py
```

Then open your browser to:
- **Local:** http://localhost:8889
- **Network:** http://YOUR_SERVER_IP:8889

The web interface includes:
- **💬 Chat Tab** - Real-time conversation with voice and text input
- **🤖 Agents Tab** - Create and manage AI agents
- **📊 Events Tab** - Monitor all agent activity in real-time
- Visual status indicators and microphone toggle
- DTLN-aec echo cancellation

### Using Agents

**Via Voice:**
1. Click **Start** to begin voice chat
2. Say: "Create a Claude Code agent called my-coder"
3. Say: "Tell my-coder to list all Python files"
4. The AI will automatically create the agent and send commands

**Via UI:**
1. Click **Start** button
2. Go to **🤖 Agents** tab
3. Click **+ Create New Agent**
4. Fill in: Tool type, Agent type, Agent name
5. Click **📝 Command** to send tasks to your agent
6. Check **📊 Events** tab to see execution logs

**Via Text:**
1. Click **Start** button
2. Type in the text box: "Create a Gemini browser agent"
3. Type: "Command the agent to search for Python tutorials"

### Agent Types

**Claude Code (`claude_code`)**
- Software development and coding tasks
- Requires: Claude CLI installed
- Type: `agentic_coding`
- Example: "Create a Python web scraper"

**Gemini Browser (`gemini`)**
- Web automation and browsing
- Requires: GEMINI_API_KEY + playwright
- Type: `agentic_browsing`
- Example: "Navigate to GitHub and take a screenshot"

**Agent Zero (`agent_zero`)**
- General-purpose AI tasks
- Requires: AGENT_ZERO_API_URL configured
- Type: `agentic_general`
- Example: "Research the latest AI news"

### Terminal Client (Advanced)

Run the command-line version:

```bash
npm run cli
```

Alternatively, using uv directly:
```bash
uv run voice_chat_client.py
```

### Controls

- **Speak naturally** - The client will detect when you start and stop speaking
- **Interrupt anytime** - Just start speaking to interrupt the AI mid-response
- **Desktop App**: Click Start/Stop buttons
- **Terminal**: Press Ctrl+C to exit

### Available npm Commands

```bash
npm install      # Install dependencies (runs setup script)
npm run dev      # Start the desktop app
npm start        # Alias for npm run dev
npm run cli      # Run terminal client
npm run setup    # Re-run setup if needed
```

## Configuration

Edit `voice_chat_client.py` to customize:

```python
# Backend server URL
BACKEND_URL = "ws://192.168.50.40:8000/v1/realtime?model=gpt-realtime"

# Speech detection threshold (higher = less sensitive)
# Located in _get_adaptive_threshold() method
return 130  # Default threshold

# Echo cancellation settings
ECHO_SUPPRESSION_ENABLED = True
DEBUG_AEC = False  # Set to True for debugging output
```

## How It Works

1. **Audio Input**: Captures microphone audio at 16kHz (optimal for VAD)
2. **Echo Cancellation**: DTLN-aec removes speaker echo from microphone input
3. **Voice Detection**: Client-side VAD detects when you're speaking
4. **Transcription**: Sends audio to backend for Whisper transcription
5. **AI Response**: Receives and plays TTS audio at 24kHz
6. **Interruption**: Detects speech during playback and cancels AI response

## Architecture

```
Microphone (16kHz)
    ↓
DTLN-aec Echo Cancellation
    ↓
Voice Activity Detection (VAD)
    ↓
WebSocket → Backend Server
    ↓
Whisper Transcription
    ↓
LLM Response Generation
    ↓
TTS Synthesis (24kHz)
    ↓
Speaker Output
    ↓
Echo Reference → DTLN-aec
```

## Troubleshooting

### Audio Issues

**No audio input/output:**
```bash
# Check audio devices
uv run python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)}') for i in range(p.get_device_count())]"
```

### Echo Cancellation Issues

**Echo still present:**
- Increase threshold in `_get_adaptive_threshold()` (currently 130)
- Enable debug mode: `DEBUG_AEC = True`
- Check DTLN-aec stats for suppression levels (should be 20-30dB)

### Connection Issues

**Cannot connect to backend:**
- Verify backend server is running at `ws://192.168.50.40:8000`
- Check firewall settings
- Update `BACKEND_URL` if using different server

## Dependencies

- **eel** - Desktop app framework (web UI in Python)
- **numpy** - Numerical computing for audio processing
- **pyaudio** - Audio I/O
- **scipy** - Audio resampling (24kHz ↔ 16kHz)
- **tensorflow** - TFLite model inference for DTLN-aec
- **webrtcvad** - Voice activity detection
- **websocket-client** - WebSocket communication

## License

MIT License

## Credits

- **DTLN-aec**: [breizhn/DTLN-aec](https://github.com/breizhn/DTLN-aec)
- **OpenAI Realtime API**: Voice conversation capabilities
