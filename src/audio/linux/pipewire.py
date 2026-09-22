import shutil
import subprocess
import time
from pathlib import Path

from src.audio.backend import AudioBackend
from src.audio.microphone import Microphone

class PipeWireBackend(AudioBackend):
    """
    Linux audio backend using PipeWire/WirePlumber.

    The backend currently uses wpctl for audio-device discovery and
    default-source detection.
    """

    name = "pipewire"

    def __init__(self):
        self.process = None

    def is_available(self) -> bool:
        """
        Check whether the PipeWire control interface is available
        and responding.
        """
        if not shutil.which("wpctl"):
            return False

        try:
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

        return bool(result.stdout.strip())

    def _run_wpctl(self, *arguments) -> str:
        """
        Execute wpctl and return its stdout.
        """
        try:
            result = subprocess.run(
                ["wpctl", *arguments],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "wpctl was not found. "
                "PipeWire/WirePlumber tools are required."
            ) from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"wpctl command failed: "
                f"{' '.join(arguments)}\n"
                f"{error.stderr.strip()}"
            ) from error

        return result.stdout

    def _get_status(self) -> str:
        return self._run_wpctl("status")

    def list_microphones(self) -> list[Microphone]:
        """
        Return physical microphones from the PipeWire Audio -> Sources
        section.

        Playback monitors and video sources are intentionally excluded.
        """
        output = self._get_status()

        microphones = []
        in_audio = False
        in_sources = False

        for line in output.splitlines():
            stripped = line.strip()

            if stripped == "Audio":
                in_audio = True
                continue

            if not in_audio:
                continue

            if stripped in {"Video", "Settings"}:
                break

            if stripped in {"├─ Sources:", "└─ Sources:"}:
                in_sources = True
                continue

            if in_sources and (
                stripped.startswith("├─")
                or stripped.startswith("└─")
            ):
                break

            if not in_sources:
                continue

            if not stripped:
                continue

            entry = stripped.lstrip("│ ").strip()

            if entry.startswith("*"):
                entry = entry[1:].strip()

            if "." not in entry:
                continue

            node_id_text, description = entry.split(".", 1)

            node_id_text = node_id_text.strip()
            description = description.strip()

            if not node_id_text.isdigit() or not description:
                continue

            if "monitor" in description.lower():
                continue

            microphones.append(
                Microphone(
                    id=node_id_text,
                    name=description,
                    description=description,
                    is_bluetooth=(
                        "bluez" in description.lower()
                        or "bluetooth" in description.lower()
                    ),
                    backend_data={
                        "node_id": int(node_id_text),
                    },
                )
            )

        return microphones

    def get_default_microphone(self) -> Microphone | None:
        """
        Return the source marked with '*' in the Audio -> Sources section.
        """
        output = self._get_status()

        in_audio = False
        in_sources = False
        default_id = None

        for line in output.splitlines():
            stripped = line.strip()

            if stripped == "Audio":
                in_audio = True
                continue

            if not in_audio:
                continue

            if stripped in {"Video", "Settings"}:
                break

            if stripped in {"├─ Sources:", "└─ Sources:"}:
                in_sources = True
                continue

            if in_sources and (
                stripped.startswith("├─")
                or stripped.startswith("└─")
            ):
                break

            if not in_sources:
                continue

            if "*" not in stripped:
                continue

            entry = stripped.lstrip("│ ").strip()
            entry = entry.replace("*", "", 1).strip()

            if "." not in entry:
                continue

            node_id_text = entry.split(".", 1)[0].strip()

            if node_id_text.isdigit():
                default_id = node_id_text
                break

        if default_id is None:
            return None

        for microphone in self.list_microphones():
            if microphone.id == default_id:
                return microphone

        return None

    def prepare_microphone(self, microphone: Microphone) -> None:
        """
        Prepare a microphone for recording.

        Bluetooth profile handling will be implemented here later.
        """
        return None

    def restore_microphone(self) -> None:
        """
        Restore audio state after recording.

        No state restoration is required yet because preparation does
        not modify the PipeWire graph at this stage.
        """
        return None

    def start_recording(
        self,
        microphone: Microphone,
        output_path: Path,
    ) -> None:
        """
        Start recording from the specified PipeWire microphone.

        The resulting file is a WAV recording at 16 kHz mono.
        """
        if self.process is not None:
            raise RuntimeError("A recording is already in progress.")

        node_id = microphone.backend_data.get("node_id")

        if node_id is None:
            raise RuntimeError(
                f"Microphone '{microphone.display_name()}' "
                "does not have a PipeWire node ID."
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            "pw-record",
            "--target",
            str(node_id),
            "--rate",
            "16000",
            "--channels",
            "1",
            "--format",
            "s16",
            str(output_path),
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "pw-record was not found. "
                "PipeWire recording tools are required."
            ) from error

        deadline = time.monotonic() + 2.0

        while time.monotonic() < deadline:
            if output_path.exists() and output_path.stat().st_size > 0:
                return

            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode(
                    errors="replace"
                ).strip()

                self.process = None

                raise RuntimeError(
                    "pw-record exited before recording started."
                    f"{f' Error: {stderr}' if stderr else ''}"
                )

            time.sleep(0.01)

        raise RuntimeError(
            "pw-record started, but did not create the output file "
            f"within 2 seconds: {output_path}"
        )

    def stop_recording(self) -> None:
        """
        Stop the active PipeWire recording process.
        """
        if self.process is None:
            return

        process = self.process
        self.process = None

        try:
            process.terminate()

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

        finally:
            if process.stdin is not None:
                process.stdin.close()

            if process.stderr is not None:
                process.stderr.close()