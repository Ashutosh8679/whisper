import json
import os
from pathlib import Path


APP_NAME = "wispr"


def get_config_dir() -> Path:
    """
    Return the user's XDG configuration directory.

    Falls back to ~/.config when XDG_CONFIG_HOME is not set.
    """

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        return Path(xdg_config_home) / APP_NAME

    return Path.home() / ".config" / APP_NAME


CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"


DEFAULT_CONFIG = {
    "audio": {
        "mode": "default",
        "source": None,
    }
}


class ConfigManager:
    """
    Handles loading and saving Wispr's user configuration.
    """

    def __init__(self):
        self.config_dir = CONFIG_DIR
        self.config_file = CONFIG_FILE

    def ensure_config_directory(self):
        """
        Create the configuration directory if necessary.
        """

        self.config_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def create_default_config(self):
        """
        Create the default configuration if it does not exist.
        """

        if self.config_file.exists():
            return

        self.ensure_config_directory()

        self.save(DEFAULT_CONFIG)

    def load(self):
        """
        Load the user's configuration.

        If no configuration exists, create the default configuration.
        """

        self.create_default_config()

        try:
            with self.config_file.open(
                "r",
                encoding="utf-8",
            ) as file:
                config = json.load(file)

        except (json.JSONDecodeError, OSError) as error:
            raise RuntimeError(
                f"Could not read configuration file "
                f"{self.config_file}: {error}"
            ) from error

        return config

    def save(self, config):
        """
        Save configuration as formatted JSON.
        """

        self.ensure_config_directory()

        temporary_file = self.config_file.with_suffix(
            ".json.tmp"
        )

        try:
            with temporary_file.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    config,
                    file,
                    indent=4,
                )

                file.write("\n")

            temporary_file.replace(self.config_file)

        except OSError as error:
            raise RuntimeError(
                f"Could not save configuration file "
                f"{self.config_file}: {error}"
            ) from error

    def get_audio_config(self):
        """
        Return the configured audio settings.
        """

        config = self.load()

        return config.get(
            "audio",
            DEFAULT_CONFIG["audio"].copy(),
        )

    def set_audio_config(
        self,
        mode,
        source=None,
    ):
        """
        Update the configured audio source.
        """

        config = self.load()

        config["audio"] = {
            "mode": mode,
            "source": source,
        }

        self.save(config)