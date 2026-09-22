import datetime as dt

import numpy as np
import pandas as pd
import pytest

import custom_backtest as cb
import portfolio_engine as pe
from errors import MarketDataError, ValidationError
import rebalance_engine as engine
from fakes import make_download


# ---------- 도메인 규칙: DC형 퇴직연금 위험자산 70% ----------

SAFE_TICKER = "273130.KS"  # KODEX 종합채권(AA-이상)액티브: 주식 0%


def test_default_target_weights_sum_to_one():
    assert sum(pe.DEFAULT_TARGET_WEIGHTS.values()) == pytest.approx(1.0)


def test_default_portfolio_respects_dc_risky_asset_cap():
    risky = sum(w for t, w in pe.DEFAULT_TARGET_WEIGHTS.items() if t != SAFE_TICKER)
    assert risky <= 0.70 + 1e-9
    assert pe.DEFAULT_TARGET_WEIGHTS[SAFE_TICKER] >= 0.30 - 1e-9


def test_every_default_ticker_has_a_name():
    assert set(pe.DEFAULT_TARGET_WEIGHTS) <= set(pe.TICKER_NAMES)
    assert all(t.endswith(".KS") for t in pe.DEFAULT_TARGET_WEIGHTS)


# ---------- target_weight ----------

def test_target_weight_returns_defaults_for_known_tickers():
    weights = pe.target_weight_portfolio(list(pe.DEFAULT_TARGET_WEIGHTS))
    assert weights == pytest.approx(pe.DEFAULT_TARGET_WEIGHTS)


def test_target_weight_renormalizes_a_known_subset():
    weights = pe.target_weight_portfolio(["360750.KS", "411060.KS"])
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["360750.KS"] / weights["411060.KS"] == pytest.approx(0.25 / 0.07)


def test_target_weight_falls_back_to_equal_weight_for_unknown_ticker():
    assert pe.target_weight_portfolio(["360750.KS", "UNKNOWN"]) == {"360750.KS": 0.5, "UNKNOWN": 0.5}


def test_target_weight_of_nothing_is_empty():
    assert pe.target_weight_portfolio([]) == {}


# ---------- 최적화 ----------

@pytest.mark.parametrize("method", ["equal_weight", "max_sharpe", "min_volatility"])
def test_optimize_portfolio_returns_valid_long_only_weights(prices, method):
    weights = pe.optimize_portfolio(prices, method=method)
    assert set(weights) == set(prices.columns)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)
    assert all(w >= -1e-9 for w in weights.values())


def test_optimize_target_weight_uses_default_weights(krx_prices):
    weights = pe.optimize_portfolio(krx_prices, method="target_weight")
    assert weights == pytest.approx(pe.DEFAULT_TARGET_WEIGHTS)


def test_discrete_allocation_never_exceeds_capital(prices):
    weights = {c: 0.25 for c in prices.columns}
    latest = prices.iloc[-1]
    allocation, leftover = pe.get_discrete_allocation(weights, latest, 1_000_000)
    spent = sum(latest[t] * n for t, n in allocation.items())
    assert leftover >= 0 and spent + leftover == pytest.approx(1_000_000)


# ---------- 시세 조회 (가짜 Yahoo) ----------

def test_get_stock_data_returns_close_prices_as_frame(monkeypatch, prices):
    monkeypatch.setattr(pe.yf, "download", make_download(prices))
    data = pe.get_stock_data(["AAA.KS", "BBB.KS"], "2024-01-01", "2024-12-31")
    assert list(data.columns) == ["AAA.KS", "BBB.KS"]
    assert data.equals(prices[["AAA.KS", "BBB.KS"]])


def test_get_stock_data_wraps_a_series_into_a_frame(monkeypatch):
    series = pd.Series([1.0, 2.0], index=pd.bdate_range("2024-01-01", periods=2), name="Close")
    monkeypatch.setattr(pe.yf, "download", lambda *a, **k: {"Close": series})
    data = pe.get_stock_data(["AAA.KS"], "2024-01-01", "2024-01-31")
    assert isinstance(data, pd.DataFrame) and list(data.columns) == ["AAA.KS"]


