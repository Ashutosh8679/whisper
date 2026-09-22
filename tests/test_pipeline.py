from pathlib import Path

from src.recorder import Recorder
from src.whisper_engine import WhisperEngine


def test_recording_pipeline():
    recorder = Recorder()

    audio_path = recorder.start()

    assert isinstance(audio_path, Path)
    assert audio_path.exists()

    recorder.stop()

    assert audio_path.exists()
    assert audio_path.stat().st_size > 0

    engine = WhisperEngine()

    text, info = engine.transcribe(audio_path)

    assert isinstance(text, str)
    assert info is not None
