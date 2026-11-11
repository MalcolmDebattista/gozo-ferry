import logging

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"wind", "cancelled"}


def load_data(path):
    """Read the daily data: date, wind (knots) and cancelled (0/1)."""
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def training_window(df, config):
    """Days before the holdout starts and, if train_start is set, on or after it."""
    dates = pd.to_datetime(df["date"])
    keep = dates < pd.Timestamp(config["holdout_start"])
    if config.get("train_start"):
        keep &= dates >= pd.Timestamp(config["train_start"])
    return df[keep]
