import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from rebalance_engine import backtest_rebalancing, calculate_metrics  # noqa: F401 (calculate_metrics는 앱에서 cb.calculate_metrics로 사용)

def get_stock_data(tickers, start_date, end_date):
    """
    주어진 티커 리스트에 대한 주가 데이터를 가져옵니다.
    """
    data = yf.download(tickers, start=start_date, end=end_date)['Close']
    if isinstance(data, pd.Series):
        data = data.to_frame()
    return data

def backtest_custom_portfolio(data, weights, rebalance_freq=None, initial_capital=10000):
    """
    사용자 정의 가중치로 백테스트를 수행합니다.
    
    Parameters:
    - data: 주가 데이터 (DataFrame)
    - weights: 포트폴리오 가중치 (dict: {ticker: weight})
    - rebalance_freq: 리밸런싱 주기 ('M', 'Q', 'Y', None)
    - initial_capital: 초기 자본
    
    Returns:
    - history_df: 포트폴리오 가치 시계열 데이터
    """
    # 데이터에 없는 티커는 제외하고, 남은 가중치의 합이 1이 되도록 정규화
    available = {ticker: w for ticker, w in weights.items() if ticker in data.columns}
    total_weight = sum(available.values())
    normalized_weights = {ticker: available.get(ticker, 0) / total_weight for ticker in data.columns}

    return backtest_rebalancing(data, normalized_weights, rebalance_freq, initial_capital)

def get_current_prices(tickers):
    """
    현재 주가를 가져옵니다.
    """
    data = yf.download(tickers, period='1d')['Close']
    if isinstance(data, pd.Series):
        return {tickers[0]: data.iloc[-1]}
    return data.iloc[-1].to_dict()

if __name__ == "__main__":
    # 테스트
    tickers = ["AAPL", "MSFT", "GOOGL"]
    weights = {"AAPL": 0.5, "MSFT": 0.3, "GOOGL": 0.2}
    
    data = get_stock_data(tickers, "2023-01-01", "2024-01-01")
    history = backtest_custom_portfolio(data, weights, rebalance_freq='M', initial_capital=10000)
    metrics = calculate_metrics(history)
    
    print("Metrics:", metrics)
    print("Final Portfolio Value:", history['Portfolio Value'].iloc[-1])
