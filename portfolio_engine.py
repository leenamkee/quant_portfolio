from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation

from alignment import align_prices
from config import DEFAULT_TARGET_WEIGHTS


def target_weight_portfolio(tickers):
    """
    config.DEFAULT_TARGET_WEIGHTS에 정의된 목표 비중을 반환합니다.
    입력 티커가 전부 정의되어 있지 않으면 동일 가중치로 대체합니다.
    """
    if tickers and all(t in DEFAULT_TARGET_WEIGHTS for t in tickers):
        total = sum(DEFAULT_TARGET_WEIGHTS[t] for t in tickers)
        return {t: DEFAULT_TARGET_WEIGHTS[t] / total for t in tickers}

    n = len(tickers)
    return {t: 1.0 / n for t in tickers}

def optimize_portfolio(data, method='max_sharpe'):
    """
    포트폴리오를 최적화하여 가중치를 반환합니다.
    통계를 쓰는 방법(max_sharpe, min_volatility)은 공통 관측 구간으로 맞춘 가격으로 계산합니다.
    """
    if method == 'target_weight':
        return target_weight_portfolio(list(data.columns))

    if method not in ('max_sharpe', 'min_volatility'):
        # 기본값: 동일 가중치
        n = len(data.columns)
        return {ticker: 1.0/n for ticker in data.columns}

    data = align_prices(data).prices

    # 기대 수익률 및 리스크 모델 계산
    mu = expected_returns.mean_historical_return(data)
    S = risk_models.sample_cov(data)

    # 효율적 투자선(Efficient Frontier) 설정
    ef = EfficientFrontier(mu, S)

    if method == 'max_sharpe':
        ef.max_sharpe()
    else:
        ef.min_volatility()

    cleaned_weights = ef.clean_weights()
    return cleaned_weights

def get_discrete_allocation(weights, latest_prices, total_portfolio_value=10000):
    """
    가중치를 바탕으로 실제 구매 가능한 주식 수를 계산합니다.
    """
    da = DiscreteAllocation(weights, latest_prices, total_portfolio_value=total_portfolio_value)
    allocation, leftover = da.greedy_portfolio()
    return allocation, leftover
