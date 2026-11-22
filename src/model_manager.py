import json
from pathlib import Path


SUPPORTED_MODELS = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v1",
    "large-v2",
    "large-v3",
)

DEFAULT_MODEL = "small"


def get_config_dir() -> Path:
    """Return the Wispr user configuration directory."""

    xdg_config_home = Path(
        __import__("os").environ.get(
            "XDG_CONFIG_HOME",
            Path.home() / ".config",
        )
    )

    return xdg_config_home / "wispr"


def get_config_file() -> Path:
    """Return the Wispr configuration file path."""

    return get_config_dir() / "config.json"


def is_supported_model(model: str) -> bool:
    """Return whether the model name is supported."""

    return model in SUPPORTED_MODELS


def get_current_model() -> str:
    """
    Return the currently selected Wispr model.

    A missing or invalid configuration falls back to the
    default model.
    """

    config_file = get_config_file()

    if not config_file.exists():
        return DEFAULT_MODEL

    try:
        with config_file.open("r", encoding="utf-8") as file:
            config = json.load(file)

        model = config.get("model", DEFAULT_MODEL)

        if is_supported_model(model):
            return model

    except (OSError, json.JSONDecodeError):
        pass

    return DEFAULT_MODEL


def set_current_model(model: str) -> None:
    """Persist the selected Wispr model."""

    if not is_supported_model(model):
        raise ValueError(
            f"Unsupported Wispr model: {model}"
        )

    config_dir = get_config_dir()
    config_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_file = get_config_file()

    config = {}

    if config_file.exists():
        try:
            with config_file.open(
                "r",
                encoding="utf-8",
            ) as file:
                config = json.load(file)

        except (OSError, json.JSONDecodeError):
            config = {}

    config["model"] = model

    temporary_file = config_file.with_suffix(".tmp")

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

    temporary_file.replace(config_file)