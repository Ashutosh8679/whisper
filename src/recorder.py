import subprocess
import time
import wave
from datetime import datetime
from pathlib import Path

from src.config.manager import ConfigManager
from config.config import RECORDINGS_DIR


SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM

# Airdopes 141 Elite ANC Bluetooth card.
BLUETOOTH_CARD = "bluez_card.24_DF_17_10_13_17"
HFP_PROFILE = "handsfree_head_unit"
HFP_SOURCE = "bluez_source.24_DF_17_10_13_17.handsfree_head_unit"


class Recorder:
    """
    Records audio from the configured input source.

    When the Airdopes Bluetooth microphone is available, the recorder
    temporarily switches the Bluetooth card to HFP before recording
    and restores the previous Bluetooth profile after recording.

    Audio is captured through the PulseAudio compatibility interface
    using parec, then stored as a WAV file.
    """

    def __init__(self):
        self.config_manager = ConfigManager()

        self.process = None
        self.raw_path = None
        self.wav_path = None

        # Bluetooth state saved before dictation.
        self.bluetooth_profile_before = None
        self.default_source_before = None
        self.bluetooth_switched = False

    def get_source(self):
        """
        Determine which audio source should be recorded.

        'default' means parec will use the system default source.

        'device' means the configured PipeWire/PulseAudio source
        name is passed explicitly to parec.
        """

        audio_config = self.config_manager.get_audio_config()

        mode = audio_config.get("mode", "default")
        source = audio_config.get("source")

        if mode == "default":
            return None

        if mode == "device":
            if not source:
                raise RuntimeError(
                    "Audio mode is 'device', but no audio source "
                    "has been configured."
                )

            return source

        raise RuntimeError(
            f"Unknown audio configuration mode: {mode}"
        )

    def create_paths(self):
        """
        Create timestamped temporary paths for the recording.
        """

        now = datetime.now()

        date_directory = (
            RECORDINGS_DIR / now.strftime("%Y-%m-%d")
        )

        date_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = now.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        self.raw_path = (
            date_directory
            / f"{filename}.raw"
        )

        self.wav_path = (
            date_directory
            / f"{filename}.wav"
        )

    def _run_pactl(self, *arguments, check=True):
        """
        Run pactl with the supplied arguments.
        """

        return subprocess.run(
            ["pactl", *arguments],
            capture_output=True,
            text=True,
            check=check,
        )

    def _get_bluetooth_profile(self):
        """
        Return the current profile of the Airdopes Bluetooth card.

        Returns None if the card is not currently available.
        """

        try:
            result = self._run_pactl(
                "list",
                "cards",
            )

        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

        card_text = result.stdout

        marker = f"Name: {BLUETOOTH_CARD}"

        if marker not in card_text:
            return None

        card_section = card_text.split(
            marker,
            1,
        )[1]

        # The next card begins at the next "Name:" entry.
        next_card = card_section.find("\nName:")

        if next_card != -1:
            card_section = card_section[:next_card]

        for line in card_section.splitlines():
            line = line.strip()

            if line.startswith("Active Profile:"):
                return line.split(":", 1)[1].strip()

        return None

    def _get_default_source(self):
        """
        Return the current PulseAudio/PipeWire default source.
        """

        try:
            result = self._run_pactl(
                "get-default-source",
            )

        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

        source = result.stdout.strip()

        return source or None

    def _bluetooth_card_available(self):
        """
        Check whether the Airdopes Bluetooth card currently exists.
        """

        try:
            result = self._run_pactl(
                "list",
                "cards",
            )

        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        return f"Name: {BLUETOOTH_CARD}" in result.stdout

    def _switch_to_bluetooth_microphone(self):
        """
        Temporarily switch the Airdopes to HFP microphone mode.

        The previous Bluetooth profile and default source are saved
        so they can be restored after recording.
        """

        if not self._bluetooth_card_available():
            print("Airdopes Bluetooth card not available.")
            return

        self.bluetooth_profile_before = (
            self._get_bluetooth_profile()
        )

        self.default_source_before = (
            self._get_default_source()
        )

        print(
            "Bluetooth profile before recording: "
            f"{self.bluetooth_profile_before or 'unknown'}"
        )

        print(
            "Default source before recording: "
            f"{self.default_source_before or 'unknown'}"
        )

        if self.bluetooth_profile_before == HFP_PROFILE:
            print(
                "Airdopes already in Handsfree Head Unit mode."
            )

            # Make sure the HFP microphone is the default source.
            self._set_hfp_source()

            return

        if self.bluetooth_profile_before != "a2dp_sink":
            print(
                "Airdopes profile is not A2DP; "
                "leaving Bluetooth profile unchanged."
            )
            return

        print(
            "Switching Airdopes: "
            "A2DP → Handsfree Head Unit..."
        )

        try:
            self._run_pactl(
                "set-card-profile",
                BLUETOOTH_CARD,
                HFP_PROFILE,
            )

        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "Failed to switch Airdopes to "
                "Handsfree Head Unit mode."
            ) from error

        # PipeWire may need a short moment to create the HFP source.
        self._set_hfp_source()

        self.bluetooth_switched = True

        print(
            "Airdopes microphone is now active."
        )

    def _set_hfp_source(self):
        """
        Make the Airdopes HFP microphone the default source.

        PipeWire can take a short moment to expose the source after
        changing the Bluetooth profile, so retry for a few seconds.
        """

        last_error = None

        for _ in range(20):
            try:
                self._run_pactl(
                    "set-default-source",
                    HFP_SOURCE,
                )

                print(
                    "Default source: "
                    f"{HFP_SOURCE}"
                )

                return

            except subprocess.CalledProcessError as error:
                last_error = error
                time.sleep(0.1)

        raise RuntimeError(
            "Airdopes switched to HFP, but the HFP "
            "microphone source could not be selected."
        ) from last_error

    def _restore_bluetooth_state(self):
        """
        Restore the Bluetooth profile and default source that were
        active before recording started.
        """

        if not self.bluetooth_profile_before:
            return

        print(
            "Restoring Bluetooth state..."
        )

        # Restore the previous profile if we changed it.
        if (
            self.bluetooth_switched
            and self.bluetooth_profile_before != HFP_PROFILE
        ):
            try:
                self._run_pactl(
                    "set-card-profile",
                    BLUETOOTH_CARD,
                    self.bluetooth_profile_before,
                )

                print(
                    "Bluetooth profile restored: "
                    f"{self.bluetooth_profile_before}"
                )

            except subprocess.CalledProcessError as error:
                print(
                    "Warning: could not restore Bluetooth "
                    f"profile: {error}"
                )

        # Restore the previous default source if it still exists.
        if self.default_source_before:
            try:
                self._run_pactl(
                    "set-default-source",
                    self.default_source_before,
                )

                print(
                    "Default source restored: "
                    f"{self.default_source_before}"
                )

            except subprocess.CalledProcessError as error:
                print(
                    "Warning: could not restore default "
                    f"source: {error}"
                )

        self.bluetooth_profile_before = None
        self.default_source_before = None
        self.bluetooth_switched = False

    def start(self):
        """
        Start recording.

        The returned WAV path becomes available after stop().
        """

        if self.process is not None:
            raise RuntimeError(
                "Recording is already in progress."
            )

        self.create_paths()

        source = self.get_source()

        # Only manage the Bluetooth profile when using the system
        # default source. Explicit device configurations are left alone.
        if source is None:
            self._switch_to_bluetooth_microphone()

            # The system default source may now be the HFP microphone.
            source = None

        command = [
            "parec",
            "--format=s16le",
            "--rate=16000",
            "--channels=1",
        ]

        if source is not None:
            command.append(
                f"--device={source}"
            )

        command.append(
            str(self.raw_path)
        )

        print("Starting recording...")
        print(f"Source: {source or 'system default'}")
        print(f"Output: {self.wav_path}")

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        except FileNotFoundError as error:
            self.process = None

            self._restore_bluetooth_state()

            raise RuntimeError(
                "parec was not found. "
                "Please install the PipeWire/PulseAudio utilities."
            ) from error

        except Exception:
            self.process = None

            self._restore_bluetooth_state()

            raise

        return self.wav_path

    def stop(self):
        """
        Stop the active recording and convert the raw PCM
        data into a WAV file.

        Bluetooth state is restored even when WAV conversion fails.
        """

        if self.process is None:
            raise RuntimeError(
                "No recording is currently in progress."
            )

        process = self.process
        self.process = None

        print("Stopping recording...")

        try:
            process.terminate()

            try:
                process.wait(timeout=3)

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            if not self.raw_path.exists():
                raise RuntimeError(
                    "Recording failed: raw audio file was not created."
                )

            self._convert_to_wav()

            try:
                self.raw_path.unlink()

            except OSError as error:
                print(
                    "Warning: could not remove temporary file: "
                    f"{error}"
                )

            print(
                f"Recording saved: {self.wav_path}"
            )

            return self.wav_path

        finally:
            # This executes even if recording/conversion fails.
            self._restore_bluetooth_state()

    def _convert_to_wav(self):
        """
        Convert raw 16-bit PCM into a standard WAV file.
        """

        with self.raw_path.open("rb") as raw_file:
            audio_data = raw_file.read()

        if not audio_data:
            raise RuntimeError(
                "Recording contains no audio data."
            )

        with wave.open(
            str(self.wav_path),
            "wb",
        ) as wav_file:

            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_data)