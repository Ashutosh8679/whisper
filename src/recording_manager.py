from datetime import datetime, timedelta
from pathlib import Path

from config.config import RECORDINGS_DIR, RETENTION_DAYS


class RecordingManager:
    """
    Handles temporary recording storage, permanent archiving,
    and automatic cleanup.
    """

    def __init__(self):
        self.recordings_dir = RECORDINGS_DIR
        self.archive_dir = self.recordings_dir / "archive"
        self.retention_days = RETENTION_DAYS

        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def create_recording_path(self) -> Path:
        """
        Create a timestamped path for a new temporary recording.
        """

        now = datetime.now()

        date_directory = self.recordings_dir / now.strftime("%Y-%m-%d")
        date_directory.mkdir(parents=True, exist_ok=True)

        filename = now.strftime("%Y-%m-%d_%H-%M-%S.wav")

        return date_directory / filename

    def archive_recording(self, recording_path: Path) -> Path:
        """
        Move a recording into the permanent archive.

        Archived recordings are never touched by cleanup.
        """

        recording_path = Path(recording_path).expanduser().resolve()

        if not recording_path.exists():
            raise FileNotFoundError(
                f"Recording does not exist: {recording_path}"
            )

        if not recording_path.is_file():
            raise ValueError(
                f"Path is not a file: {recording_path}"
            )

        # Check whether the recording is already archived.
        try:
            recording_path.relative_to(self.archive_dir.resolve())
            already_archived = True
        except ValueError:
            already_archived = False

        if already_archived:
            raise ValueError(
                f"Recording is already archived: {recording_path}"
            )

        # Preserve the original filename.
        destination = self.archive_dir / recording_path.name

        # Avoid overwriting an existing archived recording.
        if destination.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            destination = (
                self.archive_dir
                / f"{recording_path.stem}_{timestamp}"
                f"{recording_path.suffix}"
            )

        recording_path.rename(destination)

        return destination

    def cleanup_old_recordings(self):
        """
        Delete temporary recordings older than RETENTION_DAYS.

        The archive directory is explicitly excluded.
        """

        cutoff = datetime.now() - timedelta(days=self.retention_days)

        deleted_count = 0

        if not self.recordings_dir.exists():
            return

        for path in self.recordings_dir.iterdir():

            if not path.is_dir():
                continue

            # Never inspect the archive.
            if path.resolve() == self.archive_dir.resolve():
                continue

            for recording in path.rglob("*"):

                if not recording.is_file():
                    continue

                try:
                    modified_time = datetime.fromtimestamp(
                        recording.stat().st_mtime
                    )

                    if modified_time < cutoff:
                        recording.unlink()

                        print(
                            f"Deleted old recording: {recording}"
                        )

                        deleted_count += 1

                except OSError as error:
                    print(
                        f"Could not process {recording}: {error}"
                    )

            # Remove empty date directory.
            try:
                path.rmdir()
            except OSError:
                pass

        print(
            f"Cleanup complete. "
            f"Deleted {deleted_count} recording(s)."
        )