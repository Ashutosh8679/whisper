import shutil
import subprocess
import wave
from pathlib import Path

from src.audio.microphone import Microphone
from src.audio.backend import AudioBackend


class PulseAudioBackend(AudioBackend):
    name = "pulseaudio"

    def __init__(self):
        self.process = None
        self._raw_output_path = None
        self._output_path = None
        self._saved_profile = None
        self._saved_source = None

    def is_available(self) -> bool:
        return (
            shutil.which("pactl") is not None
            and shutil.which("parec") is not None
        )

    def _run_pactl(self, *args: str) -> str:
        result = subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def discover_bluetooth_devices(self) -> list[dict]:
        """
        Probe Bluetooth devices to detect which have microphone capability.
        
        This probes by temporarily switching to HFP profile, checking for
        an input source, then restoring the original profile. Results are
        cached in a JSON database.
        """
        import json
        import time
        from src.audio.linux.bluetooth import BluetoothDeviceDatabase
        
        db = BluetoothDeviceDatabase()
        cards_output = self._run_pactl("list", "cards", "short")
        
        for line in cards_output.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            
            card_id = parts[0]
            card_name = parts[1]
            
            if "bluez" not in card_name.lower() and "bluetooth" not in card_name.lower():
                continue
            
            # Get current profile
            try:
                profiles_output = self._run_pactl(
                    "list", "cards", "profiles", card_id
                )
            except subprocess.CalledProcessError:
                continue
            
            current_profile = None
            available_profiles = []
            
            for profile_line in profiles_output.splitlines():
                if ": HFP" in profile_line or "handsfree" in profile_line.lower():
                    available_profiles.append("hfp_handsfree")
                if "*:" in profile_line:
                    current_profile = profile_line.split(":")[0].strip().lstrip("*")
            
            # Get MAC address from card name
            if "." in card_name:
                mac_part = card_name.split(".")[1] if "." in card_name else ""
                # Remove underscores from hex representation to get proper MAC format
                mac = mac_part.replace("_", ":")
            else:
                continue
            
            # Check cache
            cached = db.get(card_name, mac)
            if cached:
                continue
            
            # Probe: temporarily switch to HFP, check for source, restore
            if "hfp_handsfree" in available_profiles:
                try:
                    # Save current state
                    self._run_pactl("set-card-profile", card_id, "hfp_handsfree")
                    time.sleep(0.5)
                    
                    # Check if input source appears
                    sources = self._run_pactl("list", "sources", "short")
                    # Sources are named like: bluez_source.24_DF_17_10_13_17.handsfree_head_unit
                    mac_with_underscores = mac.replace(":", "_")
                    has_input = any(
                        mac_with_underscores.lower() in src.lower()
                        for src in sources.splitlines()
                    )
                    
                    # Cache result
                    db.upsert(card_name, mac, has_input)
                    
                    # Restore profile
                    if current_profile:
                        self._run_pactl("set-card-profile", card_id, current_profile)
                    
                except Exception:
                    pass

    def list_microphones(self) -> list[Microphone]:
        output = self._run_pactl("list", "short", "sources")

        microphones = []

        for line in output.splitlines():
            parts = line.split("\t")

            if len(parts) < 2:
                continue

            source_id = parts[0]
            source_name = parts[1]

            # Ignore monitor sources; they capture sink output rather
            # than physical microphone input.
            if source_name.endswith(".monitor"):
                continue

            description = source_name

            microphones.append(
                Microphone(
                    id=source_id,
                    name=source_name,
                    description=description,
                    is_bluetooth=(
                        "bluez" in source_name.lower()
                        or "bluetooth" in source_name.lower()
                    ),
                    backend_data={
                        "source_name": source_name,
                    },
                )
            )

        return microphones

    def get_default_microphone(self) -> Microphone | None:
        default_source = self._run_pactl("get-default-source").strip()

        if not default_source:
            return None

        for microphone in self.list_microphones():
            if microphone.name == default_source:
                return microphone

        return Microphone(
            id=default_source,
            name=default_source,
            description=default_source,
            is_bluetooth=(
                "bluez" in default_source.lower()
                or "bluetooth" in default_source.lower()
            ),
            backend_data={
                "source_name": default_source,
            },
        )

    def prepare_microphone(self, microphone: Microphone) -> None:
        """
        Prepare the microphone for recording.
        
        For Bluetooth headsets in A2DP mode, this temporarily switches
        to HFP/HSP profile so the microphone becomes available.
        """
        import json
        import time
        from src.audio.linux.bluetooth import BluetoothDeviceDatabase
        
        if not microphone.is_bluetooth:
            return
        
        # Get card info from source name
        source_name = microphone.backend_data.get("source_name", "")
        if not source_name or "bluez" not in source_name.lower():
            return
        
        # Find the associated card
        try:
            output = self._run_pactl("list", "cards", "short")
        except subprocess.CalledProcessError:
            return
        
        card_id = None
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                cid, cname = parts[0], parts[1]
                if "bluez" in cname.lower():
                    card_id = cid
                    break
        
        if not card_id:
            return
        
        # Get current profile
        try:
            profiles = self._run_pactl("list", "cards", "profiles", card_id)
            current_profile = None
            for line in profiles.splitlines():
                if "*:" in line:
                    current_profile = line.split(":")[0].strip().lstrip("*")
                    break
        except subprocess.CalledProcessError:
            return
        
        self._saved_profile = current_profile
        
        # Switch to HFP if needed
        if current_profile and "a2dp" in current_profile.lower():
            try:
                # Check if HFP is available
                if "hfp" in profiles.lower() or "handsfree" in profiles.lower():
                    self._run_pactl("set-card-profile", card_id, "hfp_handsfree")
                    time.sleep(0.5)
            except subprocess.CalledProcessError:
                pass

    def restore_microphone(self) -> None:
        """
        Restore audio state after recording.
        
        For Bluetooth headsets, this switches back to the original profile.
        """
        import time
        
        if self._saved_profile is None:
            return
        
        # Restore profile
        try:
            # Need to find the card again
            output = self._run_pactl("list", "cards", "short")
            card_id = None
            for line in output.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    cid, cname = parts[0], parts[1]
                    if "bluez" in cname.lower():
                        card_id = cid
                        break
            
            if card_id:
                self._run_pactl("set-card-profile", card_id, self._saved_profile)
        except (subprocess.CalledProcessError, AttributeError):
            pass
        
        self._saved_profile = None

    def start_recording(
        self,
        microphone: Microphone,
        output_path: Path,
    ) -> None:
        if self.process is not None:
            raise RuntimeError("Recording is already active.")

        source_name = microphone.backend_data.get("source_name")

        if not source_name:
            raise RuntimeError(
                f"Microphone '{microphone.display_name()}' "
                "does not have a PulseAudio source name."
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        raw_output_path = output_path.with_suffix(".pcm")

        command = [
            "parec",
            "--device", source_name,
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16le",
            str(raw_output_path),
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "parec was not found. "
                "PulseAudio recording tools are required."
            ) from error

        self._raw_output_path = raw_output_path
        self._output_path = output_path

    def stop_recording(self) -> None:
        if self.process is None:
            return

        process = self.process
        self.process = None

        try:
            process.terminate()

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

        finally:
            if process.stdin is not None:
                process.stdin.close()

            if process.stderr is not None:
                process.stderr.close()

        raw_output_path = self._raw_output_path
        output_path = self._output_path

        self._raw_output_path = None
        self._output_path = None

        if raw_output_path is None or output_path is None:
            raise RuntimeError(
                "PulseAudio recording paths were not initialized."
            )

        if not raw_output_path.exists():
            raise RuntimeError(
                f"PulseAudio recording produced no audio data: "
                f"{raw_output_path}"
            )

        if raw_output_path.stat().st_size == 0:
            raw_output_path.unlink()
            raise RuntimeError(
                "PulseAudio recording produced an empty audio file."
            )

        try:
            with raw_output_path.open("rb") as raw_file:
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_file.writeframes(raw_file.read())
        finally:
            if raw_output_path.exists():
                raw_output_path.unlink()