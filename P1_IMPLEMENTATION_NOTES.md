# Proposed P1 implementation

This is a review build, not a replacement for the known-good baseline.

## Changes

- Added `src/audio/linux/discovery_monitor.py`: a hotkey-service background monitor polls the selected Linux backend for connected Bluetooth cards. It serializes discovery with recording start/stop and does not probe while recording is active.
- Added an explicit `discover_bluetooth_devices()` backend API. Normal microphone listing and default-microphone lookup no longer initiate capability probes. `wispr configure` invokes explicit discovery before listing devices.
- Bluetooth cache identity is the MAC address; the device name is mutable display metadata. Same-name devices with different MAC addresses remain separate. Renaming a device updates its saved name without forcing a reprobe.
- Bluetooth probe outcomes are cached only when definitive. A missing HFP/HSP profile is a definitive negative result. Operational failures, source timeouts, and restoration failures raise an inconclusive-probe error and are not cached.
- PipeWire probe restoration attempts profile and default-source restoration independently and waits for the original profile/source to return. PulseAudio retains independent restoration attempts and reports failures.
- PipeWire now rejects a second active recording and clears process/output state on stop. PulseAudio stop tolerates a recorder process that exited before stop was requested.
- Recorder filenames include microseconds to avoid same-second collisions. Startup failures report additional restoration errors rather than silently discarding them.
- Existing hardware/model-dependent tests are now explicitly opt-in so test collection does not start a microphone recording or load Wispr. Added isolated regression tests in `tests/test_p1_regressions.py`.
- Removed the stray empty file `=1.2,`.

## Validation performed in the review environment

- `python -m compileall -q src config tests`: passed.
- `bash -n install.sh scripts/wispr scripts/wispr-hotkey`: passed.
- `python -m unittest discover -s tests -v`: 10 unit tests passed; 2 hardware integration tests skipped by design.
- `python -m src.cli --help`: could not run in this environment because `faster_whisper` is not installed here. The project venv on the target machine should be used for this check.

## Required target-machine validation

1. Use the project's `.venv/bin/python` for imports and tests.
2. Test PipeWire and native PulseAudio separately.
3. Connect an unknown Bluetooth headset and verify exactly one probe, HFP/source check, and restoration to the original profile/source.
4. Reconnect the same headset and verify the JSON cache prevents another probe.
5. Test a Bluetooth device without a microphone and verify a negative result is cached when absence is definitive.
6. Verify no discovery/profile switching occurs during active dictation.
7. Verify restoration failure is visible in logs and both restoration operations are attempted.
8. Run the hotkey-to-recording-to-transcription-to-paste workflow.

No hardware-dependent claims are made by this review build. Keep the baseline archive unchanged until these tests pass.
