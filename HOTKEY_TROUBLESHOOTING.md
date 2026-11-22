# Hotkey Troubleshooting Guide

## Current Status

The Wispr hotkey system has been experiencing issues with global shortcut detection on your KDE Plasma 6 Wayland setup.

## What Works

1. **Bluetooth Detection**: Your Airdopes 141 Elite ANC headset is now correctly detected as having microphone capability
2. **Audio Configuration**: You can select the Bluetooth headset as your audio source
3. **Daemon**: Runs properly with GPU acceleration
4. **Hotkey Registration**: KGlobalAccel registers the shortcut successfully

## Known Issue: Hotkey Not Triggering

The Super+Space hotkey is registered but not triggering recordings. This appears to be a KDE Plasma 6 / Wayland-specific issue where D-Bus signals from KGlobalAccel are not being delivered to the application.

### Root Cause Analysis

1. **KGlobalAccel D-Bus Signals**: While we successfully register the shortcut, the `globalShortcutPressed` and `globalShortcutReleased` signals are not reaching our application
2. **pynput Incompatibility**: pynput uses X11 hooks which don't work on Wayland
3. **evdev Access Issues**: Direct keyboard reading via `/dev/input` events is not working reliably in this environment

### Tested Approaches

| Approach | Result | Notes |
|----------|--------|-------|
| KGlobalAccel D-Bus | ❌ No signals received | Shortcut registers but no press events |
| pynput (X11) | ❌ Doesn't work on Wayland | Uses XInput extension |
| evdev polling | ⚠️ Unreliable | May need different device or permissions |
| ydotool | ✅ Works for output | Can simulate keypresses |

## Workarounds

### Option 1: Manual Dictation Test
You can test the transcription pipeline without the hotkey:

```bash
# Start daemon
wispr daemon

# Test single dictation
wispr-hotkey test
```

### Option 2: Alternative Keyboard Libraries
Consider installing a Wayland-compatible keyboard monitoring library:

```bash
pip install python-evdev
# Or use wayland-specific tools if available
```

### Option 3: Check KDE Settings
Try manually configuring the shortcut in KDE System Settings:
1. Go to **Settings → Shortcuts**
2. Search for "Wispr"
3. Verify the shortcut is assigned and not conflicting

### Option 4: Try Different Key Combination
Modify the shortcut to avoid potential conflicts:
- Edit `src/kde_wayland_hotkey.py` line 21:
  ```python
  SUPER_SPACE = 0x10000020  # Change this
  ```
- Try `Ctrl+Alt+S` (0x02 + 0x10 + 0x33 = 0x45) or another combo

## Next Steps

To resolve the hotkey issue permanently, consider:
1. Investigating KDE Plasma 6's Wayland input handling changes
2. Using a proper Wayland input injection library
3. Checking if there's a conflict with KDE's app launcher (Super+Space)
4. Testing with a different desktop environment to isolate the issue

## Files to Check

- `src/hotkey.py` - Main hotkey logic
- `src/kde_wayland_hotkey.py` - KDE D-Bus integration
- `src/evdev_hotkey.py` - Fallback evdev implementation
- `~/.config/kglobalshortcutsrc` - KDE shortcut configuration
