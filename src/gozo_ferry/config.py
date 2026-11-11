import os

import yaml


def load_config(path=None):
    path = path or os.environ.get("CONFIG_PATH", "config/config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def data_path(config):
    """The training data file. DATA_PATH in the environment overrides config.yaml, for every command."""
    return os.environ.get("DATA_PATH", config["data_path"])
