import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from src.audio_source import get_audio
from src.daemon import SOCKET_PATH
from src.recording_manager import RecordingManager
from src.wispr_engine import WisprEngine

def daemon_request(request):
    """
    Send a request to the running Wispr daemon
    and return its JSON response.
    """

    if not SOCKET_PATH.exists():
        raise RuntimeError(
            "Wispr daemon is not running."
        )

    client = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    try:
        client.connect(str(SOCKET_PATH))

        data = json.dumps(request).encode(
            "utf-8"
        )

        client.sendall(data)

        response = client.recv(65536)

        if not response:
            raise RuntimeError(
                "Wispr daemon closed the connection."
            )

        return json.loads(
            response.decode("utf-8")
        )

    finally:
        client.close()

def command_transcribe(audio_path=None):
    """
    Transcribe an audio file using the persistent
    Wispr daemon when it is running.

    If the daemon is not running, fall back to
    loading Wispr directly.
    """

    if audio_path is None:
        audio_path = get_audio()
    else:
        audio_path = Path(audio_path).expanduser().resolve()

    if not audio_path.exists():
        print("Error: audio file does not exist:")
        print(f"  {audio_path}")
        return 1

    print(f"Audio: {audio_path}")

    # --------------------------------------------------------
    # Try the persistent daemon first.
    # --------------------------------------------------------

    if SOCKET_PATH.exists():

        try:
            response = daemon_request(
                {
                    "command": "transcribe",
                    "audio": str(audio_path),
                }
            )

            if not response.get("success"):
                print(
                    "Daemon error:"
                )
                print(
                    response.get(
                        "error",
                        "Unknown daemon error",
                    )
                )

                return 1

            print("\n--- TRANSCRIPTION ---")
            print(response["text"])

            print("\n--- INFO ---")
            print(
                f"Language: "
                f"{response['language']}"
            )

            print(
                f"Probability: "
                f"{response['language_probability']:.2f}"
            )

            return 0

        except (
            ConnectionRefusedError,
            FileNotFoundError,
            ConnectionResetError,
            BrokenPipeError,
            OSError,
        ):
            print(
                "Warning: Wispr daemon could not "
                "be contacted."
            )

            print(
                "Falling back to one-shot transcription..."
            )

    # --------------------------------------------------------
    # Fallback: load Wispr directly.
    # --------------------------------------------------------

    engine = WisprEngine()

    text, info = engine.transcribe(
        audio_path
    )

    print("\n--- TRANSCRIPTION ---")
    print(text)

    print("\n--- INFO ---")
    print(f"Language: {info.language}")
    print(
        f"Probability: "
        f"{info.language_probability:.2f}"
    )

    return 0
    
    """
    Transcribe an audio file.

    This is the one-off transcription command.
    It loads Wispr for this request and exits.
    """

    if audio_path is None:
        audio_path = get_audio()
    else:
        audio_path = Path(audio_path).expanduser().resolve()

    if not audio_path.exists():
        print("Error: audio file does not exist:")
        print(f"  {audio_path}")
        return 1

    print(f"Audio: {audio_path}")

    engine = WisprEngine()

    text, info = engine.transcribe(audio_path)

    print("\n--- TRANSCRIPTION ---")
    print(text)

    print("\n--- INFO ---")
    print(f"Language: {info.language}")
    print(f"Probability: {info.language_probability:.2f}")

    return 0


def command_archive(audio_path):
    """
    Permanently archive an audio recording.
    """

    manager = RecordingManager()

    try:
        destination = manager.archive_recording(
            Path(audio_path)
        )

    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}")
        return 1

    print("Recording archived successfully.")
    print(f"From: {Path(audio_path).expanduser().resolve()}")
    print(f"To:   {destination}")

    return 0


def command_cleanup():
    """
    Remove recordings older than the configured retention period.
    """

    manager = RecordingManager()
    manager.cleanup_old_recordings()

    return 0


def command_daemon():
    """
    Start the persistent Wispr daemon.
    """

    from src.daemon import main as daemon_main

    daemon_main()

    return 0


def command_status():
    """
    Check whether the Wispr daemon is running.
    """

    if not SOCKET_PATH.exists():
        print("Wispr daemon: NOT RUNNING")
        return 1

    client = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    try:
        client.connect(str(SOCKET_PATH))

        request = {
            "command": "status",
        }

        client.sendall(
            json.dumps(request).encode("utf-8")
        )

        response = client.recv(65536)

        if response:
            data = json.loads(
                response.decode("utf-8")
            )

            if data.get("success"):
                print("Wispr daemon: RUNNING")
                print(f"Socket: {SOCKET_PATH}")
                return 0

        print("Wispr daemon: NOT RUNNING")
        return 1

    except (ConnectionRefusedError, FileNotFoundError, OSError):
        print("Wispr daemon: NOT RUNNING")
        return 1

    finally:
        client.close()


