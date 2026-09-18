import yfinance as yf
import pandas as pd
import numpy as np
from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices

def get_stock_data(tickers, start_date, end_date):
    """
    주어진 티커 리스트에 대한 주가 데이터를 가져옵니다.
    """
    data = yf.download(tickers, start=start_date, end=end_date)['Close']
    if isinstance(data, pd.Series):
        data = data.to_frame()
    return data

# DC형 퇴직연금 위험자산 70% 한도 준수: 안전자산(채권형, 주식 0%) 30% + 위험자산 70%
DEFAULT_TARGET_WEIGHTS = {
    "273130.KS": 0.30,  # KODEX 종합채권(AA-이상)액티브 - 안전자산
    "411060.KS": 0.07,  # ACE KRX 금현물 - 위험자산
    "360750.KS": 0.25,  # TIGER 미국S&P500 - 위험자산
    "284430.KS": 0.13,  # KODEX 200미국채혼합50 - 위험자산
    "441640.KS": 0.13,  # KODEX 미국배당커버드콜액티브 - 위험자산
    "458730.KS": 0.12,  # TIGER 미국배당다우존스 - 위험자산
}

def target_weight_portfolio(tickers):
    """
    DEFAULT_TARGET_WEIGHTS에 정의된 목표 비중을 반환합니다.
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
    """
    if method == 'target_weight':
        return target_weight_portfolio(list(data.columns))

    # 기대 수익률 및 리스크 모델 계산
    mu = expected_returns.mean_historical_return(data)
    S = risk_models.sample_cov(data)

    # 효율적 투자선(Efficient Frontier) 설정
    ef = EfficientFrontier(mu, S)

    if method == 'max_sharpe':
        weights = ef.max_sharpe()
    elif method == 'min_volatility':
        weights = ef.min_volatility()
    else:
        # 기본값: 동일 가중치
        n = len(data.columns)
        weights = {ticker: 1.0/n for ticker in data.columns}
        return weights

    cleaned_weights = ef.clean_weights()
    return cleaned_weights

def get_discrete_allocation(weights, latest_prices, total_portfolio_value=10000):
    """
    가중치를 바탕으로 실제 구매 가능한 주식 수를 계산합니다.
    """
    da = DiscreteAllocation(weights, latest_prices, total_portfolio_value=total_portfolio_value)
    allocation, leftover = da.greedy_portfolio()
    return allocation, leftover

if __name__ == "__main__":
    # 테스트 코드
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    data = get_stock_data(tickers, "2023-01-01", "2023-12-31")
    weights = optimize_portfolio(data, method='max_sharpe')
    print("Optimized Weights:", weights)
