#!/usr/bin/env python3
"""
Test script to verify function calling works with direct OpenAI connection.

This temporarily overrides BACKEND_URL to connect directly to OpenAI
instead of the custom backend server.
"""

import os
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Override BACKEND_URL to connect directly to OpenAI
os.environ["BACKEND_URL"] = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
os.environ["API_KEY"] = os.environ["OPENAI_API_KEY"]

print("=" * 60)
print("🧪 Testing Direct OpenAI Connection")
print("=" * 60)
print(f"URL: {os.environ['BACKEND_URL']}")
print(f"API Key: {os.environ['API_KEY'][:10]}...")
print()

# Now import and run
from voice_chat_client import VoiceChatClient
from agent_manager import AgentManager

def main():
    # Initialize agent manager
    workspace_dir = Path.cwd() / "workspace"
    agent_manager = AgentManager(working_dir=str(workspace_dir))
    print(f"🤖 Agent manager initialized: {workspace_dir}\n")

    # Set up function handlers
    function_handlers = {
        "create_agent": agent_manager.create_agent,
        "list_agents": lambda: agent_manager.list_agents(),
        "command_agent": agent_manager.command_agent,
        "delete_agent": agent_manager.delete_agent,
        "get_agent_status": agent_manager.get_agent_status,
    }

    # Create client with direct OpenAI connection
    client = VoiceChatClient(
        os.environ["BACKEND_URL"],
        os.environ["API_KEY"],
        function_handlers=function_handlers
    )

    print("📝 Once connected, try typing: 'list agents'")
    print("   The AI should call the list_agents() function.\n")

    # Start the client
    try:
        client.connect()
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
        client.close()

if __name__ == "__main__":
    main()
