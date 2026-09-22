import numpy as np
import pandas as pd
import pytest

import rebalancing_guide as guide
from fakes import make_download


def trades(df):
    return dict(zip(df["Ticker"], df["Shares to Buy/Sell"]))


# ---------- 매수/매도 계산 (손계산) ----------

def test_balanced_portfolio_needs_no_trades():
    df, total, cash = guide.calculate_rebalancing_guide({"A": 10, "B": 10}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    assert trades(df) == {"A": 0, "B": 0}
    assert total == 2000 and cash == 0


def test_imbalanced_portfolio_sells_overweight_and_buys_underweight():
    df, total, cash = guide.calculate_rebalancing_guide({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    assert trades(df) == {"A": -5, "B": 5}
    assert total == 1000 and cash == pytest.approx(500)


def test_buy_and_sell_are_classified_by_sign():
    # 총 2,500원: 목표 A 500(-5주), B 1,000(+10주), C 500(-5주), D 500(변화 없음)
    df, _, _ = guide.calculate_rebalancing_guide(
        {"A": 10, "B": 0, "C": 10, "D": 5},
        {"A": 0.2, "B": 0.4, "C": 0.2, "D": 0.2},
        {"A": 100, "B": 100, "C": 100, "D": 100},
    )
    assert trades(df) == {"A": -5, "B": 10, "C": -5, "D": 0}
    assert list(df[df["Shares to Buy/Sell"] > 0]["Ticker"]) == ["B"]
    assert list(df[df["Shares to Buy/Sell"] < 0]["Ticker"]) == ["A", "C"]


def test_target_weights_not_summing_to_one_are_normalized():
    a, _, _ = guide.calculate_rebalancing_guide({"A": 10, "B": 0}, {"A": 0.25, "B": 0.25}, {"A": 100, "B": 100})
    b, _, _ = guide.calculate_rebalancing_guide({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    assert trades(a) == trades(b)


def test_output_rows_follow_input_order():
    df, _, _ = guide.calculate_rebalancing_guide({"B": 1, "A": 2, "C": 0}, {"C": 0.4, "A": 0.3, "B": 0.3}, {"A": 100, "B": 100, "C": 100})
    assert list(df["Ticker"]) == ["B", "A", "C"]


def test_money_columns_use_won_format():
    df, _, _ = guide.calculate_rebalancing_guide({"A": 10}, {"A": 1.0}, {"A": 100})
    assert df.loc[0, "Current Value"] == "1,000원"
    assert df.loc[0, "Current Price"] == "100원"


def test_rebalancing_cost_is_half_of_traded_value_times_rate():
    cost = guide.calculate_rebalancing_cost({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    assert cost == pytest.approx(0.5)  # (500 + 500) / 2 * 0.1%


# ---------- 경계값·실패 경로: 수정 후 기대 동작 (A5, A8) ----------

@pytest.mark.xfail(reason="A5: 보유 종목의 가격이 없으면 0원으로 계산해 다른 종목을 잘못 매도하라고 안내한다 (단계 1)")
def test_missing_price_for_held_ticker_is_an_error():
    with pytest.raises(ValueError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100})


@pytest.mark.xfail(reason="A5: 가격 0이 조용히 0주 안내를 만든다 (단계 1)")
def test_zero_price_for_held_ticker_is_an_error():
    with pytest.raises(ValueError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100, "TICKB": 0})


@pytest.mark.xfail(reason="A5: NaN 가격이 티커를 알 수 없는 오류가 된다 (단계 1)")
def test_nan_price_error_names_the_ticker():
    with pytest.raises(ValueError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100, "TICKB": float("nan")})


@pytest.mark.xfail(reason="A8: 목표 비중 합계 0이 ZeroDivisionError가 된다 (단계 1)")
def test_zero_target_weight_sum_is_rejected_with_clear_error():
    with pytest.raises(ValueError):
        guide.calculate_rebalancing_guide({"A": 10}, {"A": 0}, {"A": 100})


# ---------- 현재가 조회 ----------

def _close_frame():
    idx = pd.bdate_range("2024-01-01", periods=5)
    return pd.DataFrame({"A": [1.0, 2, 3, 4, 5], "B": [10.0, 20, 30, 40, np.nan]}, index=idx)


@pytest.mark.xfail(reason="§9-2 확정: 가격 기준은 '마지막 사용 가능한 거래일 종가'다. 현재는 끝에서 두 번째 행을 쓴다 (단계 1)")
def test_current_prices_use_last_available_close(monkeypatch):
    monkeypatch.setattr(guide.yf, "download", make_download(_close_frame()))
    assert guide.get_current_prices(["A", "B"]) == {"A": 5.0, "B": 40.0}


@pytest.mark.xfail(reason="A5: 조회 실패를 print 후 빈 dict로 숨긴다 (단계 1)")
def test_price_lookup_failure_is_not_hidden(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(guide.yf, "download", broken)
    with pytest.raises(Exception):
        guide.get_current_prices(["A"])
