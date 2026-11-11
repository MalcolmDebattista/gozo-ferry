from pathlib import Path

import pandas as pd
import pytest

from gozo_ferry.data import load_data
from gozo_ferry.features import knots_to_kmh
from gozo_ferry.model import train_model


def test_knots_to_kmh_value():
    df = pd.DataFrame({"wind": [10.0]})
    assert knots_to_kmh(df)["wind"].iloc[0] == pytest.approx(18.52)


def test_knots_to_kmh_does_not_modify_input(sample_df):
    original = sample_df.copy()
    knots_to_kmh(sample_df)
    pd.testing.assert_frame_equal(sample_df, original)


def test_matches_original_notebook():
    """The notebook trains on all 365 days and gives 0.642 for its 29-knot forecast; the package must agree.

    Since Stage 12 the 365 days are split into the training data and the frozen holdout, so join them back.
    """
    folder = Path(__file__).resolve().parents[1] / "data"
    days = pd.concat([load_data(folder / "gozo_ferry.csv"), load_data(folder / "holdout.csv")])
    assert len(days) == 365
    model = train_model(knots_to_kmh(days), seed=42)
    forecast = knots_to_kmh(pd.DataFrame({"wind": [29.0]}))
    assert model.predict_proba(forecast[["wind"]])[0][1] == pytest.approx(0.642, abs=5e-4)
