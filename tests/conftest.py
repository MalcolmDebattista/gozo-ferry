import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_df():
    rng = np.random.default_rng(0)
    wind = rng.uniform(0, 40, 60)
    return pd.DataFrame({"wind": wind, "cancelled": (wind > 22).astype(int)})
