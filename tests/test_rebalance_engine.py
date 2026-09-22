import numpy as np
import pandas as pd
import pytest

from errors import ValidationError
import rebalance_engine as engine


def make_prices(values, start="2024-01-01"):
    length = len(next(iter(values.values())))
    return pd.DataFrame(values, index=pd.bdate_range(start, periods=length), dtype=float)


# ---------- 리밸런싱 날짜 ----------

@pytest.mark.parametrize("freq,expected", [("M", 12), ("Q", 4), ("Y", 1)])
def test_rebalance_dates_are_last_trading_day_of_each_period(freq, expected):
    idx = pd.bdate_range("2024-01-01", "2024-12-31")
    dates = engine.get_rebalance_dates(idx, freq)
    assert len(dates) == expected
    assert all(d in idx for d in dates)
    period_last = idx.to_series().groupby(idx.to_period(freq)).max()
    assert list(dates) == list(period_last)


def test_rebalance_date_skips_weekend_month_end():
    idx = pd.bdate_range("2024-11-01", "2024-11-30")  # 11/30은 토요일
    assert engine.get_rebalance_dates(idx, "M")[0] == pd.Timestamp("2024-11-29")


def test_no_rebalance_dates_without_frequency():
    idx = pd.bdate_range("2024-01-01", periods=10)
    assert len(engine.get_rebalance_dates(idx, None)) == 0


# ---------- 백테스트 (손계산) ----------

def test_backtest_matches_hand_calculation_without_rebalance():
    data = make_prices({"A": [100, 110, 121, 121], "B": [100, 100, 100, 100]})
    history = engine.backtest_rebalancing(data, {"A": 0.5, "B": 0.5}, None, 1000)
    # 첫 행은 시작일의 초기 자본(A1): 수익률은 그다음 거래일부터 반영된다
    assert list(history["Portfolio Value"].round(6)) == [1000.0, 1050.0, 1105.0, 1105.0]
    assert list(history.index) == list(data.index)


def rebalance_case():
    # 1/31에 A가 두 배가 되고 2/2에 A가 10% 오른다. 1/31(월말)에 리밸런싱하면 2/2 결과가 달라진다.
    return make_prices({"A": [100, 100, 200, 200, 220], "B": [100, 100, 100, 100, 100]}, start="2024-01-29")


def test_monthly_rebalance_restores_target_weights_on_month_end():
    history = engine.backtest_rebalancing(rebalance_case(), {"A": 0.5, "B": 0.5}, None, 1000)
    assert list(history["Portfolio Value"].round(6)) == [1000.0, 1000.0, 1500.0, 1500.0, 1600.0]
    history = engine.backtest_rebalancing(rebalance_case(), {"A": 0.5, "B": 0.5}, "M", 1000)
    assert list(history["Portfolio Value"].round(6)) == [1000.0, 1000.0, 1500.0, 1500.0, 1575.0]


def test_weights_not_summing_to_one_are_normalized():
    a = engine.backtest_rebalancing(rebalance_case(), {"A": 0.35, "B": 0.35}, "M", 1000)
    b = engine.backtest_rebalancing(rebalance_case(), {"A": 0.5, "B": 0.5}, "M", 1000)
    assert np.allclose(a["Portfolio Value"], b["Portfolio Value"])


def test_backtest_runs_on_synthetic_prices(prices):
    weights = {c: 0.25 for c in prices.columns}
    history = engine.backtest_rebalancing(prices, weights, "Q", 10_000_000)
    assert len(history) == len(prices)  # 첫 행은 시작일의 초기 자본(A1)
    assert history["Portfolio Value"].iloc[0] == 10_000_000
    assert history["Portfolio Value"].notna().all()


# ---------- 성과 지표 ----------

def test_max_drawdown_from_values():
    history = pd.DataFrame({"Portfolio Value": [100, 110, 99, 120]}, index=pd.bdate_range("2024-01-01", periods=4))
    assert engine.calculate_metrics(history)["Max Drawdown"] == pytest.approx(-0.1)


def constant_growth_history():
    values = [100 * 1.01 ** n for n in range(6)]
    return pd.DataFrame({"Portfolio Value": values}, index=pd.bdate_range("2024-01-01", periods=6))


