from pathlib import Path


# ============================================================
# AUDIO SOURCE
# ============================================================

# "dummy"  -> use test1.mp3 for development
# "pipewire" -> use the actual microphone
AUDIO_SOURCE = "dummy"

# Temporary development audio source.
TEST_AUDIO = Path.home() / "Downloads" / "test1.mp3"


# ============================================================
# RECORDING STORAGE
# ============================================================

# All recordings live here.
RECORDINGS_DIR = Path.home() / "AI" / "whisper" / "recordings"

# Recordings older than this many days are automatically deleted.
RETENTION_DAYS = 7


# ============================================================
# WHISPER
# ============================================================

MODEL_SIZE = "small"

DEVICE = "cuda"

COMPUTE_TYPE = "float16"

BEAM_SIZE = 5
