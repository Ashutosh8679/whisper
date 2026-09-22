from datetime import datetime
from pathlib import Path

from src.audio.factory import get_audio_backend
from src.config.manager import ConfigManager
from config.config import RECORDINGS_DIR


class Recorder:
    """
    High-level recording manager.

    Audio capture is delegated to the platform audio backend.
    The recorder itself handles configuration, microphone
    selection, recording paths, and recording lifecycle.
    """

    def __init__(self):
        self.config_manager = ConfigManager()
        self.backend = get_audio_backend()

        self.microphone = None
        self.wav_path = None
        self.recording = False

    def get_source(self):
        """
        Determine which microphone should be recorded.

        'default' uses the system default microphone.

        'device' uses the configured microphone source.
        """

        audio_config = self.config_manager.get_audio_config()

        mode = audio_config.get("mode", "default")
        source = audio_config.get("source")

        if mode == "default":
            return self.backend.get_default_microphone()

        if mode == "device":
            if not source:
                raise RuntimeError(
                    "Audio mode is 'device', but no audio source "
                    "has been configured."
                )

            for microphone in self.backend.list_microphones():
                if (
                    microphone.id == source
                    or microphone.name == source
                ):
                    return microphone

            raise RuntimeError(
                f"Configured audio source was not found: {source}"
            )

        raise RuntimeError(
            f"Unknown audio configuration mode: {mode}"
        )

    def create_paths(self):
        """
        Create a timestamped path for the recording.
        """

        now = datetime.now()

        date_directory = (
            RECORDINGS_DIR / now.strftime("%Y-%m-%d")
        )

        date_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = now.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        self.wav_path = (
            date_directory
            / f"{filename}.wav"
        )

    def start(self):
        """
        Start recording.

        Returns the path that will contain the completed WAV
        recording after stop() is called.
        """

        if self.recording:
            raise RuntimeError(
                "Recording is already in progress."
            )

        self.create_paths()

        microphone = self.get_source()

        if microphone is None:
            raise RuntimeError(
                "No microphone is currently available."
            )

        self.microphone = microphone

        print(
            f"Audio backend: {self.backend.name}"
        )

        print(
            f"Microphone: {microphone.display_name()}"
        )

        print(
            f"Output: {self.wav_path}"
        )

        try:
            self.backend.prepare_microphone(
                microphone
            )

            self.backend.start_recording(
                microphone,
                self.wav_path,
            )

            self.recording = True

        except Exception:
            self.microphone = None

            try:
                self.backend.restore_microphone()
            except Exception:
                pass

            raise

        print("Recording started.")

        return self.wav_path

    def stop(self):
        """
        Stop the active recording.

        Returns the completed WAV path.
        """

        if not self.recording:
            raise RuntimeError(
                "No recording is currently in progress."
            )

        print("Stopping recording...")

        try:
            self.backend.stop_recording()

            if not self.wav_path.exists():
                raise RuntimeError(
                    "Recording failed: WAV file "
                    "was not created."
                )

            if self.wav_path.stat().st_size == 0:
                raise RuntimeError(
                    "Recording failed: WAV file "
                    "contains no audio data."
                )

            print(
                f"Recording saved: {self.wav_path}"
            )

            return self.wav_path

        finally:
            self.recording = False
            self.microphone = None

            try:
                self.backend.restore_microphone()
            except Exception as error:
                print(
                    "Warning: could not restore "
                    f"microphone state: {error}"
                )