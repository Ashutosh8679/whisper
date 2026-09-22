from faster_whisper import WhisperModel

from config.config import (
    DEVICE,
    COMPUTE_TYPE,
    BEAM_SIZE,
)

from src.model_manager import get_current_model


class WhisperEngine:
    """Whisper transcription engine."""

    def __init__(self):
        self.model_name = get_current_model()

        print(
            f"Loading Whisper {self.model_name} "
            f"on {DEVICE.upper()} ({COMPUTE_TYPE})..."
        )

        self.model = WhisperModel(
            self.model_name,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

        print("Whisper loaded.")

    def transcribe(self, audio_path):
        """Transcribe an audio file."""

        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=BEAM_SIZE,
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        return text, info