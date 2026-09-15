from pathlib import Path
import os


# ============================================================
# APPLICATION DIRECTORIES
# ============================================================

def get_data_dir() -> Path:
    """
    Return the user's XDG data directory for Whisper.

    Uses XDG_DATA_HOME when available and falls back to:
        ~/.local/share
    """

    xdg_data_home = os.environ.get("XDG_DATA_HOME")

    if xdg_data_home:
        return Path(xdg_data_home) / "whisper"

    return Path.home() / ".local" / "share" / "whisper"


# ============================================================
# AUDIO SOURCE
# ============================================================

# This setting is retained for the legacy one-shot development
# transcription command.
#
# "dummy"    -> use TEST_AUDIO
# "pipewire" -> reserved for future direct microphone handling
AUDIO_SOURCE = "dummy"


# Optional development/test audio file.
#
# This file is intentionally outside the repository so personal
# recordings or test media are never committed to Git.
TEST_AUDIO = (
    Path.home()
    / "Downloads"
    / "test1.mp3"
)


# ============================================================
# RECORDING STORAGE
# ============================================================

# Runtime recordings are stored in the user's XDG data directory.
#
# Example:
#     ~/.local/share/whisper/recordings/
#
# This keeps recordings outside the Git repository.
RECORDINGS_DIR = (
    get_data_dir()
    / "recordings"
)


# Recordings older than this many days are automatically deleted.
RETENTION_DAYS = 7


# ============================================================
# WHISPER
# ============================================================

# Whisper model size.
#
# Supported values depend on faster-whisper.
MODEL_SIZE = "small"


# Inference device.
#
# "cuda" requires a compatible NVIDIA CUDA environment.
# "cpu" can be used on systems without NVIDIA CUDA support.
DEVICE = "cuda"


# Computation type used by faster-whisper.
COMPUTE_TYPE = "float16"


# Beam search width used during transcription.
BEAM_SIZE = 5