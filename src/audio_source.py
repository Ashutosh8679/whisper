from pathlib import Path

from config.config import TEST_AUDIO


def get_audio() -> Path:
    """
    Return the optional development/test audio file.

    This helper exists for the legacy one-shot transcription
    test path. Live microphone recording is handled by Recorder.
    """

    if not TEST_AUDIO.exists():
        raise FileNotFoundError(
            f"Test audio file does not exist: {TEST_AUDIO}"
        )

    return TEST_AUDIO