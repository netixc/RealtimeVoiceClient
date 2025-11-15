#!/usr/bin/env python3
"""
Interactive Voice Chat Client for OpenAI Realtime API

This script creates a full voice conversation experience using your microphone
and speakers, similar to the web interface at http://192.168.50.40:8000/

Usage:
    python3 voice_chat_client.py

Requirements:
    pip install websocket-client pyaudio webrtcvad numpy scipy
"""

import json
import sys
import threading
import time
import websocket
import base64
import queue
import signal

# Try to import required libraries
try:
    import pyaudio
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False
    print("❌ Error: PyAudio not installed")
    print("   Install with: pip3 install pyaudio")
    sys.exit(1)

try:
    import webrtcvad
    VAD_ENABLED = True
except ImportError:
    VAD_ENABLED = False
    print("⚠️  WebRTC VAD not installed - using simpler voice detection")
    print("   For better performance: pip3 install webrtcvad")
    print()

try:
    import numpy as np
    NUMPY_ENABLED = True
except ImportError:
    NUMPY_ENABLED = False
    print("⚠️  NumPy not installed - echo cancellation disabled")
    print("   Install with: pip3 install numpy")

try:
    from scipy import signal as scipy_signal
    SCIPY_ENABLED = True
except ImportError:
    SCIPY_ENABLED = False
    print("⚠️  SciPy not installed - using basic echo cancellation")
    print("   For better AEC: pip3 install scipy")

try:
    from dtln_aec_realtime import DTLNAECRealtime
    DTLN_ENABLED = True
except ImportError:
    DTLN_ENABLED = False
    print("⚠️  DTLN-aec not available - echo cancellation disabled")
    print("   Ensure DTLN-aec repository is cloned in this directory")

# Configuration
BACKEND_URL = "ws://192.168.50.40:8000/v1/realtime?model=gpt-realtime"
API_KEY = "test-key"

# Audio configuration
SAMPLE_RATE = 24000  # TTS output rate
INPUT_SAMPLE_RATE = 16000  # Microphone input rate (required for VAD)
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit
CHUNK_SIZE = 480  # 30ms at 16kHz for VAD

# VAD configuration - using client-side VAD for now
CONTINUOUS_STREAMING = False  # Use client-side VAD to detect speech

# Echo cancellation configuration
ECHO_SUPPRESSION_ENABLED = True  # Enable echo cancellation
ECHO_SUPPRESSION_RATIO = 0.95  # How much to suppress echo (0.0-1.0)
DEBUG_AEC = False  # Enable AEC debugging output (set True to see echo cancellation stats)
AEC_FILTER_LENGTH = 256  # Adaptive filter taps (16ms at 16kHz)
AEC_STEP_SIZE = 0.5  # NLMS learning rate (mu) - can be higher due to normalization


