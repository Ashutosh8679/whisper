import shutil
import subprocess
import time
from pathlib import Path

from src.audio.backend import AudioBackend
from src.audio.microphone import Microphone

class PipeWireBackend(AudioBackend):
    """
    Linux audio backend using PipeWire/WirePlumber.

    The backend currently uses wpctl for audio-device discovery and
    default-source detection.
    """

    name = "pipewire"

    def __init__(self):
        self.process = None
        self._saved_profile = None
        self._saved_source = None

    def is_available(self) -> bool:
        """
        Check whether the PipeWire control interface is available
        and responding.
        """
        if not shutil.which("wpctl"):
            return False

        try:
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

        return bool(result.stdout.strip())

    def _run_wpctl(self, *arguments) -> str:
        """
        Execute wpctl and return its stdout.
        """
        try:
            result = subprocess.run(
                ["wpctl", *arguments],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "wpctl was not found. "
                "PipeWire/WirePlumber tools are required."
            ) from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"wpctl command failed: "
                f"{' '.join(arguments)}\n"
                f"{error.stderr.strip()}"
            ) from error

        return result.stdout

    def _get_status(self) -> str:
        return self._run_wpctl("status")

    def list_microphones(self) -> list[Microphone]:
        """
        Return physical microphones from the PipeWire Audio -> Sources
        section.

        Playback monitors and video sources are intentionally excluded.
        """
        output = self._get_status()

        microphones = []
        in_audio = False
        in_sources = False

        for line in output.splitlines():
            stripped = line.strip()

            if stripped == "Audio":
                in_audio = True
                continue

            if not in_audio:
                continue

            if stripped in {"Video", "Settings"}:
                break

            if stripped in {"├─ Sources:", "└─ Sources:"}:
                in_sources = True
                continue

            if in_sources and (
                stripped.startswith("├─")
                or stripped.startswith("└─")
            ):
                break

            if not in_sources:
                continue

            if not stripped:
                continue

            entry = stripped.lstrip("│ ").strip()

            if entry.startswith("*"):
                entry = entry[1:].strip()

            if "." not in entry:
                continue

            node_id_text, description = entry.split(".", 1)

            node_id_text = node_id_text.strip()
            description = description.strip()

            if not node_id_text.isdigit() or not description:
                continue

            if "monitor" in description.lower():
                continue

            microphones.append(
                Microphone(
                    id=node_id_text,
                    name=description,
                    description=description,
                    is_bluetooth=(
                        "bluez" in description.lower()
                        or "bluetooth" in description.lower()
                    ),
                    backend_data={
                        "node_id": int(node_id_text),
                    },
                )
            )

        # Also check for suspended Bluetooth sources via pactl
        # (they may not appear in wpctl status but are available for recording)
        try:
            pactl_sources = self._run_pactl("list", "sources", "short")
            for line in pactl_sources.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    node_id_str = parts[0].strip()
                    source_name = parts[1].strip()
                    
                    if not source_name.endswith(".monitor") and source_name.startswith("bluez_source"):
                        # Check if not already added
                        if not any(m.id == node_id_str for m in microphones):
                            microphones.append(
                                Microphone(
                                    id=node_id_str,
                                    name=source_name,
                                    description=source_name,
                                    is_bluetooth=True,
                                    backend_data={
                                        "node_id": int(node_id_str),
                                    },
                                )
                            )
        except Exception:
            pass

        return microphones

    def get_default_microphone(self) -> Microphone | None:
        """
        Return the source marked with '*' in the Audio -> Sources section.
        """
        output = self._get_status()

        in_audio = False
        in_sources = False
        default_id = None

        for line in output.splitlines():
            stripped = line.strip()

            if stripped == "Audio":
                in_audio = True
                continue

            if not in_audio:
                continue

            if stripped in {"Video", "Settings"}:
                break

            if stripped in {"├─ Sources:", "└─ Sources:"}:
                in_sources = True
                continue

            if in_sources and (
                stripped.startswith("├─")
                or stripped.startswith("└─")
            ):
                break

            if not in_sources:
                continue

            if "*" not in stripped:
                continue

            entry = stripped.lstrip("│ ").strip()
            entry = entry.replace("*", "", 1).strip()

            if "." not in entry:
                continue

            node_id_text = entry.split(".", 1)[0].strip()

            if node_id_text.isdigit():
                default_id = node_id_text
                break

        if default_id is None:
            return None

        for microphone in self.list_microphones():
            if microphone.id == default_id:
                return microphone

        return None

    def prepare_microphone(self, microphone: Microphone) -> None:
        """
        Prepare a microphone for recording.

        For Bluetooth headsets in A2DP mode, this temporarily switches
        to HFP/HSP profile so the microphone becomes available.
        """
        import json
        import time
        from src.audio.linux.bluetooth import BluetoothDeviceDatabase
        
        if not microphone.is_bluetooth:
            return
        
        # Get card info from description
        description = microphone.description or ""
        if "bluez" not in description.lower() and "bluetooth" not in description.lower():
            return
        
        # Try pulseaudio card ID first
        try:
            output = self._run_pactl("list", "cards", "short")
        except RuntimeError:
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
            # Use pactl list cards to get profiles
            profiles_output = self._run_pactl("list", "cards")
            current_profile = None
            in_card = False
            for line in profiles_output.splitlines():
                if f"Name: {microphone.name}" in line or f"Card #{card_id}" in line:
                    in_card = True
                elif in_card and "Active Profile:" in line:
                    current_profile = line.split(":", 1)[1].strip()
                    break
                elif in_card and line.startswith("Card #"):
                    break
        except Exception:
            current_profile = None

        self._saved_profile = current_profile

        # Switch to HFP if needed
        if current_profile and "a2dp" in current_profile.lower():
            try:
                # Check if HFP is available
                if "hfp_handsfree" in profiles_output or "handsfree" in profiles_output:
                    self._run_pactl("set-card-profile", card_id, "hfp_handsfree")
                    time.sleep(0.5)
            except Exception:
                pass

    def discover_bluetooth_devices(self) -> list[dict]:
        """
        Probe Bluetooth devices to detect which have microphone capability.
        
        This probes by temporarily switching to HFP profile, checking for
        an input source, then restoring the original profile. Results are
        cached in a JSON database.
        """
        import time
        from src.audio.linux.bluetooth import BluetoothDeviceDatabase
        
        db = BluetoothDeviceDatabase()
        
        try:
            output = self._run_pactl("list", "cards", "short")
        except RuntimeError:
            return []
        
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            
            card_id = parts[0]
            card_name = parts[1]
            
            if "bluez" not in card_name.lower() and "bluetooth" not in card_name.lower():
                continue
            
            # Get current profile and available profiles
            try:
                profiles_output = self._run_pactl("list", "cards")
            except RuntimeError:
                continue
            
            # Parse profiles
            current_profile = None
            available_profiles = []
            in_profiles_section = False
            
            for profile_line in profiles_output.splitlines():
                # Find the profiles section after card name
                if card_name in profile_line and "Name:" in profile_line:
                    in_profiles_section = True
                    continue
                elif in_profiles_section:
                    # Active profile is on its own line
                    if profile_line.strip().startswith("Active Profile:"):
                        current_profile = profile_line.split(":", 1)[1].strip()
                        continue
                    # Profile lines have format: "profile_name: description"
                    if ":" in profile_line and not profile_line.strip().startswith("Ports:") and not profile_line.strip().startswith("Active"):
                        profile_name = profile_line.split(":")[0].strip()
                        available_profiles.append(profile_name)
                    elif profile_line.strip() == "" or profile_line.strip().startswith("Ports:"):
                        break
            
            # Get MAC address
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
            if "handsfree_head_unit" in available_profiles or "hfp_handsfree" in available_profiles:
                try:
                    # Only probe if currently in A2DP
                    if current_profile and "a2dp" in current_profile.lower():
                        self._run_pactl("set-card-profile", card_id, "hfp_handsfree")
                        time.sleep(0.5)
                    
                    # Check if input source appears (HFP might already be active)
                    sources = self._run_pactl("list", "sources", "short")
                    # Sources are named like: bluez_source.24_DF_17_10_13_17.handsfree_head_unit
                    # Check if our MAC (with underscores) appears in the source name
                    mac_with_underscores = mac.replace(":", "_")
                    has_input = any(
                        mac_with_underscores.lower() in src.lower()
                        for src in sources.splitlines()
                    )
                    
                    # Cache result
                    db.upsert(card_name, mac, has_input)
                    
                    # Restore profile if we changed it
                    if current_profile and "a2dp" in current_profile.lower():
                        self._run_pactl("set-card-profile", card_id, current_profile)
                    
                except Exception:
                    try:
                        if current_profile and "a2dp" in current_profile.lower():
                            self._run_pactl("set-card-profile", card_id, current_profile)
                    except Exception:
                        pass

    def restore_microphone(self) -> None:
        """
        Restore audio state after recording.

        For Bluetooth headsets, this switches back to the original profile.
        """
        import time
        
        if self._saved_profile is None:
            return
        
        try:
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
    
    def _run_pactl(self, *args: str) -> str:
        """Run pactl command and return stdout."""
        result = subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def start_recording(
        self,
        microphone: Microphone,
        output_path: Path,
    ) -> None:
        """
        Start recording from the specified PipeWire microphone.

        The resulting file is a WAV recording at 16 kHz mono.
        """
        if self.process is not None:
            raise RuntimeError("A recording is already in progress.")

        node_id = microphone.backend_data.get("node_id")

        if node_id is None:
            raise RuntimeError(
                f"Microphone '{microphone.display_name()}' "
                "does not have a PipeWire node ID."
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            "pw-record",
            "--target",
            str(node_id),
            "--rate",
            "16000",
            "--channels",
            "1",
            "--format",
            "s16",
            str(output_path),
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "pw-record was not found. "
                "PipeWire recording tools are required."
            ) from error

        deadline = time.monotonic() + 2.0

        while time.monotonic() < deadline:
            if output_path.exists() and output_path.stat().st_size > 0:
                return

            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode(
                    errors="replace"
                ).strip()

                self.process = None

                raise RuntimeError(
                    "pw-record exited before recording started."
                    f"{f' Error: {stderr}' if stderr else ''}"
                )

            time.sleep(0.01)

        raise RuntimeError(
            "pw-record started, but did not create the output file "
            f"within 2 seconds: {output_path}"
        )

    def stop_recording(self) -> None:
        """
        Stop the active PipeWire recording process.
        """
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