def command_kill():
    """
    Ask the Wispr daemon to shut itself down gracefully.
    """

    if not SOCKET_PATH.exists():
        print("Wispr daemon is not running.")
        return 0

    try:
        response = daemon_request(
            {
                "command": "shutdown",
            }
        )

        if not response.get("success"):
            print("Daemon refused shutdown request.")
            print(
                response.get(
                    "error",
                    "Unknown daemon error.",
                )
            )

            return 1

        print("Wispr daemon shutdown requested.")
        print("Wispr model will be unloaded from VRAM.")

        return 0

    except (
        ConnectionRefusedError,
        FileNotFoundError,
        ConnectionResetError,
        BrokenPipeError,
        OSError,
    ):
        print(
            "Wispr daemon could not be contacted."
        )

        return 1
        
    """
    Stop the Wispr daemon and release GPU memory.
    """

    if not SOCKET_PATH.exists():
        print("Wispr daemon is not running.")
        return 0

    # Find the daemon process using the socket.
    try:
        import subprocess

        result = subprocess.run(
            [
                "fuser",
                str(SOCKET_PATH),
            ],
            capture_output=True,
            text=True,
        )

        pids = []

        for token in result.stdout.split():
            if token.isdigit():
                pids.append(int(token))

        if not pids:
            print("Wispr socket exists, but no daemon process was found.")
            print("Removing stale socket.")

            SOCKET_PATH.unlink(missing_ok=True)

            return 0

        for pid in pids:
            print(f"Stopping Wispr daemon (PID {pid})...")
            os.kill(pid, signal.SIGTERM)

        print("Wispr daemon stopped.")
        print("Wispr model should now be unloaded from VRAM.")

        return 0

    except Exception as error:
        print(f"Error stopping Wispr daemon: {error}")
        return 1


def command_configure():
    """
    Interactive configuration wizard.
    """

    from src.config.manager import ConfigManager
    from src.audio.factory import get_audio_backend

    manager = ConfigManager()

    print()
    print("========================================")
    print("       Wispr Audio Configuration")
    print("========================================")
    print()

    print("How should Wispr select your microphone?")
    print()
    print("  1. Use the system default input")
    print("  2. Choose a specific input device")
    print("  3. Cancel")
    print()

    while True:
        choice = input("Selection [1-3]: ").strip()

        if choice in {"1", "2", "3"}:
            break

        print("Please enter 1, 2, or 3.")

    # --------------------------------------------------------
    # DEFAULT INPUT
    # --------------------------------------------------------

    if choice == "1":

        manager.set_audio_config(
            mode="default",
            source=None,
        )

        print()
        print("✓ Audio source configured.")
        print("  Mode: System default input")
        print()
        print(f"Configuration saved to:")
        print(f"  {manager.config_file}")

        return 0

    # --------------------------------------------------------
    # CANCEL
    # --------------------------------------------------------

    if choice == "3":

        print()
        print("Configuration cancelled.")

        return 0

    # --------------------------------------------------------
    # SPECIFIC DEVICE
    # --------------------------------------------------------

    print()
    print("Scanning for audio input devices...")
    print()

    try:
        backend = get_audio_backend()
        
        # Discover and probe Bluetooth devices first
        if hasattr(backend, 'discover_bluetooth_devices'):
            backend.discover_bluetooth_devices()
        
        sources = backend.list_microphones()

    except RuntimeError as error:

        print(f"Error: {error}")

        return 1

    if not sources:

        print("No physical audio input devices were detected.")
        print()
        print(
            "Connect a microphone and run "
            "'wispr configure' again."
        )

        return 1

    print("Available input devices:")
    print()

    for number, source in enumerate(
        sources,
        start=1,
    ):
        print(
            f"  {number}. "
            f"{source.display_name()}"
        )

        print(
            f"     {source.name}"
        )

        print()

    while True:

        selection = input(
            f"Select an input [1-{len(sources)}]: "
        ).strip()

        try:
            index = int(selection)

        except ValueError:
            print("Please enter a number.")
            continue

        if 1 <= index <= len(sources):
            break

        print(
            f"Please enter a number from "
            f"1 to {len(sources)}."
        )

    selected_source = sources[index - 1]

    manager.set_audio_config(
        mode="device",
        source=selected_source.name,
    )

    print()
    print("✓ Audio source configured.")
    print(f"  Device: {selected_source.display_name()}")
    print(f"  Source: {selected_source.name}")
    print()
    print("Configuration saved to:")
    print(f"  {manager.config_file}")

    return 0

