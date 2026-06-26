#!/bin/bash
# ============================================================
#   Build Retirement Planner — Mac Standalone App
#
#   Creates RetirementPlanner.app that anyone can double-click
#   without needing Python installed.
#
#   Run this ONCE on your Mac. Requires Python 3 + internet
#   (to download PyInstaller the first time).
#
#   Usage:
#     1. Open Terminal
#     2. Drag this file into Terminal and press Enter
#        (or: cd to this folder and run: bash build_mac_app.sh)
# ============================================================

cd "$(dirname "$0")"

echo ""
echo "======================================================"
echo "  Build Retirement Planner — Mac App"
echo "======================================================"
echo ""

# ── Find Python 3 ────────────────────────────────────────────
PYTHON=""
for candidate in python3 python3.12 python3.11 python3.10 python3.9 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" &>/dev/null 2>&1 || [ -x "$candidate" ]; then
        VER=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        if [ "$VER" = "3" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ERROR: Python 3 not found."
    echo "  Install from https://www.python.org/ or via Homebrew: brew install python"
    exit 1
fi

echo "  Using: $PYTHON ($("$PYTHON" --version 2>&1))"
echo ""

# ── Install PyInstaller ───────────────────────────────────────
echo "  Installing PyInstaller..."
"$PYTHON" -m pip install pyinstaller --quiet
if [ $? -ne 0 ]; then
    echo "  ERROR: Could not install PyInstaller."
    echo "  Try: $PYTHON -m pip install pyinstaller"
    exit 1
fi

# ── Build .app bundle ─────────────────────────────────────────
echo ""
echo "  Building RetirementPlanner.app (this takes ~30 seconds)..."
echo ""

"$PYTHON" -m PyInstaller RetirementPlanner_mac.spec --noconfirm

if [ $? -ne 0 ]; then
    echo ""
    echo "  ERROR: Build failed. See output above for details."
    exit 1
fi

# ── Move .app to current folder ───────────────────────────────
if [ -d "dist/RetirementPlanner.app" ]; then
    rm -rf "RetirementPlanner.app"
    cp -R "dist/RetirementPlanner.app" "RetirementPlanner.app"
    echo ""
    echo "======================================================"
    echo "  SUCCESS!"
    echo "  RetirementPlanner.app is ready in this folder."
    echo ""
    echo "  To share: zip the .app and send it."
    echo "  Recipients: double-click RetirementPlanner.app"
    echo "  (First time: right-click → Open to bypass Gatekeeper)"
    echo "======================================================"
    echo ""
else
    echo "  ERROR: .app not found after build."
    exit 1
fi
