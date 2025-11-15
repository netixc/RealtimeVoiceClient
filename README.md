# Voice Chat Client with DTLN-aec Echo Cancellation

A real-time voice chat client for OpenAI Realtime API with state-of-the-art deep learning echo cancellation using DTLN-aec.

## Features

- 🎙️ **Real-time voice conversation** with AI assistant
- 🤖 **DTLN-aec echo cancellation** - Deep learning based acoustic echo cancellation
- 🔊 **Full-duplex communication** - Interrupt the AI anytime while it's speaking
- 🎯 **Client-side VAD** - Voice activity detection for accurate speech recognition
- ⚡ **Low latency** - ~30ms processing latency

## Requirements

- Python 3.9 or higher
- macOS (tested) or Linux
- Microphone and speakers
- Backend server running at `ws://192.168.50.40:8000` (or modify `BACKEND_URL` in the script)

## Installation

### 1. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository and install DTLN-aec

```bash
cd /Users/control/Documents/voice

# Clone DTLN-aec repository
git clone https://github.com/breizhn/DTLN-aec.git
```

### 3. Install dependencies

```bash
uv sync
```

## Usage

### Run the voice chat client

```bash
uv run voice_chat_client.py
```

### Controls

- **Speak naturally** - The client will detect when you start and stop speaking
- **Interrupt anytime** - Just start speaking to interrupt the AI mid-response
- **Press Ctrl+C** - Exit the application

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
