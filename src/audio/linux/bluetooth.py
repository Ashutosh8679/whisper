import json
from datetime import datetime, timezone
from pathlib import Path


BLUETOOTH_DATABASE_FILE = (
    Path.home()
    / ".config"
    / "wispr"
    / "bluetooth_devices.json"
)


class BluetoothDeviceDatabase:
    """
    Persistent database for discovered Bluetooth audio devices.

    This class only manages cached Bluetooth capability information.
    Audio backend implementations are responsible for discovering
    and probing devices.

    A device is cached after a definitive capability result, including a
    confirmed negative result. MAC address is the stable identity; the
    name is display metadata and may change. Inconclusive probes must not
    be inserted into this database. Cached devices are not re-probed merely
    because time has passed.
    """

    def __init__(
        self,
        database_file: Path | None = None,
    ):
        self.database_file = (
            Path(database_file)
            if database_file is not None
            else BLUETOOTH_DATABASE_FILE
        )

    def _ensure_directory(self) -> None:
        """Create the database directory if necessary."""

        self.database_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _load(self) -> list[dict]:
        """Load all cached Bluetooth device records."""

        if not self.database_file.exists():
            return []

        try:
            with self.database_file.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

        except (json.JSONDecodeError, OSError) as error:
            raise RuntimeError(
                f"Could not read Bluetooth device database "
                f"{self.database_file}: {error}"
            ) from error

        if not isinstance(data, list):
            raise RuntimeError(
                f"Bluetooth device database must contain "
                f"a JSON list: {self.database_file}"
            )

        return data

    def _save(self, devices: list[dict]) -> None:
        """Save Bluetooth device records atomically."""

        self._ensure_directory()

        temporary_file = self.database_file.with_suffix(
            ".json.tmp"
        )

        try:
            with temporary_file.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    devices,
                    file,
                    indent=4,
                )

                file.write("\n")

            temporary_file.replace(self.database_file)

        except OSError as error:
            raise RuntimeError(
                f"Could not save Bluetooth device database "
                f"{self.database_file}: {error}"
            ) from error

    @staticmethod
    def _device_matches(
        device: dict,
        name: str,
        mac: str,
    ) -> bool:
        """Return True when a cached record represents the device."""

        # MAC identifies the physical device. Name is mutable metadata: a
        # renamed device must not be probed again, while two devices sharing
        # a name remain distinct because their MAC addresses differ.
        return device.get("mac", "").casefold() == mac.casefold()

    def get(
        self,
        name: str,
        mac: str,
    ) -> dict | None:
        """Return the cached record, or None if it is unknown."""

        devices = self._load()

        for device in devices:
            if self._device_matches(
                device,
                name,
                mac,
            ):
                return device

        return None

    def upsert(
        self,
        name: str,
        mac: str,
        input_capable: bool,
    ) -> dict:
        """
        Insert or update a Bluetooth device capability record.

        The record is identified by both name and MAC address. Both
        positive and negative probe results are persisted so a known
        device is not probed again on every connection.
        """

        devices = self._load()

        record = {
            "name": name,
            "mac": mac,
            "input_capable": bool(input_capable),
            "last_checked": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        for index, device in enumerate(devices):
            if self._device_matches(device, name, mac):
                devices[index] = record
                self._save(devices)
                return record

        devices.append(record)
        self._save(devices)

        return record

    def all(self) -> list[dict]:
        """Return all cached Bluetooth device records."""

        return self._load()
