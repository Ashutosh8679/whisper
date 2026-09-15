#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_DIR/.venv"

LOCAL_BIN="$HOME/.local/bin"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

WHISPER_LAUNCHER="$LOCAL_BIN/whisper"
HOTKEY_LAUNCHER="$LOCAL_BIN/whisper-hotkey"

echo "=============================================="
echo " Whisper Local Dictation Installer"
echo "=============================================="
echo
echo "Project: $PROJECT_DIR"
echo "Virtual environment: $VENV"
echo

# ------------------------------------------------------------
# Basic dependency checks
# ------------------------------------------------------------

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $1"
        echo
        echo "Install the corresponding system package and run"
        echo "this installer again."
        exit 1
    fi
}

require_command python3
require_command systemctl
require_command install

# ------------------------------------------------------------
# Python version check
# ------------------------------------------------------------

PYTHON_VERSION="$(
    python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
)"

PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION##*.}"

if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 10) )); then
    echo "ERROR: Python 3.10 or newer is required."
    echo "Detected: Python $PYTHON_VERSION"
    exit 1
fi

echo "Python: $PYTHON_VERSION"
echo

# ------------------------------------------------------------
# Create virtual environment
# ------------------------------------------------------------

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
else
    echo "Virtual environment already exists."
fi

echo

# ------------------------------------------------------------
# Install Python dependencies
# ------------------------------------------------------------

echo "Installing Whisper Python dependencies..."

"$VENV/bin/python" -m pip install \
    -r "$PROJECT_DIR/requirements.txt"

echo

# ------------------------------------------------------------
# Install user launchers
#
# The repository launchers determine PROJECT_DIR relative to
# their location. Once copied into ~/.local/bin, that would
# incorrectly point at ~/.local.
#
# Therefore the installer creates wrappers with the actual
# installation-time project path embedded.
# ------------------------------------------------------------

echo "Installing user launchers..."

mkdir -p "$LOCAL_BIN"

TEMP_WHISPER="$(mktemp)"
TEMP_HOTKEY="$(mktemp)"

cleanup_temp() {
    rm -f "$TEMP_WHISPER" "$TEMP_HOTKEY"
}

trap cleanup_temp EXIT

{
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'PROJECT_DIR=%q\n' "$PROJECT_DIR"
    echo 'VENV="$PROJECT_DIR/.venv"'
    echo
    sed \
        -e '/^SCRIPT_DIR=/d' \
        -e '/^PROJECT_DIR=/d' \
        -e '/^VENV=/d' \
        "$PROJECT_DIR/scripts/whisper"
} > "$TEMP_WHISPER"

{
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'PROJECT_DIR=%q\n' "$PROJECT_DIR"
    echo 'VENV="$PROJECT_DIR/.venv"'
    echo
    sed \
        -e '/^SCRIPT_DIR=/d' \
        -e '/^PROJECT_DIR=/d' \
        -e '/^VENV=/d' \
        "$PROJECT_DIR/scripts/whisper-hotkey"
} > "$TEMP_HOTKEY"

install -m 755 \
    "$TEMP_WHISPER" \
    "$WHISPER_LAUNCHER"

install -m 755 \
    "$TEMP_HOTKEY" \
    "$HOTKEY_LAUNCHER"

echo "Installed:"
echo "  $WHISPER_LAUNCHER"
echo "  $HOTKEY_LAUNCHER"

echo

# ------------------------------------------------------------
# Install systemd user services
# ------------------------------------------------------------

echo "Installing systemd user services..."

mkdir -p "$SYSTEMD_USER_DIR"

install -m 644 \
    "$PROJECT_DIR/systemd/whisper.service" \
    "$SYSTEMD_USER_DIR/whisper.service"

install -m 644 \
    "$PROJECT_DIR/systemd/whisper-hotkey.service" \
    "$SYSTEMD_USER_DIR/whisper-hotkey.service"

echo "Installed:"
echo "  $SYSTEMD_USER_DIR/whisper.service"
echo "  $SYSTEMD_USER_DIR/whisper-hotkey.service"

echo

# ------------------------------------------------------------
# Reload systemd
# ------------------------------------------------------------

echo "Reloading user systemd manager..."

systemctl --user daemon-reload

# ------------------------------------------------------------
# Enable services
# ------------------------------------------------------------

echo "Enabling Whisper services..."

systemctl --user enable whisper.service
systemctl --user enable whisper-hotkey.service

echo

# ------------------------------------------------------------
# Start/restart services
# ------------------------------------------------------------

echo "Starting Whisper daemon..."

systemctl --user restart whisper.service

echo "Starting Whisper hotkey service..."

systemctl --user restart whisper-hotkey.service

echo

# ------------------------------------------------------------
# Give services a moment to initialize
# ------------------------------------------------------------

sleep 3

# ------------------------------------------------------------
# Verification
# ------------------------------------------------------------

echo "=============================================="
echo " Installation verification"
echo "=============================================="
echo

echo "----- Launcher -----"

if "$WHISPER_LAUNCHER" status; then
    echo
    echo "Whisper launcher: OK"
else
    echo
    echo "ERROR: Whisper daemon is not responding."
    echo
    echo "Check:"
    echo "  systemctl --user status whisper.service"
    echo "  journalctl --user -u whisper.service -n 100 --no-pager"
    exit 1
fi

echo
echo "----- Services -----"

systemctl --user --no-pager --full status \
    whisper.service \
    whisper-hotkey.service

echo
echo "=============================================="
echo " Installation complete."
echo "=============================================="
echo
echo "Whisper commands:"
echo "  whisper status"
echo "  whisper configure"
echo "  whisper cleanup"
echo "  whisper archive"
echo "  whisper kill"
echo
echo "Hold-to-talk:"
echo "  Super + Space"
echo
echo "If ~/.local/bin is not in PATH, add:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo
