#!/bin/bash
# ============================================================
#   Retirement Planner — Mac Startup Script
#   Double-click this file in Finder to launch the app.
#
#   First time only: if macOS blocks it, right-click the file
#   and choose "Open", then click "Open" in the dialog.
# ============================================================

# Change to the folder containing this script
cd "$(dirname "$0")"

echo ""
echo "======================================================"
echo "  Retirement Planner"
echo "  Starting server..."
echo "======================================================"
echo ""

# ── Find Python 3 ────────────────────────────────────────────
PYTHON=""

# Try common locations in order of preference
for candidate in python3 python python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" &>/dev/null; then
        VER=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        if [ "$VER" = "3" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

# Check Homebrew locations if not found yet
if [ -z "$PYTHON" ]; then
    for brew_path in \
        /usr/local/bin/python3 \
        /opt/homebrew/bin/python3 \
        "$HOME/.pyenv/shims/python3"; do
        if [ -x "$brew_path" ]; then
            PYTHON="$brew_path"
            break
        fi
    done
fi

# ── Not found ─────────────────────────────────────────────────
if [ -z "$PYTHON" ]; then
    echo "  ERROR: Python 3 is not installed."
    echo ""
    echo "  Install options:"
    echo "    A) Download from https://www.python.org/downloads/"
    echo "    B) Install Homebrew (https://brew.sh) then run:"
    echo "         brew install python"
    echo ""
    echo "  After installing Python, run this file again."
    echo ""
    read -p "Press Enter to open python.org in your browser... "
    open "https://www.python.org/downloads/"
    exit 1
fi

echo "  Found: $PYTHON ($("$PYTHON" --version 2>&1))"
echo ""
echo "  Your browser will open automatically at http://localhost:5000"
echo "  Close this window (or press Ctrl+C) to stop the app."
echo ""

"$PYTHON" app.py
