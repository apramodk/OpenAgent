#!/bin/bash
# OpenAgent TUI launcher

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUI_BIN="$SCRIPT_DIR/TUI/target/release/openagent-tui"

# Parse arguments
OFFLINE=""
REBUILD=""
for arg in "$@"; do
    case $arg in
        --offline|-o)
            OFFLINE="--offline"
            ;;
        --rebuild|-r)
            REBUILD="1"
            ;;
        --help|-h)
            echo "Usage: ./run.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --offline, -o    Run without Python backend (mock responses)"
            echo "  --rebuild, -r    Rebuild TUI before running"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
    esac
done

# Build TUI if needed
if [ ! -f "$TUI_BIN" ] || [ -n "$REBUILD" ]; then
    echo "Building TUI..."
    cd "$SCRIPT_DIR/TUI"
    cargo build --release
fi

# Activate virtual environment for Python backend
if [ -z "$OFFLINE" ]; then
    if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
        source "$SCRIPT_DIR/.venv/bin/activate"
    else
        echo "Warning: Python venv not found at $SCRIPT_DIR/.venv"
        echo "Running in offline mode..."
        OFFLINE="--offline"
    fi
    export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
fi

# Run TUI
cd "$SCRIPT_DIR"
exec "$TUI_BIN" $OFFLINE