def command_model(args):
    """
    Manage the active Wispr model.
    """

    from src.model_manager import (
        SUPPORTED_MODELS,
        get_config_file,
        get_current_model,
        set_current_model,
    )

    if args.action is None:
        print(f"Current model: {get_current_model()}")
        return 0

    if args.action == "list":
        current_model = get_current_model()

        print("Supported Wispr models:")
        print()

        for model in SUPPORTED_MODELS:
            marker = "*" if model == current_model else " "
            print(f" {marker} {model}")

        return 0

    if args.action == "set":
        model = args.model

        if model not in SUPPORTED_MODELS:
            print(f"Error: unsupported Wispr model: {model}")
            return 1

        current_model = get_current_model()

        if model == current_model:
            print(f"Wispr model is already set to: {model}")
            return 0

        set_current_model(model)

        print(f"Wispr model set to: {model}")
        print(f"Configuration: {get_config_file()}")
        print()
        print("Restarting Wispr daemon...")
        print(f"Loading Wispr {model}...")

        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "--user",
                    "restart",
                    "wispr.service",
                ],
                capture_output=True,
                text=True,
            )

        except FileNotFoundError:
            print("Error: systemctl is not available.")
            return 1

        if result.returncode != 0:
            print("Error: failed to restart Wispr daemon.")

            if result.stderr.strip():
                print(result.stderr.strip())

            return 1

        print("Waiting for Wispr daemon to become ready...")

        deadline = time.monotonic() + 300

        while time.monotonic() < deadline:
            try:
                response = daemon_request(
                    {
                        "command": "status",
                    }
                )

                if response.get("success"):
                    print()
                    print("Wispr daemon ready.")
                    print(f"Active model: {get_current_model()}")
                    return 0

            except (
                ConnectionRefusedError,
                FileNotFoundError,
                ConnectionResetError,
                BrokenPipeError,
                OSError,
                json.JSONDecodeError,
            ):
                pass

            time.sleep(0.5)

        print()
        print("Error: Wispr daemon did not become ready.")
        print()
        print("Check the daemon with:")
        print("  systemctl --user status wispr.service")
        print()
        print("The selected model remains configured as:")
        print(f"  {get_current_model()}")

        return 1

    return 1

def build_parser():
    parser = argparse.ArgumentParser(
        prog="wispr",
        description="Local Wispr transcription system",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # --------------------------------------------------------
    # configure
    # --------------------------------------------------------

    subparsers.add_parser(
        "configure",
        help="Configure Wispr",
    )

    # --------------------------------------------------------
    # transcribe
    # --------------------------------------------------------

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe an audio file",
    )

    transcribe_parser.add_argument(
        "audio",
        nargs="?",
        help="Audio file to transcribe",
    )

    # --------------------------------------------------------
    # daemon
    # --------------------------------------------------------

    subparsers.add_parser(
        "daemon",
        help="Start the persistent Wispr daemon",
    )

    # --------------------------------------------------------
    # status
    # --------------------------------------------------------

    subparsers.add_parser(
        "status",
        help="Check whether the Wispr daemon is running",
    )

    # --------------------------------------------------------
    # archive
    # --------------------------------------------------------

    archive_parser = subparsers.add_parser(
        "archive",
        help="Permanently archive a recording",
    )

    archive_parser.add_argument(
        "audio",
        help="Recording to archive",
    )

    # --------------------------------------------------------
    # cleanup
    # --------------------------------------------------------

    subparsers.add_parser(
        "cleanup",
        help="Delete recordings older than the retention period",
    )

    # --------------------------------------------------------
    # kill
    # --------------------------------------------------------

    subparsers.add_parser(
        "kill",
        help="Stop the Wispr daemon and release GPU memory",
    )

    # --------------------------------------------------------
    # model
    # --------------------------------------------------------

    model_parser = subparsers.add_parser(
        "model",
        help="Manage the active Wispr model",
    )

    model_subparsers = model_parser.add_subparsers(
        dest="action",
    )

    model_subparsers.add_parser(
        "list",
        help="List supported Wispr models",
    )

    model_set_parser = model_subparsers.add_parser(
        "set",
        help="Select the Wispr model",
    )

    model_set_parser.add_argument(
        "model",
        choices=(
            "tiny",
            "base",
            "small",
            "medium",
            "large-v1",
            "large-v2",
            "large-v3",
        ),
        help="Wispr model to use",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "configure":
        return command_configure()

    if args.command == "transcribe":
        return command_transcribe(args.audio)

    if args.command == "daemon":
        return command_daemon()

    if args.command == "status":
        return command_status()

    if args.command == "archive":
        return command_archive(args.audio)

    if args.command == "cleanup":
        return command_cleanup()

    if args.command == "kill":
        return command_kill()

    if args.command == "model":
        return command_model(args)

    parser.print_help()

    return 1


if __name__ == "__main__":
    sys.exit(main())