#!/bin/bash
# OpenAgent Setup Script
# Creates virtual environment and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔧 Setting up OpenAgent..."

# Check Python version
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Python 3.11+ is required but not found"
    exit 1
fi

echo "📦 Using $PYTHON_CMD (version $($PYTHON_CMD --version))"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📁 Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
else
    echo "📁 Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# Install the package in editable mode with dev dependencies
echo "📥 Installing OpenAgent and dependencies..."
pip install -e ".[dev]" --quiet

# Check if Rust/Cargo is available for TUI
if command -v cargo &> /dev/null; then
    echo "🦀 Rust found, building TUI..."
    cd TUI
    cargo build --release --quiet
    cd ..
    echo "✅ TUI built successfully"
else
    echo "⚠️  Rust not found - TUI will not be built"
    echo "   Install Rust from https://rustup.rs/ to build the TUI"
fi

# Create .env from example if it doesn't exist
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo "   Please edit .env with your Azure OpenAI credentials"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run OpenAgent:"
echo "  ./run.sh"
echo ""
echo "To run in offline mode (no backend):"
echo "  ./run.sh --offline"
