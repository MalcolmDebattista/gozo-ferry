import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import joblib
import mlflow
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from gozo_ferry.config import load_config
from gozo_ferry.db import save_prediction
from gozo_ferry.features import knots_to_kmh
from gozo_ferry.logging_setup import setup_logging
from gozo_ferry.metrics import INPUTS, LATENCY, PREDICTIONS
from gozo_ferry.model import FEATURES

load_dotenv()
setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

config = load_config()
WARNING_THRESHOLD = config["warning_threshold"]
# The code's version (pyproject.toml, through `make build`). The model's version comes from the registry.
APP_VERSION = os.environ.get("APP_VERSION", "dev")
# Which model to serve: the registry alias by default, or a local file for working offline.
MODEL_URI = os.environ.get("MODEL_URI", f"models:/{config['mlflow']['model_name']}@champion")

state = {"model": None, "model_version": None}


def load_model(uri):
    """Load the model named by uri. A registry alias is resolved to a version, so we know what we serve."""
    if not uri.startswith("models:/"):
        return joblib.load(uri), f"file:{uri}"
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", config["mlflow"]["tracking_uri"]))
    name, alias = uri.removeprefix("models:/").split("@")
    version = mlflow.MlflowClient().get_model_version_by_alias(name, alias).version
    return mlflow.sklearn.load_model(f"models:/{name}/{version}"), f"{name}/{version}"


def load_until_ready(uri, wait=5):
    """Runs in the background, so /health answers at once. Keeps trying until the registry answers."""
    while state["model"] is None:
        try:
            state["model"], state["model_version"] = load_model(uri)
            logger.info("Serving %s (from %s), app version %s", state["model_version"], uri, APP_VERSION)
        except Exception as err:
            logger.warning("No model loaded yet, retrying in %d s: %s", wait, err)
            time.sleep(wait)


@asynccontextmanager
async def lifespan(app):
    # Alive at once; ready only when a model is loaded. Until then /ready and /predict answer 503.
    threading.Thread(target=load_until_ready, args=(MODEL_URI,), daemon=True).start()
    yield


app = FastAPI(title="Gozo Channel cancellation model", lifespan=lifespan)


class Forecast(BaseModel):
    wind: float  # tomorrow's forecast wind speed, in knots


@app.get("/health")
def health():
    """Liveness: is the process running?"""
    return {"status": "ok"}


@app.get("/ready")
def ready(response: Response):
    """Readiness: can it do useful work? Only once a model is loaded."""
    if state["model"] is None:
        response.status_code = 503
        return {"ready": False, "model_version": None}
    return {"ready": True, "model_version": state["model_version"], "app_version": APP_VERSION}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(forecast: Forecast):
    model, version = state["model"], state["model_version"]
    if model is None:
        raise HTTPException(status_code=503, detail="No model loaded")
    with LATENCY.time():
        # Same conversion as training, so the model always sees km/h (no training-serving skew)
        df = knots_to_kmh(pd.DataFrame({"wind": [forecast.wind]}))
        probability = float(model.predict_proba(df[FEATURES])[0][1])
        warning = probability >= WARNING_THRESHOLD
        logger.info("wind=%.1f kn probability=%.3f warning=%s model=%s", forecast.wind, probability, warning, version)
        # Store the wind speed in knots, as the caller sent it, and the registry version that made the prediction
        save_prediction(forecast.wind, probability, warning, version)
    PREDICTIONS.inc()
    INPUTS.observe(forecast.wind)  # knots, as received
    return {
        "wind": forecast.wind,
        "probability_cancelled": round(probability, 3),
        "warning": warning,
        "model_version": version,
    }
