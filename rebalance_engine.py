import pandas as pd
import numpy as np

def backtest_rebalancing(data, initial_weights, rebalance_freq='M', initial_capital=10000):
    """
    리밸런싱을 포함한 백테스트를 수행합니다.
    rebalance_freq: 'M' (월간), 'Q' (분기), 'Y' (연간), None (리밸런싱 없음)
    """
    returns = data.pct_change().dropna()
    portfolio_value = initial_capital
    current_weights = np.array([initial_weights[ticker] for ticker in data.columns])
    
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
