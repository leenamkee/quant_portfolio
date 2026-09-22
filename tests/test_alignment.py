import numpy as np
import pandas as pd
import pytest

from alignment import align_prices, daily_returns
from errors import ValidationError


def frame(values, start="2024-01-01"):
    length = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.bdate_range(start, periods=length), dtype=float)


def test_complete_data_is_unchanged():
    data = frame({"A": [1, 2, 3, 4], "B": [10, 11, 12, 13]})
    aligned = align_prices(data)
    assert aligned.prices.equals(data)
    assert aligned.limiting_ticker is None and aligned.dropped_days == 0
    assert (aligned.start, aligned.end, aligned.days) == (data.index[0], data.index[-1], 4)


def test_analysis_starts_at_the_latest_first_valid_date_and_names_the_ticker():
    data = frame({"A": [1, 2, 3, 4, 5], "B": [np.nan, np.nan, 30, 31, 32]})
    aligned = align_prices(data)
    assert aligned.start == data.index[2] and aligned.limiting_ticker == "B" and aligned.days == 3
    assert aligned.first_valid["A"] == data.index[0] and aligned.first_valid["B"] == data.index[2]


def test_analysis_ends_at_the_earliest_last_valid_date():
    data = frame({"A": [1, 2, 3, 4, 5], "B": [10, 11, 12, np.nan, np.nan]})
    aligned = align_prices(data)
    assert aligned.end == data.index[2] and aligned.days == 3


def test_missing_days_inside_the_window_are_dropped_not_forward_filled(gap_prices):
    aligned = align_prices(gap_prices)
    assert list(aligned.prices.index) == [gap_prices.index[2], gap_prices.index[4], gap_prices.index[5]]
    assert aligned.dropped_days == 1
    assert not aligned.prices.isna().any().any()
    assert list(aligned.prices["B"]) == [50.0, 52.0, 53.0]  # 51 같은 채워 넣은 값이 없다


def test_non_overlapping_periods_are_rejected():
    data = frame({"A": [1, 2, np.nan, np.nan], "B": [np.nan, np.nan, 3, 4]})
    with pytest.raises(ValidationError, match="겹치지"):
        align_prices(data)


def test_fewer_than_two_common_days_is_rejected():
    data = frame({"A": [1, 2, 3], "B": [np.nan, np.nan, 3]})
    with pytest.raises(ValidationError, match="공통 거래일이 부족"):
        align_prices(data)


@pytest.mark.parametrize("bad", [None, pd.DataFrame()])
def test_empty_input_is_rejected(bad):
    with pytest.raises(ValidationError, match="비어"):
        align_prices(bad)


def test_a_column_without_any_price_is_rejected_by_name():
    with pytest.raises(ValidationError, match="B"):
        align_prices(frame({"A": [1, 2, 3], "B": [np.nan] * 3}))


def test_daily_returns_never_fill_missing_values():
    returns = daily_returns(frame({"A": [100, 110, np.nan, 121]}))["A"]
    assert returns.iloc[0] == pytest.approx(0.1)
    assert np.isnan(returns.iloc[1]) and np.isnan(returns.iloc[2])


def test_daily_returns_of_complete_data_match_pct_change(prices):
    assert np.allclose(daily_returns(prices), prices.pct_change().iloc[1:])
