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

def target_weight_portfolio(tickers, gold_ticker="411060.KS", sp500_ticker="360750.KS", gold_weight=0.10, sp500_weight=0.36):
    """
    금ETF(gold_weight)와 S&P500 ETF(sp500_weight)에 목표 비중을 지정하고,
    나머지 종목들은 남은 비중을 균등하게 나눠 갖습니다.
    """
    rest = [t for t in tickers if t not in (gold_ticker, sp500_ticker)]
    rest_weight = (1 - gold_weight - sp500_weight) / len(rest) if rest else 0

    weights = {}
    for t in tickers:
        if t == gold_ticker:
            weights[t] = gold_weight
        elif t == sp500_ticker:
            weights[t] = sp500_weight
        else:
            weights[t] = rest_weight
    return weights

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