def test_end_date_is_included_by_requesting_the_next_day(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(pe.yf, "download", make_download(prices, calls))
    pe.get_stock_data(["AAA.KS"], dt.date(2024, 1, 2), dt.date(2024, 3, 29))
    assert calls[0]["start"] == pd.Timestamp("2024-01-02") and calls[0]["end"] == pd.Timestamp("2024-03-30")


def test_tickers_are_trimmed_and_deduplicated_in_order(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(pe.yf, "download", make_download(prices, calls))
    data = pe.get_stock_data([" BBB.KS", "AAA.KS", "", "BBB.KS", "AAA.KS "], "2024-01-01", "2024-03-01")
    assert calls[0]["tickers"] == ["BBB.KS", "AAA.KS"] and list(data.columns) == ["BBB.KS", "AAA.KS"]


@pytest.mark.parametrize("tickers", [[], [""], ["  ", ""]])
def test_get_stock_data_without_tickers_is_rejected(tickers):
    with pytest.raises(ValidationError, match="티커"):
        pe.get_stock_data(tickers, "2024-01-01", "2024-03-01")


def test_get_stock_data_rejects_start_after_end():
    with pytest.raises(ValidationError, match="시작일"):
        pe.get_stock_data(["AAA.KS"], "2024-06-01", "2024-01-01")


def test_get_stock_data_rejects_a_future_end_date():
    future = dt.date.today() + dt.timedelta(days=30)
    with pytest.raises(ValidationError, match="오늘 이후"):
        pe.get_stock_data(["AAA.KS"], "2024-01-01", future)


def test_download_failure_is_reported_as_market_data_error(monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError("network down")
    monkeypatch.setattr(pe.yf, "download", broken)
    with pytest.raises(MarketDataError, match="network down"):
        pe.get_stock_data(["AAA.KS"], "2024-01-01", "2024-03-01")


def test_empty_download_result_is_a_market_data_error(monkeypatch):
    monkeypatch.setattr(pe.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(MarketDataError, match="비어"):
        pe.get_stock_data(["AAA.KS"], "2024-01-01", "2024-03-01")


def test_ticker_without_any_price_is_reported_by_name(monkeypatch, prices):
    monkeypatch.setattr(pe.yf, "download", make_download(prices))
    with pytest.raises(MarketDataError, match="NOPE.KS"):
        pe.get_stock_data(["AAA.KS", "NOPE.KS"], "2024-01-01", "2024-03-01")


# ---------- custom_backtest (얇은 래퍼) ----------

def test_custom_backtest_matches_engine_and_ignores_zero_weight_tickers(prices):
    weights = {"AAA.KS": 0.5, "BBB.KS": 0.5}
    custom = cb.backtest_custom_portfolio(prices, {**weights, "ZZZ.KS": 0.0}, "M", 1_000_000)
    full = {**weights, "CCC.KS": 0.0, "DDD.KS": 0.0}
    direct = engine.backtest_rebalancing(prices, full, "M", 1_000_000)
    assert np.allclose(custom["Portfolio Value"], direct["Portfolio Value"])


def test_custom_backtest_reexports_the_engine_metrics_function():
    assert cb.calculate_metrics is engine.calculate_metrics


def test_custom_backtest_rejects_a_weighted_ticker_without_price_data(prices):
    # 예전에는 가격이 없는 종목을 조용히 버리고 다른 구성으로 계산했다
    with pytest.raises(ValidationError, match="ZZZ.KS"):
        cb.backtest_custom_portfolio(prices, {"AAA.KS": 0.5, "ZZZ.KS": 0.5}, None, 1000)


def test_custom_backtest_rejects_weights_with_no_available_ticker(prices):
    with pytest.raises(ValidationError):
        cb.backtest_custom_portfolio(prices, {"ZZZ.KS": 1.0}, None, 1000)


def test_custom_backtest_validates_weights_first(prices):
    with pytest.raises(ValidationError, match="음수"):
        cb.backtest_custom_portfolio(prices, {"AAA.KS": 1.5, "BBB.KS": -0.5}, None, 1000)
