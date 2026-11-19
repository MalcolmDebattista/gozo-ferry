"""The API serves only once a model is loaded (Session 6, Stage 15). No registry needed: a local file stands in."""
import importlib
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gozo_ferry.features import knots_to_kmh
from gozo_ferry.model import save_model, train_model


@pytest.fixture
def model_and_file(sample_df, tmp_path):
    model = train_model(knots_to_kmh(sample_df), seed=42)
    path = tmp_path / "model.joblib"
    save_model(model, path)
    return model, str(path)


@pytest.fixture
def api(model_and_file, monkeypatch):
    monkeypatch.setenv("MODEL_URI", model_and_file[1])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import gozo_ferry.api as api
    return importlib.reload(api)


@pytest.fixture
def client(api):
    with TestClient(api.app) as client:
        for _ in range(50):          # the model loads in the background
            if client.get("/ready").status_code == 200:
                break
            time.sleep(0.1)
        yield client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reports_the_model_it_serves(client, model_and_file):
    body = client.get("/ready").json()
    assert body["ready"] is True
    assert body["model_version"] == f"file:{model_and_file[1]}"


def test_api_matches_training_code(client, model_and_file):
    """30 knots through the API must give the same probability as the training path."""
    model, path = model_and_file
    expected = model.predict_proba(knots_to_kmh(pd.DataFrame({"wind": [30.0]}))[["wind"]])[0][1]
    body = client.post("/predict", json={"wind": 30}).json()
    assert body["probability_cancelled"] == pytest.approx(round(expected, 3))
    assert isinstance(body["warning"], bool)
    assert body["model_version"] == f"file:{path}"


def test_missing_wind_is_rejected(client):
    assert client.post("/predict", json={"speed": 30}).status_code == 422


def test_prediction_is_stored_in_knots_with_its_model_version(client, api, model_and_file, monkeypatch):
    """The stored row holds the wind speed as the caller sent it, not km/h, and the version that made it."""
    saved = []
    monkeypatch.setattr(api, "save_prediction", lambda *row: saved.append(row))
    body = client.post("/predict", json={"wind": 25}).json()
    wind, probability, warning, version = saved[0]
    assert wind == 25
    assert round(probability, 3) == body["probability_cancelled"]
    assert warning is body["warning"]
    assert version == f"file:{model_and_file[1]}"


def test_metrics_record_wind_in_knots(client):
    client.post("/predict", json={"wind": 22})
    text = client.get("/metrics").text
    assert "predictions_total" in text
    assert "prediction_latency_seconds_bucket" in text
    assert 'prediction_input_bucket{le="25.0"}' in text


def test_alive_but_not_ready_without_a_model(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_URI", str(tmp_path / "missing.joblib"))
    import gozo_ferry.api as api
    api = importlib.reload(api)
    with TestClient(api.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/predict", json={"wind": 30}).status_code == 503
