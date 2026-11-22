import os
import subprocess
import sys
import time
from pathlib import Path

from src.cli import daemon_request
from src.recorder import Recorder
from src.x11_hotkey import X11Hotkey
from src.kde_wayland_hotkey import KDEWaylandHotkey


LOG_FILE = (
    Path(
        os.environ.get(
            "XDG_STATE_HOME",
            Path.home() / ".local" / "state",
        )
    )
    / "wispr"
    / "hotkey.log"
)
WISPR_SERVICE = "wispr.service"


def log(message):
    LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"

    print(line, flush=True)

    with LOG_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(line + "\n")


def create_hotkey():
    """
    Select the appropriate global hotkey backend
    for the current graphical session.
    """

    session_type = os.environ.get(
        "XDG_SESSION_TYPE",
        "",
    ).lower()

    if session_type == "wayland":
        log("Display server detected: Wayland")
        log("Using KDE KGlobalAccel hotkey backend.")
        return KDEWaylandHotkey()

    if session_type == "x11":
        log("Display server detected: X11")
        log("Using pynput X11 hotkey backend.")
        return X11Hotkey()

    raise RuntimeError(
        "Unsupported or unknown display server: "
        f"{session_type!r}"
    )


def wispr_is_running():
    """Return True when the Wispr systemd service is active."""

    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "is-active",
            "--quiet",
            WISPR_SERVICE,
        ],
        check=False,
    )

    return result.returncode == 0


def ensure_wispr_running():
    """
    Make sure the Wispr daemon is running.

    If it was manually stopped with `wispr kill`,
    start it and wait until the daemon responds to requests.
    """

    if wispr_is_running():
        return

    log("Wispr daemon is not running.")
    log("Starting Wispr service...")

    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "start",
            WISPR_SERVICE,
        ],
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to start wispr.service."
        )

    log("Wispr service started.")
    log("Waiting for Wispr daemon to become ready...")

    socket_path = (
        Path.home()
        / ".cache"
        / "wispr"
        / "wispr.sock"
    )

    deadline = time.monotonic() + 60

    while time.monotonic() < deadline:
        if not wispr_is_running():
            raise RuntimeError(
                "Wispr service stopped while starting."
            )

        if socket_path.exists():
            time.sleep(0.25)

            if wispr_is_running():
                log("Wispr daemon is ready.")
                return

        time.sleep(0.25)

    raise RuntimeError(
        "Timed out waiting for Wispr daemon to become ready."
    )


def start_dictation():
    """Start a dictation recording."""

    ensure_wispr_running()

    log("Starting dictation...")

    recorder = Recorder()
    recorder.start()

    log("RECORDING ACTIVE.")

    return recorder


def stop_dictation(recorder):
    """Stop recording, transcribe through the daemon, and paste."""

    log("Stopping dictation...")

    recording_path = recorder.stop()

    log(f"Recording saved: {recording_path}")
    log("Sending recording to Wispr daemon...")

    response = daemon_request(
        {
            "command": "transcribe",
            "audio": str(recording_path),
        }
    )

    if not response.get("success"):
        raise RuntimeError(
            response.get(
                "error",
                "Wispr transcription failed.",
            )
        )

    text = response.get(
        "text",
        "",
    ).strip()

    log(f"Wispr result: {text!r}")

    if not text:
        log("Wispr returned empty text.")
        return ""

    paste_text(text)

    log("SUCCESS: transcription pasted.")

    return text


def paste_text(text):
    """
    Copy text to the desktop clipboard and paste it using ydotool.

    Uses wl-copy on Wayland and xclip on X11.
    """

    session_type = os.environ.get(
        "XDG_SESSION_TYPE",
        "",
    ).lower()

    if session_type == "wayland":
        clipboard_command = [
            "wl-copy",
        ]

        clipboard_name = "Wayland clipboard"

    else:
        clipboard_command = [
            "xclip",
            "-selection",
            "clipboard",
        ]

        clipboard_name = "X11 clipboard"

    log(f"Copying transcription to {clipboard_name}...")

    subprocess.run(
        clipboard_command,
        input=text,
        text=True,
        check=True,
    )

    time.sleep(0.2)

    log("Pasting transcription with ydotool...")

    subprocess.run(
        [
            "ydotool",
            "key",
            "ctrl+v",
        ],
        check=True,
    )


def run_hold_to_talk():
    """Run the global Super+Space hold-to-talk loop."""

    hotkey = create_hotkey()

    hotkey.start()

    log("Global hotkey listener started.")
    log("Hold Super+Space to dictate.")
    log("Release either key to stop and transcribe.")

    try:
        while True:
            hotkey.wait_for_activation()

            recorder = None

            try:
                recorder = start_dictation()

                hotkey.wait_for_release()

                stop_dictation(recorder)

            except Exception as error:
                log(
                    f"ERROR during dictation: "
                    f"{type(error).__name__}: {error}"
                )

                if recorder is not None:
                    try:
                        recorder.stop()
                    except Exception:
                        pass

    except KeyboardInterrupt:
        log("Hotkey listener interrupted.")

    finally:
        hotkey.close()
        log("Global hotkey listener stopped.")


def run_single_dictation():
    """Manual test mode; starts immediately and stops on Enter."""

    recorder = None

    try:
        recorder = start_dictation()

        input("Press Enter to stop recording...")

        stop_dictation(recorder)

    except KeyboardInterrupt:
        log("Interrupted.")

        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass

    except Exception as error:
        log(
            f"ERROR: {type(error).__name__}: {error}"
        )

        return 1

    return 0


def main():
    LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    log("=" * 60)
    log("WISPR DICTATION")

    try:
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()

            if command == "start":
                run_hold_to_talk()
                return 0

            if command == "test":
                return run_single_dictation()

            raise ValueError(
                f"Unknown command: {command}. "
                f"Use 'start' or 'test'."
            )

        return run_hold_to_talk()

    except Exception as error:
        log(
            f"ERROR: {type(error).__name__}: {error}"
        )

        return 1

    finally:
        log("WISPR DICTATION FINISHED")
        log("=" * 60)


if __name__ == "__main__":
    raise SystemExit(main())