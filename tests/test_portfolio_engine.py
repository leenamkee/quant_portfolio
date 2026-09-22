import numpy as np
import pytest

import config
import portfolio_engine as pe
from errors import ValidationError


# ---------- 도메인 규칙: DC형 퇴직연금 위험자산 70% ----------

SAFE_TICKER = "273130.KS"  # KODEX 종합채권(AA-이상)액티브: 주식 0%


def test_default_target_weights_sum_to_one():
    assert sum(config.DEFAULT_TARGET_WEIGHTS.values()) == pytest.approx(1.0)


def test_default_portfolio_respects_dc_risky_asset_cap():
    risky = sum(w for t, w in config.DEFAULT_TARGET_WEIGHTS.items() if t != SAFE_TICKER)
    assert risky <= 0.70 + 1e-9
    assert config.DEFAULT_TARGET_WEIGHTS[SAFE_TICKER] >= 0.30 - 1e-9


def test_every_default_ticker_has_a_name():
    assert set(config.DEFAULT_TARGET_WEIGHTS) <= set(config.TICKER_NAMES)
    assert all(t.endswith(".KS") for t in config.DEFAULT_TARGET_WEIGHTS)


# ---------- target_weight ----------

def test_target_weight_returns_defaults_for_known_tickers():
    weights = pe.target_weight_portfolio(list(config.DEFAULT_TARGET_WEIGHTS))
    assert weights == pytest.approx(config.DEFAULT_TARGET_WEIGHTS)


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
    assert weights == pytest.approx(config.DEFAULT_TARGET_WEIGHTS)


def test_optimize_uses_the_common_observation_window(prices):
    data = prices.copy()
    data.iloc[:30, 0] = np.nan  # 첫 종목이 30거래일 늦게 시작
    weights = pe.optimize_portfolio(data, method="max_sharpe")
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_discrete_allocation_never_exceeds_capital(prices):
    weights = {c: 0.25 for c in prices.columns}
    latest = prices.iloc[-1]
    allocation, leftover = pe.get_discrete_allocation(weights, latest, 1_000_000)
    spent = sum(latest[t] * n for t, n in allocation.items())
    assert leftover >= 0 and spent + leftover == pytest.approx(1_000_000)