class RLSEchoCanceller:
    """
    Recursive Least Squares (RLS) adaptive echo canceller with double-talk detection.

    RLS converges 10-100x faster than NLMS, making it ideal for real-time AEC.
    Based on: https://github.com/Keyvanhardani/Python-Acoustic-Echo-Cancellation-Library
    """
    def __init__(self, filter_length=256, forgetting_factor=0.98, reg_param=1.0):
        self.filter_length = filter_length
        self.lambda_val = forgetting_factor  # 0.95-0.99, higher = more stable
        self.reg_param = reg_param  # Regularization to prevent instability

        # RLS filter state
        self.weights = np.zeros(filter_length, dtype=np.float64)
        self.P = np.eye(filter_length, dtype=np.float64) / reg_param  # Inverse correlation matrix
        self.reference_buffer = np.zeros(filter_length, dtype=np.float64)
        self.epsilon = 1e-10

        # Double-talk detection (Geigel algorithm)
        self.geigel_window_size = 128
        self.geigel_window = np.zeros(self.geigel_window_size, dtype=np.float64)
        self.geigel_index = 0

    def _detect_double_talk(self, mic_sample, ref_sample):
        """
        Detect if both near-end (user) and far-end (AI) are talking.
        Uses simplified Geigel algorithm - if mic energy >> reference energy, likely double-talk.

        Returns True if double-talk detected (don't adapt filter)
        """
        # Update Geigel window with reference samples
        self.geigel_window[self.geigel_index] = abs(ref_sample)
        self.geigel_index = (self.geigel_index + 1) % self.geigel_window_size

        # Get max reference in recent window
        max_ref = np.max(self.geigel_window) + self.epsilon

        # If mic signal is much larger than reference, it's likely near-end speech (double-talk)
        # Threshold: mic > 2 * max_ref means user is probably speaking
        return abs(mic_sample) > (2.0 * max_ref)

    def process(self, mic_sample, ref_sample):
        """
        Process one sample with RLS adaptive filtering.

        Args:
            mic_sample: Current microphone sample (desired signal + echo)
            ref_sample: Current reference sample (speaker output)

        Returns:
            error_sample: Echo-cancelled output (estimated desired signal)
        """
        # Normalize inputs to prevent overflow
        mic_sample = np.clip(mic_sample, -32768, 32767)
        ref_sample = np.clip(ref_sample, -32768, 32767)

        # Update reference buffer (shift and add new sample)
        self.reference_buffer = np.roll(self.reference_buffer, 1)
        self.reference_buffer[0] = ref_sample

        # Predict echo using current filter weights
        predicted_echo = np.dot(self.weights, self.reference_buffer)

        # Calculate prior estimation error
        error = mic_sample - predicted_echo

        # Double-talk detection - only adapt if no double-talk
        is_double_talk = self._detect_double_talk(mic_sample, ref_sample)

        if not is_double_talk:
            # RLS algorithm update
            # Step 1: Compute gain vector k
            # k = P * u / (λ + u^T * P * u)
            P_u = np.dot(self.P, self.reference_buffer)
            denominator = self.lambda_val + np.dot(self.reference_buffer, P_u)
            gain_vector = P_u / (denominator + self.epsilon)

            # Step 2: Update filter weights
            # w = w + k * error
            self.weights += gain_vector * error

            # Step 3: Update inverse correlation matrix P
            # P = (1/λ) * (P - k * u^T * P)
            self.P = (1.0 / self.lambda_val) * (
                self.P - np.outer(gain_vector, np.dot(self.reference_buffer, self.P))
            )

        # else: freeze adaptation during double-talk

        return error


