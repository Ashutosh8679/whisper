from threading import Event, Lock
from pynput import keyboard


SUPER_KEYS = {
    keyboard.Key.cmd,
    keyboard.Key.cmd_l,
    keyboard.Key.cmd_r,
}

SPACE_KEY = keyboard.Key.space


class X11Hotkey:
    """Global Super+Space hold detector for X11."""

    def __init__(self):
        self.super_down = False
        self.space_down = False
        self.activated = False

        self._activation_event = Event()
        self._release_event = Event()
        self._state_lock = Lock()

        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )

    def _on_press(self, key):
        with self._state_lock:
            if key in SUPER_KEYS:
                self.super_down = True

            elif key == SPACE_KEY:
                self.space_down = True

            if (
                self.super_down
                and self.space_down
                and not self.activated
            ):
                self.activated = True
                self._release_event.clear()
                self._activation_event.set()

    def _on_release(self, key):
        with self._state_lock:
            if key in SUPER_KEYS:
                self.super_down = False

            elif key == SPACE_KEY:
                self.space_down = False

            if (
                self.activated
                and not self.super_down
                and not self.space_down
            ):
                self.activated = False
                self._release_event.set()

    def wait_for_activation(self):
        """Block until Super+Space is pressed together."""
        self._activation_event.wait()
        self._activation_event.clear()

    def wait_for_release(self):
        """Block until either Super or Space is released."""
        self._release_event.wait()
        self._release_event.clear()

    def start(self):
        """Start global keyboard monitoring."""
        self.listener.start()

    def close(self):
        """Stop global keyboard monitoring."""
        self.listener.stop()