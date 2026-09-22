from abc import ABC, abstractmethod
from pathlib import Path

from src.audio.microphone import Microphone


class AudioBackend(ABC):
    """
    Backend interface for microphone discovery, preparation,
    recording, and restoration.

    Concrete implementations handle platform/audio-system-specific
    details such as PipeWire, PulseAudio, or other audio APIs.
    """

    @abstractmethod
    def list_microphones(self) -> list[Microphone]:
        """
        Return all usable physical microphones available to the system.

        Playback monitors and other non-microphone sources should not
        be returned.
        """
        raise NotImplementedError

    @abstractmethod
    def get_default_microphone(self) -> Microphone | None:
        """
        Return the microphone currently selected by the operating system.

        Return None if no usable default microphone can be determined.
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_microphone(self, microphone: Microphone) -> None:
        """
        Prepare the microphone for recording.

        This may involve backend-specific operations such as changing
        Bluetooth profiles or selecting an audio source.
        """
        raise NotImplementedError

    @abstractmethod
    def restore_microphone(self) -> None:
        """
        Restore the audio state that existed before recording began.
        """
        raise NotImplementedError

    @abstractmethod
    def start_recording(
        self,
        microphone: Microphone,
        output_path: Path,
    ) -> None:
        """
        Start recording from the specified microphone.

        The backend is responsible for creating and managing the
        underlying recording process.
        """
        raise NotImplementedError

    @abstractmethod
    def stop_recording(self) -> None:
        """
        Stop the active recording process.
        """
        raise NotImplementedError