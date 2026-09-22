import platform

from src.audio.backend import AudioBackend


def get_audio_backend() -> AudioBackend:
    """
    Detect the operating system and return the appropriate
    audio backend.
    """
    system = platform.system()

    if system == "Linux":
        from src.audio.linux.backend import LinuxAudioBackend

        return LinuxAudioBackend()

    if system == "Windows":
        raise RuntimeError(
            "Windows audio support is not implemented yet."
        )

    if system == "Darwin":
        raise RuntimeError(
            "macOS audio support is not implemented yet."
        )

    raise RuntimeError(
        f"Unsupported operating system: {system}"
    )