import datetime as dt

import pandas as pd
import pytest

from errors import ValidationError
import validation as v


# ---------- 비중 ----------

def test_weights_are_returned_as_floats():
    assert v.validate_weights({"A": 1, "B": 2}) == {"A": 1.0, "B": 2.0}


@pytest.mark.parametrize("weights,match", [
    ({}, "비어"),
    ({"A": 0, "B": 0}, "합계가 0"),
    ({"A": -0.1, "B": 1.1}, "음수"),
    ({"A": float("nan"), "B": 1.0}, "숫자가 아닙니다"),
    ({"A": float("inf")}, "숫자가 아닙니다"),
    ({"A": "abc"}, "숫자가 아닙니다"),
    ({"A": None}, "숫자가 아닙니다"),
])
def test_invalid_weights_are_rejected_with_reason(weights, match):
    with pytest.raises(ValidationError, match=match):
        v.validate_weights(weights)


def test_weight_error_names_the_ticker_and_uses_custom_label():
    with pytest.raises(ValidationError, match="TICKB.*목표 비중"):
        v.validate_weights({"TICKA": 1.0, "TICKB": -1.0}, "목표 비중")


# ---------- 보유 수량 ----------

def test_holdings_accept_zero_and_positive_numbers():
    assert v.validate_holdings({"A": 0, "B": 3}) == {"A": 0, "B": 3}
    assert v.validate_holdings(None) == {}


@pytest.mark.parametrize("bad", [-1, float("nan"), "3", None, True])
def test_invalid_holdings_are_rejected(bad):
    with pytest.raises(ValidationError, match="TICKB"):
        v.validate_holdings({"TICKB": bad})


# ---------- 자본·주기 ----------

@pytest.mark.parametrize("capital", [0, -1, float("nan"), "100", None])
def test_invalid_capital_is_rejected(capital):
    with pytest.raises(ValidationError):
        v.validate_capital(capital)


@pytest.mark.parametrize("freq", [None, "M", "Q", "Y"])
def test_valid_frequencies_pass(freq):
    assert v.validate_frequency(freq) == freq


@pytest.mark.parametrize("freq", ["W", "m", "", "None", 1])
def test_invalid_frequencies_are_rejected(freq):
    with pytest.raises(ValidationError):
        v.validate_frequency(freq)


# ---------- 가격 표 ----------

def test_prices_frame_must_be_non_empty_dataframe():
    for bad in (None, pd.DataFrame(), pd.DataFrame(index=pd.bdate_range("2024-01-01", periods=3)), [1, 2, 3]):
        with pytest.raises(ValidationError, match="비어"):
            v.validate_prices_frame(bad)


def test_prices_frame_rejects_fully_missing_columns():
    frame = pd.DataFrame({"A": [1.0, 2.0], "B": [float("nan")] * 2})
    with pytest.raises(ValidationError, match="B"):
        v.validate_prices_frame(frame)


# ---------- 날짜 ----------

TODAY = dt.date(2026, 9, 22)


def test_end_date_is_made_inclusive_by_adding_a_day():
    start, end_exclusive = v.validate_dates(dt.date(2026, 1, 1), dt.date(2026, 3, 31), today=TODAY)
    assert start == pd.Timestamp("2026-01-01") and end_exclusive == pd.Timestamp("2026-04-01")


def test_start_after_end_is_rejected():
    with pytest.raises(ValidationError, match="시작일.*종료일"):
        v.validate_dates(dt.date(2026, 6, 1), dt.date(2026, 1, 1), today=TODAY)


def test_same_day_range_is_accepted_here():
    v.validate_dates(dt.date(2026, 1, 5), dt.date(2026, 1, 5), today=TODAY)


def test_future_end_date_is_rejected_but_one_day_ahead_is_tolerated_for_timezones():
    v.validate_dates(dt.date(2026, 1, 1), TODAY + dt.timedelta(days=1), today=TODAY)  # 서버 UTC ↔ 사용자 KST
    with pytest.raises(ValidationError, match="오늘 이후"):
        v.validate_dates(dt.date(2026, 1, 1), TODAY + dt.timedelta(days=2), today=TODAY)


@pytest.mark.parametrize("start,end", [("not a date", "2026-01-01"), (None, "2026-01-01"), ("2026-01-01", None)])
def test_unparseable_dates_are_rejected(start, end):
    with pytest.raises(ValidationError):
        v.validate_dates(start, end, today=TODAY)
