"""The quality gate (Session 5).

Exit codes of gozo-gate: 0 pass, 1 below the threshold, 2 the frozen holdout has changed, 3 a file is missing.
Run as `gozo-gate` (frozen holdout) or `gozo-gate --split random` (a random 20 % of the training window, for comparison).
"""
import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from gozo_ferry.config import data_path, load_config
from gozo_ferry.data import load_data, training_window
from gozo_ferry.features import knots_to_kmh
from gozo_ferry.logging_setup import setup_logging
from gozo_ferry.model import FEATURES, TARGET, train_model
from gozo_ferry.seed import set_seed

logger = logging.getLogger(__name__)

# Every metric we might gate on: each takes the true labels, the predicted labels and the predicted probabilities.
METRICS = {
    "accuracy": lambda y, pred, prob: accuracy_score(y, pred),
    "precision": lambda y, pred, prob: precision_score(y, pred, zero_division=0),
    "recall": lambda y, pred, prob: recall_score(y, pred, zero_division=0),
    "f1": lambda y, pred, prob: f1_score(y, pred, zero_division=0),
    "roc_auc": lambda y, pred, prob: roc_auc_score(y, prob),
}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def predict(model, X, threshold):
    """Probabilities, and the warning the API would give (probability >= warning_threshold)."""
    prob = model.predict_proba(X)[:, 1]
    return (prob >= threshold).astype(int), prob


def interval(y, pred, prob, name, seed, rounds=1000):
    """A 95 % bootstrap interval for one metric: how far the score could move on another sample of this size."""
    y = np.asarray(y)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(rounds):
        rows = rng.integers(0, len(y), len(y))
        if len(set(y[rows])) == 2:  # recall and ROC-AUC need both classes
            values.append(METRICS[name](y[rows], pred[rows], prob[rows]))
    return np.percentile(values, [2.5, 97.5])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score the model and apply the quality gate.")
    parser.add_argument("--split", choices=["holdout", "random"], default="holdout")
    args = parser.parse_args(argv)

    load_dotenv()
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
    config = load_config()
    seed = config["seed"]
    set_seed(seed)

    # 0. A missing file is neither a weak model nor a moved goalpost: say so, with a code of its own.
    for path in (data_path(config), config["holdout_path"]):
        if not Path(path).exists():
            logger.error("Cannot run the gate: %s not found", path)
            sys.exit(3)

    # 1. The goalposts: refuse to run if the frozen holdout has changed.
    expected = config["holdout_sha256"]
    actual = sha256(config["holdout_path"])
    if actual != expected:
        logger.error("Holdout fingerprint changed: expected %s, found %s", expected[:12], actual[:12])
        sys.exit(2)

    # 2. Train on the window before the holdout, exactly as gozo-train does (knots -> km/h first).
    data = knots_to_kmh(training_window(load_data(data_path(config)), config))

    # 3. Score on the frozen holdout, or on a random 20 % of the training window.
    if args.split == "holdout":
        model = train_model(data, seed=seed)
        test = knots_to_kmh(load_data(config["holdout_path"]))
        X_test, y_test = test[FEATURES], test[TARGET]
        label = f"frozen holdout from {config['holdout_start']} ({len(test)} days)"
    else:
        train, test = train_test_split(data, test_size=0.2, random_state=seed, stratify=data[TARGET])
        model = train_model(train, seed=seed)
        X_test, y_test = test[FEATURES], test[TARGET]
        label = f"random 20 % of the training window ({len(test)} days)"

    pred, prob = predict(model, X_test, config["warning_threshold"])
    metrics = {name: metric(y_test, pred, prob) for name, metric in METRICS.items()}
    name, threshold = config["gate_metric"], config["gate_threshold"]
    low, high = interval(y_test, pred, prob, name, seed)
    majority = max(y_test.mean(), 1 - y_test.mean())

    print(f"Scored on the {label}: {int(y_test.sum())} cancelled days")
    for metric, value in metrics.items():
        print(f"  {metric:<10} {value:.3f}")
    print(f"  baseline   {majority:.3f}   accuracy of always predicting 'no cancellation'")
    print(f"  interval   {low:.3f} to {high:.3f}   95 % interval for {name} on a sample this size")

    # 4. The gate.
    value = metrics[name]
    if value < threshold:
        print(f"GATE FAIL: {name} {value:.3f} is below {threshold:.2f}")
        sys.exit(1)
    print(f"GATE PASS: {name} {value:.3f} meets {threshold:.2f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
