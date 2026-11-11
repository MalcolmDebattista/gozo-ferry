"""Property-based tests (Session 5): rules that must hold for every wind speed, not just the examples."""
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gozo_ferry.config import data_path, load_config
from gozo_ferry.data import load_data, training_window
from gozo_ferry.features import knots_to_kmh
from gozo_ferry.model import train_model

CONFIG = load_config()
# The strongest wind the service must answer for, in knots: hurricane force (64 kn) with headroom.
# A business number, not a sample statistic (the data peaks at about 45 kn).
MAX_WIND = 80.0


@pytest.fixture(scope="module")
def model():
    # The same days the gate trains on, so this tests the model that ships.
    df = knots_to_kmh(training_window(load_data(data_path(CONFIG)), CONFIG))
    return train_model(df, seed=CONFIG["seed"])


def prob(model, knots):
    # Knots in, km/h to the model: the same conversion as training and the API.
    df = knots_to_kmh(pd.DataFrame({"wind": [knots]}))
    return float(model.predict_proba(df[["wind"]])[0][1])


@settings(max_examples=200, deadline=None)
@given(knots=st.floats(min_value=0.0, max_value=MAX_WIND))
def test_probability_is_a_probability(model, knots):
    assert 0.0 <= prob(model, knots) <= 1.0


@settings(max_examples=200, deadline=None)
@given(a=st.floats(min_value=0.0, max_value=MAX_WIND), b=st.floats(min_value=0.0, max_value=MAX_WIND))
def test_stronger_wind_never_makes_a_cancellation_less_likely(model, a, b):
    low, high = sorted((a, b))
    assert prob(model, high) >= prob(model, low) - 1e-9
