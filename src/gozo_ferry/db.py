import logging
import os

import psycopg

logger = logging.getLogger(__name__)

INSERT_SQL = """
    INSERT INTO predictions (wind_knots, probability, warning, model_version)
    VALUES (%s, %s, %s, %s)
"""


def save_prediction(wind_knots, probability, warning, model_version):
    url = os.environ.get("DATABASE_URL")
    if not url:
        logger.debug("DATABASE_URL not set; prediction not stored")
        return
    try:
        with psycopg.connect(url) as conn:
            conn.execute(INSERT_SQL, (wind_knots, probability, warning, model_version))
    except psycopg.Error:
        logger.exception("Could not store the prediction")
