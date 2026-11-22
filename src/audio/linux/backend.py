import shutil

from src.audio.backend import AudioBackend


class LinuxAudioBackend(AudioBackend):
    """
    Selects and exposes the best available audio backend on Linux.

    PipeWire is preferred when its command-line interface is available.
    PulseAudio compatibility tools are used as a fallback.
    """

    def __init__(self):
        self._backend = self._detect_backend()

    @staticmethod
    def _detect_backend() -> AudioBackend:
        """
        Detect the first usable Linux audio backend.

        PipeWire is preferred over the PulseAudio compatibility layer.
        """
        if shutil.which("wpctl"):
            from src.audio.linux.pipewire import PipeWireBackend

            backend = PipeWireBackend()

            if backend.is_available():
                return backend

        if shutil.which("pactl") and shutil.which("parec"):
            from src.audio.linux.pulseaudio import PulseAudioBackend

            backend = PulseAudioBackend()

            if backend.is_available():
                return backend

        raise RuntimeError(
            "No supported Linux audio backend was found.\n"
            "Wispr requires either:\n"
            "  - PipeWire/WirePlumber (wpctl), or\n"
            "  - PulseAudio compatibility tools (pactl + parec)."
        )

    @property
    def name(self) -> str:
        """Return the name of the active backend."""
        return self._backend.name

    def list_microphones(self):
        return self._backend.list_microphones()

    def get_default_microphone(self):
        return self._backend.get_default_microphone()

    def prepare_microphone(self, microphone):
        return self._backend.prepare_microphone(microphone)

    def restore_microphone(self):
        return self._backend.restore_microphone()

    def start_recording(self, microphone, output_path):
        return self._backend.start_recording(microphone, output_path)

    def stop_recording(self):
        return self._backend.stop_recording()

    def discover_bluetooth_devices(self):
        if hasattr(self._backend, 'discover_bluetooth_devices'):
            return self._backend.discover_bluetooth_devices()