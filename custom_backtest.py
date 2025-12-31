import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

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
    returns = data.pct_change().dropna()
    
    # 가중치 정규화 (합이 1이 되도록)
    total_weight = sum(weights.values())
    normalized_weights = {ticker: w / total_weight for ticker, w in weights.items()}
    
    # 데이터에 없는 티커 제거
    normalized_weights = {ticker: w for ticker, w in normalized_weights.items() if ticker in data.columns}
    
    # 가중치 재정규화
    total_weight = sum(normalized_weights.values())
    normalized_weights = {ticker: w / total_weight for ticker, w in normalized_weights.items()}
    
    portfolio_value = initial_capital
    current_weights = np.array([normalized_weights.get(ticker, 0) for ticker in data.columns])
    
    portfolio_history = []
    dates = returns.index
    
    # 리밸런싱 날짜 설정
    if rebalance_freq:
        rebalance_dates = data.resample(rebalance_freq).last().index
    else:
        rebalance_dates = []
    
    current_portfolio_value = initial_capital
    
    # 각 자산별 보유 금액
    asset_values = current_portfolio_value * current_weights
    
    for date in dates:
        # 자산 가치 업데이트 (일일 수익률 반영)
        daily_ret = returns.loc[date].values
        asset_values = asset_values * (1 + daily_ret)
        current_portfolio_value = np.sum(asset_values)
        
        # 리밸런싱 수행
        if date in rebalance_dates:
            asset_values = current_portfolio_value * current_weights
            
        portfolio_history.append({
            'Date': date,
            'Portfolio Value': current_portfolio_value
        })
    
    history_df = pd.DataFrame(portfolio_history).set_index('Date')
    return history_df

def calculate_metrics(history_df):
    """
    포트폴리오 성과 지표를 계산합니다.
    """
    df = history_df.copy()
    df['Daily Return'] = df['Portfolio Value'].pct_change()
    
    total_return = (df['Portfolio Value'].iloc[-1] / df['Portfolio Value'].iloc[0]) - 1
    annualized_return = (1 + total_return) ** (252 / len(df)) - 1
    annualized_vol = df['Daily Return'].std() * np.sqrt(252)
    sharpe_ratio = annualized_return / annualized_vol if annualized_vol != 0 else 0
    
    # MDD 계산
    df['Cumulative Max'] = df['Portfolio Value'].cummax()
    df['Drawdown'] = (df['Portfolio Value'] - df['Cumulative Max']) / df['Cumulative Max']
    mdd = df['Drawdown'].min()
    
    return {
        'Total Return': total_return,
        'Annualized Return': annualized_return,
        'Annualized Volatility': annualized_vol,
        'Sharpe Ratio': sharpe_ratio,
        'Max Drawdown': mdd
    }

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
