"""Evdev-based hotkey handler for Wayland/X11 hybrid environments."""

import os
import struct
import threading
import time
from pathlib import Path

# Key codes (from linux/input-event-codes.h)
KEY_SUPER_L = 125
KEY_SUPER_R = 126
KEY_SPACE = 57
KEY_LEFTALT = 56
KEY_LEFTCTRL = 29

# Event types
EV_KEY = 1


class EvdevHotkey:
    """
    Global Super+Space hold detector using /dev/input directly.
    
    Bypasses KGlobalAccel D-Bus which has issues on some Wayland setups.
    """

    def __init__(self):
        self._activation_event = threading.Event()
        self._release_event = threading.Event()
        self._ready_event = threading.Event()
        self._keyboard_fd = None
        self._thread = None
        self._running = False

    def _find_keyboard(self) -> str | None:
        """Find the main keyboard event device."""
        try:
            with open('/proc/bus/input/devices', 'r') as f:
                content = f.read()
            
            current_name = None
            current_handler = None
            handlers = []
            
            for line in content.split('\n'):
                if line.startswith('N: Name='):
                    current_name = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('H: Handlers='):
                    handlers = line.split('=', 1)[1].strip().split()
                    # Look for keyboard handler
                    for h in handlers:
                        if h.startswith('event') and 'kbd' in handlers:
                            return f'/dev/input/{h}'
                            
        except Exception as e:
            print(f"Error finding keyboard: {e}")
        
        return None

    def _read_loop(self):
        """Main loop that reads keyboard events."""
        keyboard_path = self._find_keyboard()
        if not keyboard_path:
            self._ready_event.set()
            return
        
        try:
            self._keyboard_fd = os.open(keyboard_path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            print("Permission denied reading keyboard. Try: sudo usermod -aG input $USER")
            self._ready_event.set()
            return
        except FileNotFoundError:
            print(f"Keyboard device not found: {keyboard_path}")
            self._ready_event.set()
            return
        
        self._ready_event.set()
        self._super_pressed = False
        self._space_pressed = False
        
        buffer_size = 4096
        key_states = {}  # Track which keys are currently pressed
        
        while self._running:
            try:
                data = os.read(self._keyboard_fd, buffer_size)
                
                # Parse input_event structures
                # struct input_event { struct timeval time; __u16 type; __u16 code; __s32 value; };
                offset = 0
                while offset + 24 <= len(data):
                    event_type = struct.unpack_from('H', data, offset + 16)[0]
                    event_code = struct.unpack_from('H', data, offset + 18)[0]
                    event_value = struct.unpack_from('i', data, offset + 20)[0]
                    
                    if event_type == EV_KEY:
                        # Track key state
                        if event_value == 1:  # Press
                            key_states[event_code] = True
                        elif event_value == 0:  # Release
                            key_states[event_code] = False
                        
                        # Check for Super+Space
                        super_down = key_states.get(KEY_SUPER_L, False) or key_states.get(KEY_SUPER_R, False)
                        space_down = key_states.get(KEY_SPACE, False)
                        
                        if super_down and space_down and not self._activation_event.is_set():
                            self._on_pressed()
                        elif not (super_down and space_down) and self._activation_event.is_set():
                            self._on_released()
                    
                    offset += 24
                    
            except BlockingIOError:
                time.sleep(0.01)
            except Exception as e:
                if self._running:
                    print(f"Error reading keyboard: {e}")
                    time.sleep(0.1)

    def _on_pressed(self):
        if self._active:
            return
        self._active = True
        self._release_event.clear()
        self._activation_event.set()

    def _on_released(self):
        if not self._active:
            return
        self._active = False
        self._release_event.set()

    def start(self):
        """Start the evdev hotkey backend."""
        if self._thread is not None:
            return
        
        self._active = False
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop,
            name="evdev-hotkey",
            daemon=True,
        )
        self._thread.start()
        
        if not self._ready_event.wait(timeout=5):
            raise RuntimeError("Timed out waiting for keyboard detection.")
        
        print("[OK] Evdev hotkey listener started.", flush=True)

    def wait_for_activation(self):
        """Block until Super+Space is pressed."""
        self._activation_event.wait()
        self._activation_event.clear()

    def wait_for_release(self):
        """Block until Super+Space is released."""
        self._release_event.wait()
        self._release_event.clear()

    def close(self):
        """Stop the hotkey backend."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._keyboard_fd is not None:
            try:
                os.close(self._keyboard_fd)
            except Exception:
                pass
