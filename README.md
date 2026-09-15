# Whisper Local Dictation

A fully local, system-wide hold-to-talk speech-to-text dictation system for Linux (KDE Plasma Wayland & X11). Powered by [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), CUDA acceleration, PipeWire/PulseAudio, and `ydotool`.

Press **`Super + Space`**, talk, release — your spoken text is instantly transcribed locally and pasted into your active window.

---

## Key Features

-  **100% Local & Private:** No cloud APIs required. Speech recognition runs entirely on your GPU via CUDA.
-  **Instant Transcription:** Persistent daemon keeps the model loaded in GPU memory for low latency.
-  **Hold-to-Talk Hotkey (`Super + Space`):** Native global shortcut integration for both KDE Wayland (`KGlobalAccel`) and X11 (`pynput`).
-  **Smart Bluetooth Handling:** Automatically switches Bluetooth headsets from high-quality playback (A2DP) to a hands-free microphone profile during dictation, restoring your audio state immediately afterward.
-  **Seamless Auto-Paste:** Leverages the system clipboard and `ydotool` to inject text directly into whatever application currently has focus.
-  **User-Level Systemd Services:** Runs unobtrusively in the background via `systemctl --user`.

---

## System Architecture & Workflow

```
┌────────────────────────┐
│  User: Super + Space   │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐    Wayland: KDE KGlobalAccel via D-Bus
│    Hotkey Controller   ├──────────────────────────────────────┐
└───────────┬────────────┘    X11:     pynput                   │
            │                                                   │
            ▼                                                   │
┌────────────────────────┐                                      │
│   Recording Manager    │◄─────────────────────────────────────┘
└───────────┬────────────┘
            │ 1. Switch Bluetooth Profile (if required)
            │ 2. Capture Audio (16kHz Mono PCM via parec)
            ▼
┌────────────────────────┐
│   Whisper Daemon IPC   │ (Unix Domain Socket: ~/.cache/whisper/whisper.sock)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Faster-Whisper + CUDA  │ (Inference via persistent Python daemon)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Clipboard + ydotool    │ 1. Restore Audio/Bluetooth Profile
└───────────┬────────────┘ 2. Copy transcription to Clipboard & Trigger Paste
            │
            ▼
┌────────────────────────┐
│  Focused Application   │ (Text appears at cursor)
└────────────────────────┘
```

---

## Requirements

### Target Environment
- **OS:** Linux (Validated on Arch Linux)
- **Desktop:** KDE Plasma (Wayland and X11 supported)
- **Python:** Python 3.10+
- **GPU:** NVIDIA GPU with a compatible NVIDIA driver (Validated on RTX 3060 12GB)

### System Dependencies
- `pipewire` / `pulseaudio` stack (`pactl` and `parec` binaries required)
- `ydotool` (for simulated keypress pasting)
- `NVIDIA CUDA Toolkit` / `cuDNN` / `cuBLAS` runtime libraries

### Python Dependencies
- `faster-whisper >= 1.2, < 2`
- `dbus-next >= 0.2, < 1`
- `pynput >= 1.7, < 2`

---

## Project Structure

```text
whisper/
├── README.md                  # System documentation & usage guide
├── LICENSE                    # License file
├── requirements.txt           # Python dependency definitions
├── install.sh                 # One-step automated installer script
├── .gitignore                 # Excluded build artifacts, logs, and virtual environments
├── config/
│   ├── __init__.py
│   └── config.py              # Main application parameters (model, audio settings, paths)
├── src/
│   ├── audio_source.py        # Legacy/test audio source interface
│   ├── audio_sources.py       # Audio source discovery helpers
│   ├── cli.py                 # CLI interface handler
│   ├── daemon.py              # Persistent Whisper background process & Unix socket IPC
│   ├── hotkey.py              # Hotkey engine coordinator & paste manager
│   ├── kde_wayland_hotkey.py  # KDE KGlobalAccel D-Bus hotkey implementation
│   ├── recorder.py            # Audio recording, parec pipeline & Bluetooth profile manager
│   ├── recording_manager.py   # Recording lifecycle & 7-day file retention manager
│   ├── whisper_engine.py      # Faster-Whisper CUDA engine loader
│   ├── x11_hotkey.py          # X11 pynput keyboard listener
│   └── config/
│       ├── __init__.py
│       └── manager.py         # Configuration loader/manager
├── scripts/
│   ├── whisper                # CLI launcher script
│   └── whisper-hotkey         # Hotkey daemon launcher script
├── systemd/
│   ├── whisper.service        # Systemd user service unit for daemon
│   └── whisper-hotkey.service # Systemd user service unit for hotkey listener
└── tests/
    ├── test_pipeline.py       # End-to-end processing pipeline tests
    └── test_recorder.py       # Audio capture and device tests
```

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone <REPOSITORY_URL>
   cd whisper
   ```

2. **Run the installer:**
   ```bash
   ./install.sh
   ```

The installer script will automatically:
- Create a Python virtual environment (`.venv`) and install all Python packages.
- Generate standalone launchers in `~/.local/bin/`.
- Install and enable user-level `systemd` units (`whisper.service` and `whisper-hotkey.service`).
- Start both services immediately.

3. **Verify installation:**
   ```bash
   systemctl --user is-active whisper.service whisper-hotkey.service
   ls -l ~/.local/bin/whisper ~/.local/bin/whisper-hotkey
   ```

> **Note:** Executable launchers store absolute paths to your repository. If you move the project directory, simply re-run `./install.sh`.

---

## Usage & Service Management

Once installed, dictation works system-wide automatically:
1. **Hold `Super + Space`** and speak into your microphone.
2. **Release `Super + Space`** to end recording.
3. The transcription will automatically paste into your active text cursor location.

### Managing Services

```bash
# Check service status & daemon status
whisper status
systemctl --user status whisper.service whisper-hotkey.service

