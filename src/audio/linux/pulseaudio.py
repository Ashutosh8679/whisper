import shutil
import subprocess
import wave
from pathlib import Path

from src.audio.microphone import Microphone
from src.audio.backend import AudioBackend


class PulseAudioBackend(AudioBackend):
    name = "pulseaudio"

    def __init__(self):
        self.process = None
        self._raw_output_path = None
        self._output_path = None

    def is_available(self) -> bool:
        return (
            shutil.which("pactl") is not None
            and shutil.which("parec") is not None
        )

    def _run_pactl(self, *args: str) -> str:
        result = subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def list_microphones(self) -> list[Microphone]:
        output = self._run_pactl("list", "short", "sources")

        microphones = []

        for line in output.splitlines():
            parts = line.split("\t")

            if len(parts) < 2:
                continue

            source_id = parts[0]
            source_name = parts[1]

            # Ignore monitor sources; they capture sink output rather
            # than physical microphone input.
            if source_name.endswith(".monitor"):
                continue

            description = source_name

            microphones.append(
                Microphone(
                    id=source_id,
                    name=source_name,
                    description=description,
                    is_bluetooth=(
                        "bluez" in source_name.lower()
                        or "bluetooth" in source_name.lower()
                    ),
                    backend_data={
                        "source_name": source_name,
                    },
                )
            )

        return microphones

    def get_default_microphone(self) -> Microphone | None:
        default_source = self._run_pactl("get-default-source").strip()

        if not default_source:
            return None

        for microphone in self.list_microphones():
            if microphone.name == default_source:
                return microphone

        return Microphone(
            id=default_source,
            name=default_source,
            description=default_source,
            is_bluetooth=(
                "bluez" in default_source.lower()
                or "bluetooth" in default_source.lower()
            ),
            backend_data={
                "source_name": default_source,
            },
        )

    def prepare_microphone(self, microphone: Microphone) -> None:
        return None

    def restore_microphone(self) -> None:
        return None

    def start_recording(
        self,
        microphone: Microphone,
        output_path: Path,
    ) -> None:
        if self.process is not None:
            raise RuntimeError("Recording is already active.")

        source_name = microphone.backend_data.get("source_name")

        if not source_name:
            raise RuntimeError(
                f"Microphone '{microphone.display_name()}' "
                "does not have a PulseAudio source name."
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        raw_output_path = output_path.with_suffix(".pcm")

        command = [
            "parec",
            "--device", source_name,
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16le",
            str(raw_output_path),
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "parec was not found. "
                "PulseAudio recording tools are required."
            ) from error

        self._raw_output_path = raw_output_path
        self._output_path = output_path

    def stop_recording(self) -> None:
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

        raw_output_path = self._raw_output_path
        output_path = self._output_path

        self._raw_output_path = None
        self._output_path = None

        if raw_output_path is None or output_path is None:
            raise RuntimeError(
                "PulseAudio recording paths were not initialized."
            )

        if not raw_output_path.exists():
            raise RuntimeError(
                f"PulseAudio recording produced no audio data: "
                f"{raw_output_path}"
            )

        if raw_output_path.stat().st_size == 0:
            raw_output_path.unlink()
            raise RuntimeError(
                "PulseAudio recording produced an empty audio file."
            )

        try:
            with raw_output_path.open("rb") as raw_file:
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_file.writeframes(raw_file.read())
        finally:
            if raw_output_path.exists():
                raw_output_path.unlink()