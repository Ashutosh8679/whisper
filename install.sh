#!/usr/bin/env bash
set -euo pipefail

OS="$(uname -s)"

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT_DIR/.venv"

echo "=============================================="
echo " Wispr Local Dictation Installer"
echo "=============================================="
echo
echo "Operating system: $OS"
echo "Project: $PROJECT_DIR"
echo "Virtual environment: $VENV"
echo


install_linux_dependencies() {
    echo "Checking Linux runtime dependencies..."
    echo

    local missing_commands=()

    command -v python3 >/dev/null 2>&1 || missing_commands+=("python3")
    command -v systemctl >/dev/null 2>&1 || missing_commands+=("systemctl")
    command -v install >/dev/null 2>&1 || missing_commands+=("install")
    command -v udevadm >/dev/null 2>&1 || missing_commands+=("udevadm")

    if ((${#missing_commands[@]} > 0)); then
        echo "ERROR: Required system commands are missing:"
        printf '  - %s\n' "${missing_commands[@]}"
        echo
        echo "Please install the corresponding system packages and"
        echo "run this installer again."
        exit 1
    fi

    local package_manager=""
    local package_args=()

    if command -v apt-get >/dev/null 2>&1; then
        package_manager="apt-get"
        package_args=(xclip ydotool)
    elif command -v pacman >/dev/null 2>&1; then
        package_manager="pacman"
        package_args=(xclip ydotool)
    elif command -v dnf >/dev/null 2>&1; then
        package_manager="dnf"
        package_args=(xclip ydotool)
    elif command -v zypper >/dev/null 2>&1; then
        package_manager="zypper"
        package_args=(xclip ydotool)
    elif command -v apk >/dev/null 2>&1; then
        package_manager="apk"
        package_args=(xclip ydotool)
    else
        echo "ERROR: No supported Linux package manager was found."
        echo
        echo "Supported package managers:"
        echo "  apt, pacman, dnf, zypper, apk"
        exit 1
    fi

    local packages_to_install=()

    for package in "${package_args[@]}"; do
        case "$package_manager" in
            apt-get)
                if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null \
                    | grep -q "install ok installed"; then
                    packages_to_install+=("$package")
                fi
                ;;
            pacman)
                if ! pacman -Q "$package" >/dev/null 2>&1; then
                    packages_to_install+=("$package")
                fi
                ;;
            dnf)
                if ! rpm -q "$package" >/dev/null 2>&1; then
                    packages_to_install+=("$package")
                fi
                ;;
            zypper)
                if ! rpm -q "$package" >/dev/null 2>&1; then
                    packages_to_install+=("$package")
                fi
                ;;
            apk)
                if ! apk info -e "$package" >/dev/null 2>&1; then
                    packages_to_install+=("$package")
                fi
                ;;
        esac
    done

    if ((${#packages_to_install[@]} > 0)); then
        echo "Installing Linux input/clipboard dependencies:"
        printf '  - %s\n' "${packages_to_install[@]}"
        echo

        case "$package_manager" in
            apt-get)
                sudo apt-get update
                sudo apt-get install -y "${packages_to_install[@]}"
                ;;
            pacman)
                sudo pacman -S --needed --noconfirm "${packages_to_install[@]}"
                ;;
            dnf)
                sudo dnf install -y "${packages_to_install[@]}"
                ;;
            zypper)
                sudo zypper --non-interactive install "${packages_to_install[@]}"
                ;;
            apk)
                sudo apk add "${packages_to_install[@]}"
                ;;
        esac

        echo
    else
        echo "xclip and ydotool are already installed."
        echo
    fi

    if ! getent group input >/dev/null 2>&1; then
        echo "Creating input group..."
        sudo groupadd input
        echo
    fi

    local uinput_rule="/etc/udev/rules.d/99-wispr-uinput.rules"

    echo "Configuring /dev/uinput access..."
    sudo tee "$uinput_rule" >/dev/null <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF

    sudo udevadm control --reload-rules
    sudo udevadm trigger --name-match=uinput

    echo "Installed udev rule:"
    echo "  $uinput_rule"
    echo

    local current_groups
    current_groups="$(id -nG)"

    if printf '%s\n' "$current_groups" | tr ' ' '\n' | grep -qx input; then
        echo "Current user already belongs to the input group."
        echo
    else
        echo "Adding $USER to the input group..."
        sudo usermod -aG input "$USER"
        echo
        echo "IMPORTANT:"
        echo "Your current login session does not yet have the new"
        echo "input-group membership."
        echo
        echo "Log out and log back in before using Wispr's"
        echo "ydotool-based paste functionality."
        echo
        echo "The Wispr services will not be started by this"
        echo "installer until the new group membership is active."
        echo
        return 10
    fi

    if [[ -e /dev/uinput ]]; then
        echo "uinput device:"
        ls -l /dev/uinput
        echo
    else
        echo "WARNING: /dev/uinput does not currently exist."
        echo "ydotool may require the uinput kernel module."
        echo
    fi
}


