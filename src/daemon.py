import json
import os
import socket
import signal
import sys
from pathlib import Path

from src.wispr_engine import WisprEngine


SOCKET_PATH = Path.home() / ".cache" / "wispr" / "wispr.sock"
PID_FILE = Path.home() / ".cache" / "wispr" / "wispr.pid"


class WisprDaemon:
    """
    Persistent Wispr transcription daemon.

    Wispr is loaded once and remains in memory while the
    daemon waits for requests over a Unix domain socket.
    """

    def __init__(self):
        self.socket_path = SOCKET_PATH
        self.running = True

        self.socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Check if daemon is already running
        if self._is_running():
            print("Wispr daemon is already running.")
            sys.exit(0)

        print("Starting Wispr daemon...")
        print("Loading Wispr Small onto GPU...")

        self.engine = WisprEngine()

        print("Wispr daemon ready.")
        print(f"Socket: {self.socket_path}")

        # Write PID file
        self._write_pid()

    def _is_running(self):
        """Check if another daemon instance is running."""
        if not PID_FILE.exists():
            return False
        
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file stale or process doesn't exist
            return False

    def _write_pid(self):
        """Write current process PID to file."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def _cleanup_pid(self):
        """Remove PID file on shutdown."""
        if PID_FILE.exists():
            PID_FILE.unlink()

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print("\nReceived shutdown signal.")
        self.running = False

    def remove_old_socket(self):
        """
        Remove a stale socket left behind by a previous daemon.
        """

        if self.socket_path.exists():
            self.socket_path.unlink()
        
        # Also clean up stale PID file
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                # Check if it's a different process
                if pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        # Different process is still running
                        return
                    except (ProcessLookupError, PermissionError):
                        # Stale PID file
                        PID_FILE.unlink()
            except (ValueError, ProcessLookupError, PermissionError):
                PID_FILE.unlink()

    def start(self):
        """
        Start the Unix socket server.
        """

        self.remove_old_socket()

        # Set up signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        server.bind(str(self.socket_path))

        # Only the current user can communicate with the daemon.
        os.chmod(self.socket_path, 0o600)

        server.listen(5)

        print("Wispr daemon is waiting for requests...")

        try:
            while self.running:
                connection, _ = server.accept()

                try:
                    self.handle_request(connection)

                except Exception as error:
                    print(f"Request error: {error}")

                    response = {
                        "success": False,
                        "error": str(error),
                    }

                    self.send_response(
                        connection,
                        response,
                    )

                finally:
                    connection.close()

        finally:
            server.close()

            if self.socket_path.exists():
                self.socket_path.unlink()

            self._cleanup_pid()

            # Explicitly release the Wispr engine.
            self.engine = None

            print("Wispr daemon stopped.")

    def handle_request(self, connection):
        """
        Receive and process one request.
        """

        data = connection.recv(65536)

        if not data:
            return

        request = json.loads(
            data.decode("utf-8")
        )

        command = request.get("command")

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if command == "status":

            response = {
                "success": True,
                "status": "running",
            }

            self.send_response(
                connection,
                response,
            )

            return

        # ----------------------------------------------------
        # SHUTDOWN
        # ----------------------------------------------------

        if command == "shutdown":

            print("Shutdown request received.")

            response = {
                "success": True,
                "status": "shutting_down",
            }

            self.send_response(
                connection,
                response,
            )

            self.running = False

            return

        # ----------------------------------------------------
        # TRANSCRIBE
        # ----------------------------------------------------

        if command == "transcribe":

            audio_path = Path(
                request["audio"]
            ).expanduser().resolve()

            if not audio_path.exists():
                raise FileNotFoundError(
                    f"Audio file does not exist: {audio_path}"
                )

            print(
                f"Transcription request: {audio_path}"
            )

            text, info = self.engine.transcribe(
                audio_path
            )

            response = {
                "success": True,
                "text": text,
                "language": info.language,
                "language_probability": (
                    info.language_probability
                ),
            }

            self.send_response(
                connection,
                response,
            )

            return

        # ----------------------------------------------------
        # UNKNOWN COMMAND
        # ----------------------------------------------------

        raise ValueError(
            f"Unknown command: {command}"
        )

    @staticmethod
    def send_response(connection, response):
        """
        Send a JSON response to the client.
        """

        data = json.dumps(
            response
        ).encode("utf-8")

        connection.sendall(data)


def main():
    daemon = WisprDaemon()
    daemon.start()


if __name__ == "__main__":
    main()