def test_metrics_for_constant_growth_have_zero_volatility():
    metrics = engine.calculate_metrics(constant_growth_history())
    assert metrics["Annualized Volatility"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["Total Return"] == pytest.approx(1.01 ** 5 - 1)


def test_sharpe_is_undefined_when_volatility_is_numerically_zero():
    # 매일 똑같은 비율로만 오르면 변동성이 부동소수 오차 수준(~1e-17)이라 그대로 나누면 샤프가 무의미하게
    # 커진다(예: 2.8e15). VOLATILITY_EPSILON 미만이면 정의되지 않음(NaN)으로 처리한다.
    sharpe = engine.calculate_metrics(constant_growth_history())["Sharpe Ratio"]
    assert np.isnan(sharpe)


def test_sharpe_is_computed_normally_above_the_epsilon():
    history = pd.DataFrame({"Portfolio Value": [100, 105, 98, 110, 103, 115]},
                            index=pd.bdate_range("2024-01-01", periods=6))
    metrics = engine.calculate_metrics(history)
    assert metrics["Annualized Volatility"] > 1e-3
    assert not np.isnan(metrics["Sharpe Ratio"])
    assert metrics["Sharpe Ratio"] == pytest.approx(metrics["Annualized Return"] / metrics["Annualized Volatility"])


def test_total_return_includes_first_day_return():
    data = make_prices({"A": [100, 110, 110, 121]})  # 실제 총수익률 +21%
    history = engine.backtest_rebalancing(data, {"A": 1.0}, None, 1000)
    assert engine.calculate_metrics(history)["Total Return"] == pytest.approx(0.21)


def test_annualized_return_uses_days_with_an_actual_return_applied():
    # 첫 행(시작일)은 수익률이 없는 초기 자본이라 연환산의 분모(적용 일수)에서 제외한다
    history = pd.DataFrame({"Portfolio Value": [100.0, 110.0]}, index=pd.bdate_range("2024-01-01", periods=2))
    metrics = engine.calculate_metrics(history)
    assert metrics["Total Return"] == pytest.approx(0.10)
    assert metrics["Annualized Return"] == pytest.approx(1.10 ** 252 - 1)


# ---------- 결측·정렬 정책 (A2, §9-3 확정: 공통 관측 구간, 전방 채움 없음) ----------

def test_backtest_skips_days_with_missing_prices_without_forward_fill(gap_prices):
    history = engine.backtest_rebalancing(gap_prices, {"A": 0.5, "B": 0.5}, None, 1000)
    # 공통 구간은 B의 첫 유효일(idx2)부터 시작하고(A1: 그날의 초기 자본이 첫 행), idx3은 B 가격이
    # 없어 제외되어 idx2→idx4의 수익률이 idx4에 반영된다
    assert list(history.index) == [gap_prices.index[2], gap_prices.index[4], gap_prices.index[5]]
    assert history["Portfolio Value"].iloc[0] == 1000
    assert history["Portfolio Value"].iloc[1] == pytest.approx(500 * 104 / 102 + 500 * 52 / 50)


def test_backtest_starts_at_the_latest_first_valid_date():
    data = make_prices({"A": [100, 101, 102, 103], "B": [np.nan, np.nan, 50, 55]})
    history = engine.backtest_rebalancing(data, {"A": 0.5, "B": 0.5}, None, 1000)
    assert list(history.index) == [data.index[2], data.index[3]]
    assert history["Portfolio Value"].iloc[0] == 1000
    assert history["Portfolio Value"].iloc[1] == pytest.approx(500 * 103 / 102 + 500 * 55 / 50)


# ---------- 입력 검증 (A8, 단계 1) ----------

def small_prices():
    return make_prices({"A": [100, 101, 102], "B": [50, 51, 52]})


def test_zero_weight_sum_is_rejected():
    with pytest.raises(ValidationError, match="합계가 0"):
        engine.backtest_rebalancing(small_prices(), {"A": 0, "B": 0}, "M", 1000)


def test_negative_weight_is_rejected():
    with pytest.raises(ValidationError, match="음수"):
        engine.backtest_rebalancing(small_prices(), {"A": 1.5, "B": -0.5}, None, 1000)


def test_nan_weight_is_rejected():
    with pytest.raises(ValidationError, match="숫자가 아닙니다"):
        engine.backtest_rebalancing(small_prices(), {"A": float("nan"), "B": 1.0}, None, 1000)


def test_empty_price_data_is_rejected_with_clear_error():
    with pytest.raises(ValidationError, match="비어"):
        engine.backtest_rebalancing(pd.DataFrame(), {}, "M", 1000)


def test_single_trading_day_is_rejected_with_clear_error():
    with pytest.raises(ValidationError, match="거래일이 부족"):
        engine.backtest_rebalancing(make_prices({"A": [100.0]}), {"A": 1.0}, None, 1000)


def test_ticker_without_a_weight_is_rejected_by_name():
    with pytest.raises(ValidationError, match="B"):
        engine.backtest_rebalancing(small_prices(), {"A": 1.0}, None, 1000)


def test_extra_weights_for_tickers_not_in_data_are_ignored():
    history = engine.backtest_rebalancing(small_prices(), {"A": 0.5, "B": 0.5, "ZZZ": 0.5}, None, 1000)
    assert len(history) == 3  # 첫 행은 시작일의 초기 자본(A1)


@pytest.mark.parametrize("capital", [0, -100, float("nan")])
def test_non_positive_initial_capital_is_rejected(capital):
    with pytest.raises(ValidationError, match="초기 자본"):
        engine.backtest_rebalancing(small_prices(), {"A": 0.5, "B": 0.5}, None, capital)


def test_unknown_rebalance_frequency_is_rejected():
    with pytest.raises(ValidationError, match="리밸런싱 주기"):
        engine.backtest_rebalancing(small_prices(), {"A": 0.5, "B": 0.5}, "W", 1000)


def test_metrics_need_at_least_two_days_of_values():
    one_day = pd.DataFrame({"Portfolio Value": [100.0]}, index=pd.bdate_range("2024-01-01", periods=1))
    with pytest.raises(ValidationError, match="최소 2일"):
        engine.calculate_metrics(one_day)
    with pytest.raises(ValidationError):
        engine.calculate_metrics(None)
