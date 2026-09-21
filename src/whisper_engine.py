from faster_whisper import WhisperModel

from config.config import (
    MODEL_SIZE,
    DEVICE,
    COMPUTE_TYPE,
    BEAM_SIZE,
)


class WhisperEngine:
    def __init__(self):
        print(
            f"Loading Whisper {MODEL_SIZE} "
            f"on {DEVICE.upper()} ({COMPUTE_TYPE})..."
        )

        self.model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

        print("Whisper loaded.")

    def transcribe(self, audio_path):
        print(f"Transcribing: {audio_path}")

        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=BEAM_SIZE,
        )

        text = "".join(segment.text for segment in segments).strip()

        return text, info
