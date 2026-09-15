from pathlib import Path

from config.config import TEST_AUDIO


def get_audio() -> Path:
    """
    Temporary dummy audio source.

    For now, this simply returns test1.mp3.
    Later this function will be replaced with the
    PipeWire microphone recording implementation.
    """

    if not TEST_AUDIO.exists():
        raise FileNotFoundError(
            f"Test audio file does not exist: {TEST_AUDIO}"
        )

    return TEST_AUDIO
