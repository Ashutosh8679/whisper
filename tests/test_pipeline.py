from src.audio_source import get_audio
from src.whisper_engine import WhisperEngine


def main():
    print("Getting audio source...")
    audio = get_audio()

    print(f"Audio source: {audio}")

    engine = WhisperEngine()

    text, info = engine.transcribe(audio)

    print("\n--- TRANSCRIPTION ---")
    print(text)

    print("\n--- INFO ---")
    print(f"Language: {info.language}")
    print(f"Probability: {info.language_probability:.2f}")

    print("\n--- DONE ---")


if __name__ == "__main__":
    main()
