"""Data validation (Session 5): check both data files against a schema before anything trains on them."""
import logging
import os
import sys

import pandas as pd
import pandera.pandas as pa
from dotenv import load_dotenv

from gozo_ferry.config import data_path, load_config
from gozo_ferry.logging_setup import setup_logging

logger = logging.getLogger(__name__)

# What a valid file looks like. strict=True rejects any column not listed here.
# Wind is in KNOTS here, as in the CSV; the model receives km/h through knots_to_kmh.
SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column("datetime64[ns]", coerce=True, unique=True),
        "wind": pa.Column(float, pa.Check.in_range(0, 100), coerce=True),
        "cancelled": pa.Column(int, pa.Check.isin([0, 1])),
    },
    strict=True,
)


def validate_file(path):
    """Return the validated data, or raise pandera's SchemaErrors listing every bad row."""
    df = pd.read_csv(path)
    return SCHEMA.validate(df, lazy=True)


def check_split(data, holdout, holdout_start):
    """The holdout must start on or after holdout_start, and share no day with the training data."""
    problems = []
    early = int((holdout["date"] < pd.Timestamp(holdout_start)).sum())
    if early:
        problems.append(f"{early} holdout rows are dated before holdout_start ({holdout_start})")
    shared = len(set(data["date"]) & set(holdout["date"]))
    if shared:
        problems.append(f"{shared} days appear in both the training data and the holdout")
    return problems


def main():
    load_dotenv()
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
    config = load_config()
    paths = [data_path(config), config["holdout_path"]]
    valid = {}
    for path in paths:
        try:
            valid[path] = validate_file(path)
            logger.info("%s: %d rows valid", path, len(valid[path]))
        except pa.errors.SchemaErrors as err:
            logger.error("%s failed validation:\n%s", path, err.failure_cases.to_string())
        except FileNotFoundError:
            logger.error("%s not found", path)
    failed = len(valid) < len(paths)
    if not failed:
        for problem in check_split(valid[paths[0]], valid[paths[1]], config["holdout_start"]):
            failed = True
            logger.error("The split is broken: %s", problem)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
