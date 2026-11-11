import logging
import os
import sys

from dotenv import load_dotenv

from gozo_ferry.config import data_path, load_config
from gozo_ferry.data import load_data, training_window
from gozo_ferry.features import knots_to_kmh
from gozo_ferry.logging_setup import setup_logging
from gozo_ferry.model import save_model, train_model
from gozo_ferry.seed import set_seed

logger = logging.getLogger(__name__)


def main():
    load_dotenv()
    config = load_config()
    set_seed(config["seed"])
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    try:
        model_path = os.environ.get("MODEL_PATH", config["model_path"])

        df = training_window(load_data(data_path(config)), config)
        logger.info("Training on %d days in the training window", len(df))
        df = knots_to_kmh(df)
        model = train_model(df, seed=config["seed"])
        save_model(model, model_path)
    except Exception:
        logger.exception("Training failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
