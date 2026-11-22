from dataclasses import dataclass, field


@dataclass
class Microphone:
    """
    Backend-neutral representation of a physical microphone.

    The backend-specific information is kept inside backend_data so that
    the rest of Wispr does not need to know whether the microphone is
    managed through PipeWire, PulseAudio, or another audio system.
    """

    id: str
    name: str
    description: str = ""
    is_bluetooth: bool = False
    backend_data: dict = field(default_factory=dict)

    def display_name(self) -> str:
        """
        Return the most useful human-readable name for the microphone.
        """
        return self.description or self.name