class VoiceChatClient:
    def __init__(self, url, api_key, function_handlers=None):
        self.url = url
        self.api_key = api_key
        self.ws = None
        self.running = False
        self.function_handlers = function_handlers or {}  # Function call handlers

        # Audio streams
        self.pyaudio_instance = pyaudio.PyAudio()
        self.output_stream = None
        self.input_stream = None

        # VAD
        self.vad = webrtcvad.Vad(1) if VAD_ENABLED else None  # Aggressiveness 0-3 (1=less aggressive)

        # State
        self.is_tts_playing = False  # AI is speaking
        self.is_listening = False  # User is speaking
        self.audio_buffer = []
        self.silence_frames = 0
        self.speech_frames = 0
        self.mic_enabled = True  # Microphone toggle

        # Function calling state
        self.pending_function_calls = {}

        # Queues
        self.audio_queue = queue.Queue()
        self.output_audio_queue = queue.Queue()  # For managing audio playback

        # Echo cancellation - track recent output audio for reference
        self.echo_reference_buffer = []  # Stores recent TTS audio chunks
        self.echo_reference_lock = threading.Lock()
        self.max_echo_delay_samples = int(INPUT_SAMPLE_RATE * 0.5)  # 500ms buffer

        # Initialize DTLN-aec for echo cancellation
        if DTLN_ENABLED and ECHO_SUPPRESSION_ENABLED:
            # Use model size 128 for lowest latency (best for real-time)
            # Options: 128 (fastest), 256 (balanced), 512 (best quality)
            self.dtln_aec = DTLNAECRealtime(model_size=128)
        else:
            self.dtln_aec = None
            print("   ⚠️  Echo cancellation disabled")

        # Timing tracking for adaptive VAD threshold
        self.last_tts_chunk_time = 0
        self.tts_decay_time = 1.5  # seconds to decay threshold after TTS stops

        print("🎙️  Initializing audio devices...")
        self._setup_audio()

    def _setup_audio(self):
        """Setup audio input and output streams."""
        # Output stream for playing AI responses
        self.output_stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=1024
        )

        # Input stream for recording user speech
        # Try to enable echo cancellation if platform supports it
        try:
            import platform
            # Platform-specific echo cancellation
            if platform.system() == 'Darwin':  # macOS
                # macOS uses Core Audio which has built-in echo cancellation
                self.input_stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=INPUT_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE,
                    # Note: PyAudio on macOS should use echo cancellation by default
                )
            else:
                # Other platforms
                self.input_stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=INPUT_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE
                )
        except Exception as e:
            print(f"⚠️  Could not enable echo cancellation: {e}")
            self.input_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE
            )

        print("✅ Audio devices ready")
        print(f"   🔊 Output: {SAMPLE_RATE}Hz")
        print(f"   🎤 Input: {INPUT_SAMPLE_RATE}Hz")
        if ECHO_SUPPRESSION_ENABLED and DTLN_ENABLED and self.dtln_aec is not None:
            print(f"   🔇 Echo cancellation: DTLN-aec (DEEP LEARNING) ⭐⭐⭐")
            print(f"   🤖 Neural network-based AEC - State of the art!")
            print(f"   🎯 Full-duplex: You can interrupt the AI anytime")
        else:
            print("   ⚠️  Echo cancellation: DISABLED")
        print()

    def on_open(self, ws):
        """Called when WebSocket connection is established."""
        print("✅ Connected to Realtime API")
        print("⏳ Waiting for session initialization...\n")

    def on_message(self, ws, message):
        """Called when a message is received from the server."""
        try:
            event = json.loads(message)
            event_type = event.get("type", "unknown")

            # Debug: log all non-audio events
            if DEBUG_AEC and event_type not in ["response.audio.delta", "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"]:
                print(f"   📨 Event: {event_type}")

            if event_type == "session.created":
                print("🎉 Session created!")
                session = event.get("session", {})
                print(f"   Voice: {session.get('voice')}")
                turn_detection_type = session.get('turn_detection', {})
                if isinstance(turn_detection_type, dict):
                    print(f"   Turn detection: {turn_detection_type.get('type')}")
                else:
                    print(f"   Turn detection: {turn_detection_type}")
                print()

                # Update session with our preferences
                # IMPORTANT: Explicitly disable server-side turn detection for client-side VAD
                session_config = {
                    "session": {
                        "instructions": "You are a helpful AI assistant with access to agent management tools. You can create and manage AI agents (Claude Code, Gemini, Agent Zero) to help with coding, browsing, and general tasks. Be concise and conversational.",
                        "voice": "nova",
                        "temperature": 0.8,
                        "input_audio_transcription": {"model": "whisper-1"},
                        "turn_detection": {"type": "none"}  # Disable server-side VAD
                    }
                }

                # Add tools if function handlers are registered
                if self.function_handlers:
                    session_config["session"]["tools"] = self._get_tools_schema()

                self.send_event("session.update", session_config)

            elif event_type == "session.updated":
                print("✅ Session configured")
                updated_session = event.get("session", {})
                turn_detection = updated_session.get("turn_detection", {})
                if isinstance(turn_detection, dict):
                    print(f"   Turn detection updated to: {turn_detection.get('type', 'unknown')}")
                else:
                    print(f"   Turn detection updated to: {turn_detection}")
                print()
                print("=" * 60)
                print("🎤 Ready! Start speaking...")
                print("   Press Ctrl+C to quit")
                print("=" * 60)
                print()

                # Start listening for user input
                self.start_listening()
                # Start audio playback thread
                self.start_audio_playback()

            elif event_type == "conversation.item.created":
                item = event.get("item", {})
                role = item.get("role", "unknown")
                content = item.get("content", [])

                if DEBUG_AEC:
                    print(f"   📨 Conversation item - role: {role}, content items: {len(content)}")

                if role == "user" and content:
                    # Check for transcript in content
                    for content_item in content:
                        if content_item.get("type") == "input_audio":
                            transcript = content_item.get("transcript")
                            if transcript:
                                print(f"\n👤 You: {transcript}")
                        elif content_item.get("type") == "input_text":
                            text = content_item.get("text", "")
                            if text:
                                print(f"\n👤 You: {text}")

            elif event_type == "response.text.delta":
                delta = event.get("delta", "")
                if delta:
                    # Don't print anything during streaming to avoid clutter
                    pass

            elif event_type == "response.text.done":
                text = event.get("text", "")
                print(f"\n🤖 AI: {text}")
                self.is_tts_playing = True

            elif event_type == "response.audio.delta":
                # Queue audio chunk for playback
                delta = event.get("delta", "")
                if delta:
                    try:
                        audio_data = base64.b64decode(delta)
                        self.output_audio_queue.put(audio_data)
                        # Track audio chunks received
                        if not hasattr(self, 'audio_chunk_count'):
                            self.audio_chunk_count = 0
                            self.is_tts_playing = True
                            print(f"   🔊 Starting TTS playback...")
                        self.audio_chunk_count += 1
                    except Exception as e:
                        print(f"   ❌ Error queueing audio: {e}")

            elif event_type == "response.audio.done":
                # Mark end of audio stream
                chunks = getattr(self, 'audio_chunk_count', 0)
                print(f"   📻 Audio stream ended by server (received {chunks} chunks)")
                self.audio_chunk_count = 0
                self.output_audio_queue.put(None)  # Signal end of audio

            elif event_type == "response.cancelled":
                print("   🛑 Response cancelled")
                self.is_tts_playing = False

            elif event_type == "response.done":
                response = event.get("response", {})
                status = response.get("status", "unknown")
                if DEBUG_AEC:
                    print(f"   📨 Response done - status: {status}")
                print()
                print("─" * 60)
                print("🎤 Listening...")
                print()

            elif event_type == "response.function_call_arguments.delta":
                # Function call argument streaming
                call_id = event.get("call_id")
                delta = event.get("delta", "")
                if call_id:
                    if call_id not in self.pending_function_calls:
                        self.pending_function_calls[call_id] = {"name": "", "arguments": ""}
                    self.pending_function_calls[call_id]["arguments"] += delta

            elif event_type == "response.function_call_arguments.done":
                # Function call complete - execute it
                call_id = event.get("call_id")
                name = event.get("name")
                arguments = event.get("arguments", "{}")

                print(f"\n🔧 Function call: {name}")
                print(f"   Arguments: {arguments}")

                if name in self.function_handlers:
                    try:
                        import json as json_lib
                        args = json_lib.loads(arguments)
                        result = self.function_handlers[name](**args)
                        print(f"   ✅ Result: {result}")

                        # Send function output back to server
                        self.send_event("conversation.item.create", {
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json_lib.dumps(result)
                            }
                        })

                        # Request response to continue conversation
                        self.send_event("response.create")

                    except Exception as e:
                        print(f"   ❌ Error executing function: {e}")
                        error_result = {"ok": False, "error": str(e)}
                        self.send_event("conversation.item.create", {
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json_lib.dumps(error_result)
                            }
                        })
                else:
                    print(f"   ⚠️  No handler registered for function: {name}")

                # Clean up pending call
                if call_id in self.pending_function_calls:
                    del self.pending_function_calls[call_id]

            elif event_type == "error":
                error = event.get("error", {})
                print(f"\n❌ Error: {error.get('type')} - {error.get('message')}")

        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse message: {e}")

    def on_error(self, ws, error):
        """Called when an error occurs."""
        print(f"\n❌ WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed."""
        print(f"\n🔌 Connection closed")
        self.running = False

    def send_event(self, event_type, event_data=None):
        """Send an event to the server."""
        if not self.ws:
            return

        event = {"type": event_type}
        if event_data:
            event.update(event_data)

        self.ws.send(json.dumps(event))

    def _get_tools_schema(self):
        """Get tools schema for function calling"""
        return [
            {
                "type": "function",
                "name": "create_agent",
                "description": "Create a new AI agent (Claude Code for coding, Gemini for browser automation, or Agent Zero for general tasks)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "enum": ["claude_code", "gemini", "agent_zero"],
                            "description": "Type of agent to create"
                        },
                        "agent_type": {
                            "type": "string",
                            "description": "Agent type (agentic_coding, agentic_browsing, agentic_general)"
                        },
                        "agent_name": {
                            "type": "string",
                            "description": "Unique name for the agent"
                        },
                        "lifetime_hours": {
                            "type": "number",
                            "description": "How many hours the agent should live (default 24)",
                            "default": 24
                        }
                    },
                    "required": ["tool", "agent_type", "agent_name"]
                }
            },
            {
                "type": "function",
                "name": "list_agents",
                "description": "List all active AI agents and their status",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "type": "function",
                "name": "command_agent",
                "description": "Send a command or instruction to an existing agent",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent to command"
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Command or instruction for the agent"
                        }
                    },
                    "required": ["agent_name", "prompt"]
                }
            },
            {
                "type": "function",
                "name": "delete_agent",
                "description": "Delete an agent and remove it from the registry",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent to delete"
                        }
                    },
                    "required": ["agent_name"]
                }
            },
            {
                "type": "function",
                "name": "get_agent_status",
                "description": "Get detailed status and metadata for an agent",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent to query"
                        }
                    },
                    "required": ["agent_name"]
                }
            }
        ]

    def start_listening(self):
        """Start listening to microphone in a separate thread."""
        self.running = True
        listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        listen_thread.start()

    def start_audio_playback(self):
        """Start audio playback in a separate thread."""
        playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        playback_thread.start()

    def _playback_loop(self):
        """Continuous loop that plays audio from the queue."""
        while self.running:
            try:
                # Get audio chunk from queue (blocking with timeout)
                audio_chunk = self.output_audio_queue.get(timeout=0.1)

                if audio_chunk is None:
                    # End of audio stream
                    self.is_tts_playing = False
                    print("   🔊 Audio playback complete")

                    # Clear echo reference buffer after TTS completes
                    # This prevents stale reference data from interfering with future detections
                    with self.echo_reference_lock:
                        # Keep last 128ms of audio for residual echo cancellation
                        keep_samples = int(INPUT_SAMPLE_RATE * 0.128)  # 128ms at 16kHz = ~2048 samples
                        if len(self.echo_reference_buffer) > keep_samples:
                            self.echo_reference_buffer = self.echo_reference_buffer[-keep_samples:]

                    continue

                # CRITICAL: Store audio chunk for echo reference BEFORE playing it
                # This ensures the reference buffer has the signal before it reaches the mic
                if ECHO_SUPPRESSION_ENABLED and NUMPY_ENABLED:
                    self._add_echo_reference(audio_chunk)
                    self.last_tts_chunk_time = time.time()

                # Play audio chunk (this goes to speakers and will echo back to mic)
                self.output_stream.write(audio_chunk)

            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    print(f"\n❌ Error in playback loop: {e}")
                break

    def _add_echo_reference(self, audio_chunk):
        """Add TTS audio chunk to echo reference buffer (resampled to mic rate)."""
        try:
            # Convert bytes to numpy array
            audio_24k = np.frombuffer(audio_chunk, dtype=np.int16)

            # Resample from 24kHz to 16kHz using scipy for better quality
            # Ratio: 16000/24000 = 2/3
            if SCIPY_ENABLED:
                from scipy import signal as scipy_signal
                # Resample using polyphase filtering for high quality
                num_samples_16k = int(len(audio_24k) * 16000 / 24000)
                audio_16k = scipy_signal.resample(audio_24k, num_samples_16k).astype(np.int16)
            else:
                # Fallback: simple decimation (take every 3rd sample from pairs of 2)
                # 24kHz -> 16kHz means keeping 2 out of every 3 samples
                # Better approach: average pairs then decimate
                audio_16k = audio_24k[::3]  # Simple decimation

            with self.echo_reference_lock:
                # Insert at beginning (oldest samples) since we're building a delay buffer
                self.echo_reference_buffer.extend(audio_16k)

                # Keep only recent audio (max delay window)
                if len(self.echo_reference_buffer) > self.max_echo_delay_samples:
                    # Remove oldest samples (from beginning)
                    excess = len(self.echo_reference_buffer) - self.max_echo_delay_samples
                    self.echo_reference_buffer = self.echo_reference_buffer[excess:]
        except Exception as e:
            if DEBUG_AEC:
                print(f"   ❌ Echo ref error: {e}")
            pass

    def _get_adaptive_threshold(self):
        """Get adaptive speech detection threshold based on TTS playback state."""
        # Raised threshold to prevent false interruptions from noise
        # DTLN-aec handles echo, so we don't need dynamic thresholds
        return 130  # Balanced threshold - filters noise but detects speech

    def _suppress_echo(self, audio_chunk):
        """Apply DTLN-aec echo cancellation."""
        if not DTLN_ENABLED or not ECHO_SUPPRESSION_ENABLED or self.dtln_aec is None:
            return audio_chunk

        try:
            chunk_len = len(audio_chunk) // 2  # bytes to samples (int16)

            # Get reference signal (or use silence if no playback)
            with self.echo_reference_lock:
                if len(self.echo_reference_buffer) >= chunk_len:
                    # Get reference samples from buffer
                    reference_samples = self.echo_reference_buffer[:chunk_len]
                    self.echo_reference_buffer = self.echo_reference_buffer[chunk_len:]
                else:
                    # No reference - use silence
                    reference_samples = [0] * chunk_len

            # Convert to numpy arrays
            mic_array = np.frombuffer(audio_chunk, dtype=np.int16)
            ref_array = np.array(reference_samples, dtype=np.int16)

            # Process through DTLN-aec
            cleaned_array = self.dtln_aec.process_frame(mic_array, ref_array)

            # Debug output
            if DEBUG_AEC and np.mean(np.abs(ref_array)) > 500:
                orig_energy = np.mean(np.abs(mic_array))
                clean_energy = np.mean(np.abs(cleaned_array))
                ref_energy = np.mean(np.abs(ref_array))
                if orig_energy > 1:
                    suppression_db = 20 * np.log10((orig_energy + 1) / (clean_energy + 1))
                    print(f"   🤖 DTLN: {suppression_db:.1f}dB (ref={ref_energy:.0f}, mic={orig_energy:.0f})")

            return cleaned_array.tobytes()

        except Exception as e:
            if DEBUG_AEC:
                print(f"   ❌ DTLN error: {e}")
                import traceback
                traceback.print_exc()
            return audio_chunk

    def _listen_loop(self):
        """Continuous loop that streams microphone audio to server."""
        print("🎤 Microphone active - streaming to server...")

        chunk_count = 0
        while self.running:
            try:
                # Read audio chunk from microphone
                audio_chunk = self.input_stream.read(CHUNK_SIZE, exception_on_overflow=False)

                # Skip processing if mic is disabled
                if not self.mic_enabled:
                    # Reset speech detection state when mic is disabled
                    if self.is_listening:
                        self.is_listening = False
                        self.audio_buffer = []
                        self.silence_frames = 0
                        self.speech_frames = 0
                        print("\n🔇 Microphone muted - stopping recording")
                    continue

                chunk_count += 1
                if DEBUG_AEC and chunk_count % 50 == 0:  # Every 50 chunks (~1.5 seconds)
                    print(f"   📡 Received {chunk_count} audio chunks from microphone")

                # Apply echo suppression first
                if ECHO_SUPPRESSION_ENABLED and NUMPY_ENABLED:
                    audio_chunk = self._suppress_echo(audio_chunk)
                    if DEBUG_AEC and chunk_count % 50 == 0:
                        print(f"   ✅ Echo suppression complete")

                # Stream directly to server for server-side VAD
                if CONTINUOUS_STREAMING:
                    self._send_audio_chunk(audio_chunk)
                else:
                    # Client-side VAD mode with adaptive threshold
                    is_speech = self._is_speech(audio_chunk)

                    if DEBUG_AEC and is_speech:
                        print(f"   ✅ SPEECH DETECTED! is_listening={self.is_listening}, speech_frames={self.speech_frames}")

                    if is_speech:
                        self.speech_frames += 1
                        self.silence_frames = 0

                        if not self.is_listening:
                            self.is_listening = True
                            self.audio_buffer = []
                            print("\n🔴 Recording...", flush=True)

                            # INTERRUPTION: Stop TTS playback when user starts speaking
                            if self.is_tts_playing:
                                print("   🛑 Interrupting AI...")
                                # Send response.cancel to stop the AI
                                self.send_event("response.cancel")
                                # Clear the audio queue to stop playback immediately
                                while not self.output_audio_queue.empty():
                                    try:
                                        self.output_audio_queue.get_nowait()
                                    except:
                                        break
                                self.is_tts_playing = False

                        if self.is_listening:
                            self.audio_buffer.append(audio_chunk)
                    else:
                        self.silence_frames += 1
                        self.speech_frames = 0

                        if DEBUG_AEC and self.is_listening:
                            print(f"   🔇 Silence frame {self.silence_frames}/15")

                        if self.is_listening:
                            self.audio_buffer.append(audio_chunk)

                        if self.is_listening and self.silence_frames > 15:
                            self.is_listening = False
                            print(f"\n⏸️  Processing... (collected {len(self.audio_buffer)} chunks)", flush=True)
                            self._send_audio_buffer()
                            self.audio_buffer = []

            except Exception as e:
                if self.running:
                    print(f"\n❌ Error in listen loop: {e}")
                break

    def _is_speech(self, audio_chunk):
        """Detect if audio chunk contains speech with adaptive threshold."""
        # Get adaptive threshold based on TTS playback state
        adaptive_threshold = self._get_adaptive_threshold()

        # Calculate energy for all paths
        import array
        audio_data = array.array('h', audio_chunk)
        energy = sum(abs(x) for x in audio_data) / len(audio_data)

        # Primary detection: energy-based (DTLN-aec handles echo, so we trust energy levels)
        is_speech_energy = energy > adaptive_threshold

        if DEBUG_AEC and energy > 10:
            print(f"   🎤 Energy: {energy:.0f}, Threshold: {adaptive_threshold:.0f}, Speech: {is_speech_energy}, TTS: {self.is_tts_playing}")

        # Use energy-based detection as primary (since DTLN-aec cleans audio)
        return is_speech_energy

    def _send_audio_chunk(self, audio_chunk):
        """Send a single audio chunk to server for server-side VAD."""
        # Encode to base64
        audio_b64 = base64.b64encode(audio_chunk).decode()

        # Send audio via input_audio_buffer.append
        # Note: isTTSPlaying state is managed via response events (response.audio.delta, response.done)
        # The server tracks this based on the response lifecycle
        self.send_event("input_audio_buffer.append", {
            "audio": audio_b64
        })

    def _send_audio_buffer(self):
        """Send accumulated audio buffer to server (fallback mode)."""
        if not self.audio_buffer:
            return

        # Combine all chunks
        audio_data = b''.join(self.audio_buffer)

        if DEBUG_AEC:
            print(f"   📤 Sending {len(audio_data)} bytes of audio")

        # Encode to base64
        audio_b64 = base64.b64encode(audio_data).decode()

        # Send audio via input_audio_buffer.append
        self.send_event("input_audio_buffer.append", {
            "audio": audio_b64
        })

        # Commit the buffer (triggers transcription and response)
        self.send_event("input_audio_buffer.commit")

        # Request a new response
        self.send_event("response.create")

        if DEBUG_AEC:
            print(f"   ✅ Audio sent, waiting for response...")

    def connect(self):
        """Connect to the Realtime API."""
        print("=" * 60)
        print("🎙️  Voice Chat Client - OpenAI Realtime API")
        print("=" * 60)
        print(f"🌐 Connecting to: {self.url}")
        print()

        # Create WebSocket connection
        self.ws = websocket.WebSocketApp(
            self.url,
            header=[f"Authorization: Bearer {self.api_key}"],
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )

        # Run the WebSocket
        self.ws.run_forever(
            ping_interval=30,
            ping_timeout=10,
            skip_utf8_validation=True
        )

    def close(self):
        """Close connections and cleanup."""
        print("\n\n🛑 Shutting down...")
        self.running = False

        if self.ws:
            self.ws.close()

        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()

        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()

        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()

        print("👋 Goodbye!")


def signal_handler(_sig, _frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Interrupt received...")
    sys.exit(0)


def main():
    """Main entry point."""
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    try:
        client = VoiceChatClient(BACKEND_URL, API_KEY)
        client.connect()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Check dependencies
    missing_deps = []

    try:
        import websocket
    except ImportError:
        missing_deps.append("websocket-client")

    try:
        import pyaudio
    except ImportError:
        missing_deps.append("pyaudio")

    if missing_deps:
        print("❌ Missing dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\nInstall with:")
        print(f"   pip3 install {' '.join(missing_deps)}")
        if not VAD_ENABLED:
            print("\nOptional (recommended for better voice detection):")
            print("   pip3 install webrtcvad")
        sys.exit(1)

    main()
