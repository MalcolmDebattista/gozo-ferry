import logging
import os

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Response
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
MODEL_PATH = os.environ.get("MODEL_PATH", config["model_path"])
WARNING_THRESHOLD = config["warning_threshold"]
MODEL_VERSION = os.environ.get("MODEL_VERSION", "dev")
model = joblib.load(MODEL_PATH)
logger.info("Model loaded from %s", MODEL_PATH)

app = FastAPI(title="Gozo Channel cancellation model")


class Forecast(BaseModel):
    wind: float  # tomorrow's forecast wind speed, in knots


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(forecast: Forecast):
    with LATENCY.time():
        # Same conversion as training, so the model always sees km/h (no training-serving skew)
        df = knots_to_kmh(pd.DataFrame({"wind": [forecast.wind]}))
        probability = float(model.predict_proba(df[FEATURES])[0][1])
        warning = probability >= WARNING_THRESHOLD
        logger.info("wind=%.1f kn probability=%.3f warning=%s", forecast.wind, probability, warning)
        # Store the wind speed in knots, as the caller sent it; only the model sees km/h
        save_prediction(forecast.wind, probability, warning, MODEL_VERSION)
    PREDICTIONS.inc()
    INPUTS.observe(forecast.wind)  # knots, as received
    return {
        "wind": forecast.wind,
        "probability_cancelled": round(probability, 3),
        "warning": warning,
    }
