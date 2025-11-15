#!/bin/bash
set -e

echo "🚀 Setting up RealtimeVoiceClient..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
uv sync

# Initialize git submodules (DTLN-aec)
echo "📦 Initializing git submodules..."
git submodule update --init --recursive

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.sample to .env and configure your API keys"
echo "  2. Run 'npm run dev' to start the desktop app"
