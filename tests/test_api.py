import importlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gozo_ferry.features import knots_to_kmh
from gozo_ferry.model import save_model, train_model


@pytest.fixture
def client_and_model(sample_df, tmp_path, monkeypatch):
    model = train_model(knots_to_kmh(sample_df), seed=42)
    path = tmp_path / "model.joblib"
    save_model(model, path)
    monkeypatch.setenv("MODEL_PATH", str(path))
    import gozo_ferry.api as api
    api = importlib.reload(api)
    return TestClient(api.app), model


def test_health(client_and_model):
    client, _ = client_and_model
    assert client.get("/health").json() == {"status": "ok"}


def test_api_matches_training_code(client_and_model):
    """30 knots through the API must give the same probability as the training path."""
    client, model = client_and_model
    expected = model.predict_proba(knots_to_kmh(pd.DataFrame({"wind": [30.0]}))[["wind"]])[0][1]
    body = client.post("/predict", json={"wind": 30}).json()
    assert body["probability_cancelled"] == pytest.approx(round(expected, 3))
    assert isinstance(body["warning"], bool)


def test_missing_wind_is_rejected(client_and_model):
    client, _ = client_and_model
    assert client.post("/predict", json={"speed": 30}).status_code == 422


def test_prediction_is_stored_in_knots(client_and_model, monkeypatch):
    """The stored row holds the wind speed as the caller sent it, not km/h."""
    import gozo_ferry.api as api
    saved = []
    monkeypatch.setattr(api, "save_prediction", lambda *row: saved.append(row))
    client, _ = client_and_model
    body = client.post("/predict", json={"wind": 25}).json()
    wind, probability, warning, version = saved[0]
    assert wind == 25
    assert round(probability, 3) == body["probability_cancelled"]
    assert warning is body["warning"]


def test_metrics_record_wind_in_knots(client_and_model):
    client, _ = client_and_model
    client.post("/predict", json={"wind": 22})
    text = client.get("/metrics").text
    assert "predictions_total" in text
    assert "prediction_latency_seconds_bucket" in text
    assert 'prediction_input_bucket{le="25.0"}' in text
