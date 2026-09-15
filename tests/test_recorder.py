from src.recorder import Recorder


recorder = Recorder()

print("Starting...")
path = recorder.start()

print("Recording for 5 seconds...")
print("Speak now!")

import time
time.sleep(5)

path = recorder.stop()

print(f"Final WAV: {path}")