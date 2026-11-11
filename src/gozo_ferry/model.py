import logging
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

FEATURES = ["wind"]
TARGET = "cancelled"


def train_model(df, seed):
    """Fit a logistic regression of cancellation on wind speed (km/h).

    Since Stage 12 it is trained on the training window only (every day before the
    frozen holdout). Trained on all 365 days, it gives the notebook's 0.642 at 29 knots.
    """
    model = LogisticRegression(random_state=seed)
    model.fit(df[FEATURES], df[TARGET])
    logger.info("Training accuracy: %.4f", model.score(df[FEATURES], df[TARGET]))
    return model


def save_model(model, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    logger.info("Model saved to %s", path)
