import logging

logger = logging.getLogger(__name__)

KNOTS_TO_KMH = 1.852


def knots_to_kmh(df):
    """Return a copy of df with the wind column converted from knots to km/h.

    The input frame is left unchanged, so running this twice on the same
    data cannot convert the wind speed twice (the notebook's VAT-style bug).
    """
    out = df.copy()
    out["wind"] = out["wind"] * KNOTS_TO_KMH
    logger.info("Wind converted from knots to km/h")
    return out
