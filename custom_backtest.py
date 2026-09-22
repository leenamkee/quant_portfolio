from errors import ValidationError
from portfolio_engine import get_stock_data  # noqa: F401 (앱에서 cb.get_stock_data로 사용)
from rebalance_engine import backtest_rebalancing, calculate_metrics  # noqa: F401 (calculate_metrics는 앱에서 cb.calculate_metrics로 사용)
from validation import validate_weights


def backtest_custom_portfolio(data, weights, rebalance_freq=None, initial_capital=10000):
    """
    사용자 정의 가중치로 백테스트를 수행합니다.

    Parameters:
    - data: 주가 데이터 (DataFrame)
    - weights: 포트폴리오 가중치 (dict: {ticker: weight}), 합이 1이 아니어도 비율에 맞춰 정규화
    - rebalance_freq: 리밸런싱 주기 ('M', 'Q', 'Y', None)
    - initial_capital: 초기 자본

    Returns:
    - history_df: 포트폴리오 가치 시계열 데이터

    비중이 있는 종목의 가격 데이터를 받지 못했으면 다른 구성으로 조용히 계산하지 않고 ValidationError를 발생시킵니다.
    """
    weights = validate_weights(weights)
    missing = [t for t, w in weights.items() if w > 0 and t not in data.columns]
    if missing:
        raise ValidationError(f"가격 데이터를 받지 못한 종목이 있습니다: {', '.join(missing)}. 티커를 확인하세요.")

    total_weight = sum(weights.values())
    normalized_weights = {ticker: weights.get(ticker, 0) / total_weight for ticker in data.columns}
    return backtest_rebalancing(data, normalized_weights, rebalance_freq, initial_capital)
