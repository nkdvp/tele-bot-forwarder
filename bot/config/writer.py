from __future__ import annotations
import yaml
from bot.config.loader import Config, load_config


def save_config(config: Config, path: str = "config.yaml") -> None:
    with open(path, "w") as f:
        yaml.dump(config._raw, f, default_flow_style=False, allow_unicode=True)


def save_and_reload(config: Config, path: str = "config.yaml") -> None:
    """Persist _raw to disk, then re-parse it and update config in-place.

    This ensures that runtime command changes (filter, mask) take effect
    immediately without requiring a bot restart.
    """
    save_config(config, path)
    fresh = load_config(path)
    config.admins = fresh.admins
    config.masking = fresh.masking
    config.pairs = fresh.pairs
