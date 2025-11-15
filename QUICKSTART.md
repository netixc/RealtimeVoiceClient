# Quick Start Guide

Get up and running with RealtimeVoiceClient in 3 simple steps!

## Prerequisites

- Node.js and npm installed
- Python 3.9 or higher (check with `python3 --version`)
- Microphone and speakers
- Backend server running ([RealtimeVoiceChat](https://github.com/netixc/RealtimeVoiceChat))

## Installation

```bash
# Clone the repository
git clone --recurse-submodules https://github.com/netixc/RealtimeVoiceClient.git
cd RealtimeVoiceClient

# Install dependencies (this will automatically install uv and all Python packages)
npm install
```

## Configuration

Create your `.env` file:

```bash
cp .env.sample .env
```

Edit `.env` and set at minimum:

```bash
OPENAI_API_KEY=sk-your-key-here
BACKEND_URL=ws://YOUR_SERVER_IP:PORT/v1/realtime?model=gpt-realtime
```

## Run

Start the web server:

```bash
npm run dev
```

Then open your browser to:
- http://localhost:8889 (local)
- http://192.168.50.40:8889 (network access)

Or use the terminal client:

```bash
npm run cli
```

## Available Commands

```bash
npm install      # Install dependencies
npm run dev      # Start desktop app (recommended)
npm start        # Alias for npm run dev
npm run cli      # Start terminal client
npm run setup    # Re-run setup if needed
```

## Troubleshooting

**Error: uv command not found**
- The install script should automatically install uv
- If it fails, manually install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Restart your terminal and try `npm install` again

**Error: Cannot connect to backend**
- Verify your backend server is running
- Check `BACKEND_URL` in `.env` file
- Test with: `curl http://YOUR_SERVER_IP:PORT/health`

**No audio input/output**
- Check your microphone/speaker permissions
- Try listing audio devices: `npm run cli` and check for errors

## Next Steps

1. Open http://localhost:8889 in your browser
2. Click **Start** button in the web interface
3. Say "Hello" or type a message
4. Create agents via voice: "Create a Claude Code agent called my-assistant"
5. Check the **Agents** tab to manage your agents
6. Monitor activity in the **Events** tab

For detailed documentation, see [README.md](README.md)
