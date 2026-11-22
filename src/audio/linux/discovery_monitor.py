"""Background Bluetooth discovery for the Linux hotkey service."""

import threading
import time
from typing import Callable

from src.audio.factory import get_audio_backend


class BluetoothDiscoveryMonitor:
    """Periodically discover newly connected Bluetooth input devices.

    The monitor serializes discovery with recording start/stop. It never runs
    a probe while dictation is active, and normal microphone enumeration is
    intentionally passive. Probe failures are logged and retried on a later
    poll because inconclusive results are not cached.
    """

    def __init__(
        self,
        backend=None,
        interval: float = 3.0,
        logger: Callable[[str], None] | None = None,
    ):
        self.backend = backend or get_audio_backend()
        self.interval = max(0.5, float(interval))
        self.logger = logger or (lambda message: None)
        self._lock = threading.RLock()
        self._recording = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="wispr-bluetooth-discovery",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(2.0, self.interval + 1.0))

    def begin_recording(self) -> None:
        # Wait for any in-progress probe to finish before recording starts.
        with self._lock:
            self._recording = True

    def end_recording(self) -> None:
        with self._lock:
            self._recording = False

    def _run_once(self) -> None:
        with self._lock:
            if self._recording:
                return
            try:
                # The backend consults its MAC-keyed cache and probes only
                # unknown cards. Avoid logging the same cached devices every poll.
                self.backend.discover_bluetooth_devices()
            except Exception as error:
                self.logger(
                    "Bluetooth discovery deferred after an inconclusive check: "
                    f"{type(error).__name__}: {error}"
                )

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self._run_once()
