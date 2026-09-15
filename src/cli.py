import argparse
import json
import os
import signal
import socket
import sys
from pathlib import Path

from src.audio_source import get_audio
from src.daemon import SOCKET_PATH
from src.recording_manager import RecordingManager
from src.whisper_engine import WhisperEngine

def daemon_request(request):
    """
    Send a request to the running Whisper daemon
    and return its JSON response.
    """

    if not SOCKET_PATH.exists():
        raise RuntimeError(
            "Whisper daemon is not running."
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
                "Whisper daemon closed the connection."
            )

        return json.loads(
            response.decode("utf-8")
        )

    finally:
        client.close()

def command_transcribe(audio_path=None):
    """
    Transcribe an audio file using the persistent
    Whisper daemon when it is running.

    If the daemon is not running, fall back to
    loading Whisper directly.
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
                "Warning: Whisper daemon could not "
                "be contacted."
            )

            print(
                "Falling back to one-shot transcription..."
            )

    # --------------------------------------------------------
    # Fallback: load Whisper directly.
    # --------------------------------------------------------

    engine = WhisperEngine()

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
    It loads Whisper for this request and exits.
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

    engine = WhisperEngine()

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
    Start the persistent Whisper daemon.
    """

    from src.daemon import main as daemon_main

    daemon_main()

    return 0


def command_status():
    """
    Check whether the Whisper daemon is running.
    """

    if not SOCKET_PATH.exists():
        print("Whisper daemon: NOT RUNNING")
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
                print("Whisper daemon: RUNNING")
                print(f"Socket: {SOCKET_PATH}")
                return 0

        print("Whisper daemon: NOT RUNNING")
        return 1

    except (ConnectionRefusedError, FileNotFoundError, OSError):
        print("Whisper daemon: NOT RUNNING")
        return 1

    finally:
        client.close()


def command_kill():
    """
    Ask the Whisper daemon to shut itself down gracefully.
    """

    if not SOCKET_PATH.exists():
        print("Whisper daemon is not running.")
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

        print("Whisper daemon shutdown requested.")
        print("Whisper model will be unloaded from VRAM.")

        return 0

    except (
        ConnectionRefusedError,
        FileNotFoundError,
        ConnectionResetError,
        BrokenPipeError,
        OSError,
    ):
        print(
            "Whisper daemon could not be contacted."
        )

        return 1
        
    """
    Stop the Whisper daemon and release GPU memory.
    """

    if not SOCKET_PATH.exists():
        print("Whisper daemon is not running.")
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
            print("Whisper socket exists, but no daemon process was found.")
            print("Removing stale socket.")

            SOCKET_PATH.unlink(missing_ok=True)

            return 0

        for pid in pids:
            print(f"Stopping Whisper daemon (PID {pid})...")
            os.kill(pid, signal.SIGTERM)

        print("Whisper daemon stopped.")
        print("Whisper model should now be unloaded from VRAM.")

        return 0

    except Exception as error:
        print(f"Error stopping Whisper daemon: {error}")
        return 1


def command_configure():
    """
    Interactive configuration wizard.
    """

    from src.config.manager import ConfigManager
    from src.audio_sources import list_audio_sources

    manager = ConfigManager()

    print()
    print("========================================")
    print("       Whisper Audio Configuration")
    print("========================================")
    print()

    print("How should Whisper select your microphone?")
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
        sources = list_audio_sources()

    except RuntimeError as error:

        print(f"Error: {error}")

        return 1

    if not sources:

        print("No physical audio input devices were detected.")
        print()
        print(
            "Connect a microphone and run "
            "'whisper configure' again."
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

def build_parser():
    parser = argparse.ArgumentParser(
        prog="whisper",
        description="Local Whisper transcription system",
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
        help="Configure Whisper",
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
        help="Start the persistent Whisper daemon",
    )

    # --------------------------------------------------------
    # status
    # --------------------------------------------------------

    subparsers.add_parser(
        "status",
        help="Check whether the Whisper daemon is running",
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
        help="Stop the Whisper daemon and release GPU memory",
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

    parser.print_help()

    return 1


if __name__ == "__main__":
    sys.exit(main())