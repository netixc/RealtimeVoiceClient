#!/usr/bin/env python3
"""
Desktop Voice Chat Application with DTLN-aec Echo Cancellation

This combines the voice_chat_client.py with a beautiful web UI using Eel.
"""

import eel
import threading
import sys
from voice_chat_client import VoiceChatClient, BACKEND_URL, API_KEY

# Global client instance
client = None
client_thread = None

# Initialize Eel
eel.init('web')

@eel.expose
def start_voice_chat(mic_enabled=True):
    """Start the voice chat client"""
    global client, client_thread

    if client is not None:
        print("Voice chat already running")
        return

    print("🎤 Starting voice chat client...")

    # Create client with custom callbacks for UI updates
    client = VoiceChatClient(BACKEND_URL, API_KEY)
    # Set initial mic state from UI
    client.mic_enabled = mic_enabled
    print(f"   🎤 Microphone initial state: {'enabled' if mic_enabled else 'muted'}")

    # Override callbacks to update UI
    original_on_message = client.on_message

    def on_message_with_ui(ws, message):
        """Intercept messages to update UI"""
        import json

        try:
            event = json.loads(message)
            event_type = event.get("type", "unknown")

            # Update UI based on events
            if event_type == "conversation.item.created":
                item = event.get("item", {})
                role = item.get("role", "unknown")
                content = item.get("content", [])

                if role == "user" and content:
                    for content_item in content:
                        if content_item.get("type") == "input_audio":
                            transcript = content_item.get("transcript")
                            if transcript:
                                eel.add_user_message(transcript)
                        elif content_item.get("type") == "input_text":
                            text = content_item.get("text", "")
                            if text:
                                eel.add_user_message(text)

            elif event_type == "response.text.delta":
                delta = event.get("delta", "")
                if delta:
                    # Update typing indicator
                    if not hasattr(on_message_with_ui, 'assistant_text'):
                        on_message_with_ui.assistant_text = ""
                    on_message_with_ui.assistant_text += delta
                    eel.set_assistant_typing(on_message_with_ui.assistant_text)

            elif event_type == "response.text.done":
                text = event.get("text", "")
                if text:
                    eel.add_assistant_message(text)
                    on_message_with_ui.assistant_text = ""

            elif event_type == "response.audio.delta":
                eel.update_status("AI speaking...", True)

            elif event_type == "response.audio.done":
                eel.update_status("Listening...", True)

            elif event_type == "response.done":
                eel.update_status("Listening...", True)

            elif event_type == "session.created":
                eel.update_status("Connected", True)

        except Exception as e:
            print(f"Error updating UI: {e}")

        # Call original handler
        original_on_message(ws, message)

    client.on_message = on_message_with_ui

    # Start client in separate thread
    def run_client():
        try:
            client.connect()
        except Exception as e:
            print(f"Error running client: {e}")
            eel.update_status(f"Error: {e}", False)
            eel.enable_controls(True)

    client_thread = threading.Thread(target=run_client, daemon=True)
    client_thread.start()

    eel.update_status("Connecting...", True)

@eel.expose
def stop_voice_chat():
    """Stop the voice chat client"""
    global client, client_thread

    if client is None:
        print("Voice chat not running")
        return

    print("🛑 Stopping voice chat client...")

    try:
        client.close()
        client = None
        eel.update_status("Stopped", False)
    except Exception as e:
        print(f"Error stopping client: {e}")
        eel.update_status(f"Error: {e}", False)

@eel.expose
def send_text_message(text):
    """Send a text message to the AI"""
    global client

    if client is None:
        print("Voice chat not running - cannot send text message")
        eel.update_status("Not connected", False)
        return

    print(f"📤 Sending text message: {text}")

    try:
        # Send text message as a conversation item
        client.send_event("conversation.item.create", {
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text
                    }
                ]
            }
        })

        # Request a response
        client.send_event("response.create")

    except Exception as e:
        print(f"Error sending text message: {e}")
        eel.update_status(f"Error: {e}", False)

@eel.expose
def toggle_microphone(enabled):
    """Toggle microphone on/off"""
    global client

    if client is None:
        print("Voice chat not running - cannot toggle microphone")
        return

    if enabled:
        print("🎤 Microphone enabled")
        client.mic_enabled = True
        eel.update_status("Listening...", True)
    else:
        print("🔇 Microphone muted")
        client.mic_enabled = False
        eel.update_status("Mic muted", True)

@eel.expose
def clear_conversation():
    """Clear conversation - placeholder for future functionality"""
    print("Clear conversation requested")

def main():
    """Main entry point"""
    print("=" * 60)
    print("🎙️ Voice Chat Desktop App with DTLN-aec")
    print("=" * 60)
    print()
    print("Starting desktop app...")
    print()

    try:
        # Start Eel app - try Brave browser on macOS
        eel.start('index.html',
                  size=(800, 900),
                  port=8889,
                  mode='custom',
                  cmdline_args=['/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '--app=http://localhost:8889/index.html'])
    except (SystemExit, KeyboardInterrupt):
        print("\n\nShutting down...")
        if client:
            client.close()
        sys.exit(0)

if __name__ == "__main__":
    main()
