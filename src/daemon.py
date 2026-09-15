import json
import os
import socket
from pathlib import Path

from src.whisper_engine import WhisperEngine


SOCKET_PATH = Path.home() / ".cache" / "whisper" / "whisper.sock"


class WhisperDaemon:
    """
    Persistent Whisper transcription daemon.

    Whisper is loaded once and remains in memory while the
    daemon waits for requests over a Unix domain socket.
    """

    def __init__(self):
        self.socket_path = SOCKET_PATH
        self.running = True

        self.socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        print("Starting Whisper daemon...")
        print("Loading Whisper Small onto GPU...")

        self.engine = WhisperEngine()

        print("Whisper daemon ready.")
        print(f"Socket: {self.socket_path}")

    def remove_old_socket(self):
        """
        Remove a stale socket left behind by a previous daemon.
        """

        if self.socket_path.exists():
            self.socket_path.unlink()

    def start(self):
        """
        Start the Unix socket server.
        """

        self.remove_old_socket()

        server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        server.bind(str(self.socket_path))

        # Only the current user can communicate with the daemon.
        os.chmod(self.socket_path, 0o600)

        server.listen(5)

        print("Whisper daemon is waiting for requests...")

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

        except KeyboardInterrupt:
            print("\nStopping Whisper daemon...")

        finally:
            server.close()

            if self.socket_path.exists():
                self.socket_path.unlink()

            # Explicitly release the Whisper engine.
            self.engine = None

            print("Whisper daemon stopped.")

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
    daemon = WhisperDaemon()
    daemon.start()


if __name__ == "__main__":
    main()