install_linux() {
    local LOCAL_BIN="$HOME/.local/bin"
    local SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    local WISPR_LAUNCHER="$LOCAL_BIN/wispr"
    local HOTKEY_LAUNCHER="$LOCAL_BIN/wispr-hotkey"

    local dependency_status=0

    if install_linux_dependencies; then
        dependency_status=0
    else
        dependency_status=$?
        if ((dependency_status != 10)); then
            exit "$dependency_status"
        fi
    fi

    if ((dependency_status == 10)); then
        echo "Continuing installation without starting services."
        echo
    elif ((dependency_status != 0)); then
        exit "$dependency_status"
    fi

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

    if [[ ! -x "$VENV/bin/python" ]]; then
        echo "Creating virtual environment..."
        python3 -m venv "$VENV"
    else
        echo "Virtual environment already exists."
    fi

    echo

    echo "Installing Wispr Python dependencies..."
    "$VENV/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
    echo

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
            "$PROJECT_DIR/scripts/wispr"
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
            "$PROJECT_DIR/scripts/wispr-hotkey"
    } > "$TEMP_HOTKEY"

    install -m 755 "$TEMP_WHISPER" "$WISPR_LAUNCHER"
    install -m 755 "$TEMP_HOTKEY" "$HOTKEY_LAUNCHER"

    echo "Installed:"
    echo "  $WISPR_LAUNCHER"
    echo "  $HOTKEY_LAUNCHER"
    echo

    echo "Installing systemd user services..."
    mkdir -p "$SYSTEMD_USER_DIR"

    install -m 644 \
        "$PROJECT_DIR/systemd/wispr.service" \
        "$SYSTEMD_USER_DIR/wispr.service"

    install -m 644 \
        "$PROJECT_DIR/systemd/wispr-hotkey.service" \
        "$SYSTEMD_USER_DIR/wispr-hotkey.service"

    echo "Installed:"
    echo "  $SYSTEMD_USER_DIR/wispr.service"
    echo "  $SYSTEMD_USER_DIR/wispr-hotkey.service"
    echo

    echo "Reloading user systemd manager..."
    systemctl --user daemon-reload

    echo "Enabling Wispr services..."
    systemctl --user enable wispr.service
    systemctl --user enable wispr-hotkey.service
    echo

    if ((dependency_status == 10)); then
        echo "=============================================="
        echo " Installation prepared"
        echo "=============================================="
        echo
        echo "Wispr has been installed, but the services were"
        echo "not started because your current session does not"
        echo "yet have input-group access."
        echo
        echo "Log out and log back in, then run:"
        echo
        echo "  $PROJECT_DIR/install.sh"
        echo
        return 0
    fi

    echo "Starting Wispr daemon..."
    systemctl --user restart wispr.service

    echo "Starting Wispr hotkey service..."
    systemctl --user restart wispr-hotkey.service

    echo
    echo "Waiting for Wispr daemon to become ready..."

    DAEMON_READY=0

    for _ in {1..30}; do
        if "$WISPR_LAUNCHER" status >/dev/null 2>&1; then
            DAEMON_READY=1
            break
        fi
        sleep 1
    done

    if ((DAEMON_READY == 0)); then
        echo
        echo "ERROR: Wispr daemon did not become ready within 30 seconds."
        echo
        echo "----- Wispr service status -----"
        systemctl --user --no-pager --plain status wispr.service
        echo
        echo "----- Recent Wispr logs -----"
        journalctl --user -u wispr.service -n 30 --no-pager
        exit 1
    fi

    echo "Wispr daemon is ready."
    echo

    echo "=============================================="
    echo " Installation verification"
    echo "=============================================="
    echo

    echo "----- Launcher -----"

    if "$WISPR_LAUNCHER" status; then
        :
    else
        echo
        echo "ERROR: Wispr launcher verification failed."
        exit 1
    fi

    echo

    echo "----- Services -----"
    systemctl --user --no-pager --plain status \
        wispr.service \
        wispr-hotkey.service

    echo

    echo "=============================================="
    echo " Installation complete"
    echo "=============================================="
}


install_macos() {
    echo "ERROR: macOS installation is not implemented yet."
    exit 1
}


install_windows() {
    echo "ERROR: Windows installation is not implemented yet."
    exit 1
}


case "$OS" in
    Linux)
        install_linux
        ;;
    Darwin)
        install_macos
        ;;
    MINGW*|MSYS*|CYGWIN*)
        install_windows
        ;;
    *)
        echo "ERROR: Unsupported operating system: $OS"
        exit 1
        ;;
esac