import subprocess
from dataclasses import dataclass


@dataclass
class AudioSource:
    """
    Represents an audio input source exposed by PipeWire.
    """

    index: int
    name: str
    description: str
    state: str
    is_monitor: bool

    def display_name(self) -> str:
        """
        Return a human-friendly name for the source.
        """

        if self.description:
            return self.description

        return self.name


def _run_pactl(*arguments):
    """
    Run pactl and return its stdout.
    """

    try:
        result = subprocess.run(
            ["pactl", *arguments],
            capture_output=True,
            text=True,
            check=True,
        )

    except FileNotFoundError as error:
        raise RuntimeError(
            "pactl was not found. "
            "Please install the PipeWire/PulseAudio utilities."
        ) from error

    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"pactl command failed: "
            f"{' '.join(arguments)}\n"
            f"{error.stderr.strip()}"
        ) from error

    return result.stdout


def _parse_short_sources():
    """
    Parse the compact source list returned by:
        pactl list short sources
    """

    output = _run_pactl(
        "list",
        "short",
        "sources",
    )

    sources = []

    for line in output.splitlines():

        if not line.strip():
            continue

        parts = line.split("\t")

        if len(parts) < 2:
            continue

        try:
            index = int(parts[0])

        except ValueError:
            continue

        name = parts[1]

        state = parts[-1] if len(parts) >= 5 else ""

        sources.append(
            AudioSource(
                index=index,
                name=name,
                description=name,
                state=state,
                is_monitor=name.endswith(".monitor"),
            )
        )

    return sources


def list_audio_sources(include_monitors=False):
    """
    Return available audio input sources.

    By default, monitor sources are excluded because they represent
    playback/monitor streams rather than physical microphone inputs.
    """

    sources = _parse_short_sources()

    if include_monitors:
        return sources

    return [
        source
        for source in sources
        if not source.is_monitor
    ]