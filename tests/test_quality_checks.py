"""The checks that guard the pipeline must themselves be tested."""
import pandas as pd
import pandera.pandas as pa
import pytest

from gozo_ferry import evaluate
from gozo_ferry.validate import check_split, validate_file

GOOD = {"date": ["2025-03-01"], "wind": [12.5], "cancelled": [0]}


def test_validate_accepts_a_good_row(tmp_path):
    path = tmp_path / "good.csv"
    pd.DataFrame(GOOD).to_csv(path, index=False)
    assert len(validate_file(path)) == 1


@pytest.mark.parametrize(
    "column,value",
    [("wind", -3.0), ("wind", 150.0), ("cancelled", 2), ("date", "not a date")],
)
def test_validate_rejects_a_bad_row(tmp_path, column, value):
    path = tmp_path / "bad.csv"
    pd.DataFrame({**GOOD, column: [value]}).to_csv(path, index=False)
    with pytest.raises(pa.errors.SchemaErrors):
        validate_file(path)


def test_validate_rejects_an_unexpected_column(tmp_path):
    path = tmp_path / "extra.csv"
    pd.DataFrame({**GOOD, "wave_height": [1.2]}).to_csv(path, index=False)
    with pytest.raises(pa.errors.SchemaErrors):
        validate_file(path)


def test_validate_rejects_a_repeated_day(tmp_path):
    path = tmp_path / "twice.csv"
    pd.DataFrame({k: v * 2 for k, v in GOOD.items()}).to_csv(path, index=False)
    with pytest.raises(pa.errors.SchemaErrors):
        validate_file(path)


def frame(rows):
    df = pd.DataFrame(rows, columns=["date", "wind", "cancelled"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_split_check_passes_a_clean_split_and_names_a_broken_one():
    data = frame([["2025-10-01", 12.0, 0]])
    assert check_split(data, frame([["2025-11-10", 30.0, 1]]), "2025-11-06") == []
    early = check_split(data, frame([["2025-11-01", 30.0, 1]]), "2025-11-06")
    assert "before holdout_start" in early[0]
    shared = check_split(data, frame([["2025-10-01", 12.0, 0]]), "2025-09-01")
    assert "both" in shared[0]


def test_gate_refuses_a_changed_holdout(tmp_path, monkeypatch):
    path = tmp_path / "holdout.csv"
    pd.DataFrame(GOOD).to_csv(path, index=False)
    config = evaluate.load_config()
    config["holdout_path"] = str(path)  # same SHA-256 expected, different file
    monkeypatch.setattr(evaluate, "load_config", lambda: config)
    with pytest.raises(SystemExit) as exit_info:
        evaluate.main([])
    assert exit_info.value.code == 2