# Restart services
systemctl --user restart whisper.service whisper-hotkey.service

# Stop services (e.g., to free VRAM)
systemctl --user stop whisper.service whisper-hotkey.service
```

---

## Configuration

The default configuration file is located at `config/config.py`:

```python
from pathlib import Path
import os

def get_data_dir() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "whisper"
    return Path.home() / ".local" / "share" / "whisper"

AUDIO_SOURCE = "dummy"
TEST_AUDIO = Path.home() / "Downloads" / "test1.mp3"
RECORDINGS_DIR = get_data_dir() / "recordings"
RETENTION_DAYS = 7
MODEL_SIZE = "small"     # Faster-Whisper model size (tiny, base, small, medium, large-v3)
DEVICE = "cuda"          # Options: "cuda", "cpu"
COMPUTE_TYPE = "float16" # Options: "float16", "int8_float16", "float32"
BEAM_SIZE = 5
```

### Runtime Data Paths

- **IPC Socket & Runtime:** `~/.cache/whisper/` (or `$XDG_CACHE_HOME/whisper/`)
- **Persistent Data & Audio Logs:** `~/.local/share/whisper/recordings/` (Auto-cleaned after 7 days)
- **Application Logs:** `~/.local/state/whisper/` (or `$XDG_STATE_HOME/whisper/`)

---

## Desktop Environment Integration

### Wayland (KDE Plasma)
Uses `src/kde_wayland_hotkey.py` to register shortcuts via **KGlobalAccel** over D-Bus:
- **Service:** `org.kde.kglobalaccel`
- **Component:** `whisper` | **Action:** `hold_to_talk` | **Shortcut:** `Super + Space`
- Releasing either key stops the active recording session.

### X11 (KDE Plasma / General X11)
Uses `src/x11_hotkey.py` with `pynput` to monitor global key states independently, maintaining active recording as long as the key combination is depressed.

---

## Troubleshooting & Diagnostics

Run a full system diagnostic using the following script snippet:

```bash
echo "=== SESSION ==="
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
echo "DISPLAY=$DISPLAY"

echo -e "\n=== SERVICES ==="
systemctl --user is-active whisper.service whisper-hotkey.service

echo -e "\n=== GPU / WHISPER ==="
nvidia-smi
whisper status

echo -e "\n=== AUDIO & BLUETOOTH ==="
pactl get-default-source
pactl list cards short | grep bluez
```

### Common Issues

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| **Hotkey does not trigger** | Hotkey service crashed or wrong session type detected | Run `systemctl --user restart whisper-hotkey.service` and check `journalctl --user -u whisper-hotkey.service -f`. |
| **CUDA Error / Model fail** | Missing NVIDIA runtime libraries or VRAM full | Check `nvidia-smi`. Verify libraries in virtual environment: `./.venv/bin/python -c "import faster_whisper"`. |
| **Audio not recording** | `parec` unable to access default input source | Verify default mic: `pactl get-default-source`. Test audio setup with `pactl list sources short`. |
| **Text transcribed but not pasted** | `ydotool` daemon not running or missing permissions | Test `which ydotool`. Check if transcription is copied to clipboard manually (`ctrl+v`). |

### Viewing Logs

```bash
# Watch Whisper Daemon logs
journalctl --user -u whisper.service -f

# Watch Hotkey Service logs
journalctl --user -u whisper-hotkey.service -f
```

---

## Development & Testing

1. **Setup Development Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run Syntax Check & Test Suites:**
   ```bash
   python -m compileall src config
   python tests/test_recorder.py
   python tests/test_pipeline.py
   ```

3. **Manual CLI Testing:**
   ```bash
   ./scripts/whisper status
   ./scripts/whisper daemon
   ```

---

## Privacy & Security

- **100% On-Device Processing:** Speech-to-text processing occurs strictly on your local GPU. Audio stream data is never transmitted to external servers.
- **Data Cleanup:** Microphones capture temporary PCM files stored locally under `~/.local/share/whisper/recordings/` and are automatically deleted based on the retention policy (`RETENTION_DAYS = 7`).

---

## License

This project is licensed under the terms included in the [LICENSE](LICENSE) file.
