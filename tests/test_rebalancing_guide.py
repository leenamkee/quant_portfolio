import pytest

import rebalancing_guide as guide
from errors import ValidationError


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


# ---------- 추가 투자금 ----------

def test_extra_cash_is_added_to_the_allocation_target():
    # 현재 2,000원(A 10주 · B 10주, 각 100원) + 추가 1,000원 = 3,000원을 50:50으로 배분 → 각 1,500원
    df, total, cash = guide.calculate_rebalancing_guide(
        {"A": 10, "B": 10}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100}, extra_cash=1000)
    assert trades(df) == {"A": 5, "B": 5}
    assert total == 2000  # 보고되는 "포트폴리오 총 가치"는 추가 투자금을 뺀 현재 보유 가치
    assert cash == pytest.approx(1000)


def test_extra_cash_fills_underweight_tickers_before_forcing_a_sell():
    # 현재 A만 1,000원 보유, 목표는 50:50. 추가 1,000원을 더하면 총 2,000원 중 B가 1,000원 필요하고
    # 추가 투자금만으로 정확히 채워져 A를 매도할 필요가 없다.
    df, _, cash = guide.calculate_rebalancing_guide(
        {"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100}, extra_cash=1000)
    assert trades(df) == {"A": 0, "B": 10}
    assert cash == pytest.approx(1000)


def test_extra_cash_defaults_to_zero():
    with_default = guide.calculate_rebalancing_guide({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    explicit_zero = guide.calculate_rebalancing_guide({"A": 10, "B": 0}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100}, extra_cash=0)
    assert trades(with_default[0]) == trades(explicit_zero[0])


def test_negative_extra_cash_is_rejected():
    with pytest.raises(ValidationError, match="추가 투자금"):
        guide.calculate_rebalancing_guide({"A": 10}, {"A": 1.0}, {"A": 100}, extra_cash=-1)


def test_rebalancing_cost_grows_with_extra_cash():
    without = guide.calculate_rebalancing_cost({"A": 10, "B": 10}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100})
    with_extra = guide.calculate_rebalancing_cost({"A": 10, "B": 10}, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 100}, extra_cash=1000)
    assert with_extra > without


# ---------- 입력·가격 검증 (A5, A8, 단계 1) ----------

def test_missing_price_for_held_ticker_is_an_error_naming_the_ticker():
    with pytest.raises(ValidationError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100})


def test_missing_price_never_produces_a_wrong_sell_advice():
    # 예전에는 B를 0원으로 계산해 A를 5주 매도하라고 안내했다
    with pytest.raises(ValidationError):
        guide.calculate_rebalancing_guide({"A": 10, "B": 10}, {"A": 0.5, "B": 0.5}, {"A": 100})


@pytest.mark.parametrize("price", [0, -5, float("nan"), None, "100"])
def test_invalid_price_for_held_ticker_is_an_error(price):
    with pytest.raises(ValidationError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100, "TICKB": price})


def test_price_is_required_for_a_target_ticker_even_without_holdings():
    with pytest.raises(ValidationError, match="TICKB"):
        guide.calculate_rebalancing_guide({"TICKA": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100})


def test_ticker_with_no_holding_and_no_target_does_not_need_a_price():
    df, _, _ = guide.calculate_rebalancing_guide({"A": 10, "Z": 0}, {"A": 1.0, "Z": 0.0}, {"A": 100})
    assert trades(df) == {"A": 0, "Z": 0}


def test_zero_target_weight_sum_is_rejected_with_clear_error():
    with pytest.raises(ValidationError, match="목표 비중 합계가 0"):
        guide.calculate_rebalancing_guide({"A": 10}, {"A": 0}, {"A": 100})


def test_negative_holdings_and_weights_are_rejected():
    with pytest.raises(ValidationError, match="보유 수량"):
        guide.calculate_rebalancing_guide({"A": -1}, {"A": 1.0}, {"A": 100})
    with pytest.raises(ValidationError, match="음수"):
        guide.calculate_rebalancing_guide({"A": 1}, {"A": 1.5, "B": -0.5}, {"A": 100, "B": 100})


def test_cost_calculation_applies_the_same_validation():
    with pytest.raises(ValidationError, match="TICKB"):
        guide.calculate_rebalancing_cost({"TICKA": 10, "TICKB": 10}, {"TICKA": 0.5, "TICKB": 0.5}, {"TICKA": 100})
