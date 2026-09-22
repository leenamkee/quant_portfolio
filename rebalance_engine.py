import pandas as pd
import numpy as np

from errors import ValidationError
from validation import validate_capital, validate_frequency, validate_prices_frame, validate_weights

def get_rebalance_dates(index, rebalance_freq):
    """
    각 기간(월/분기/연)의 마지막 실제 거래일을 반환합니다.
    resample().last().index는 달력상 기간 말일이라 휴장일이면 거래일과 일치하지 않는다.
    """
    if not rebalance_freq:
        return pd.DatetimeIndex([])
    periods = index.to_period(rebalance_freq)
    return pd.DatetimeIndex(index.to_series().groupby(periods).max().values)

def backtest_rebalancing(data, initial_weights, rebalance_freq='M', initial_capital=10000):
    """
    리밸런싱을 포함한 백테스트를 수행합니다.
    rebalance_freq: 'M' (월간), 'Q' (분기), 'Y' (연간), None (리밸런싱 없음)
    입력이 올바르지 않으면 ValidationError를 발생시킵니다.
    """
    validate_frequency(rebalance_freq)
    validate_capital(initial_capital)
    validate_prices_frame(data)
    missing = [str(t) for t in data.columns if t not in initial_weights]
    if missing:
        raise ValidationError(f"비중이 지정되지 않은 종목이 있습니다: {', '.join(missing)}")
    weights = validate_weights({t: initial_weights[t] for t in data.columns})

    returns = data.pct_change().dropna()
    if returns.empty:
        raise ValidationError("수익률을 계산할 수 있는 거래일이 부족합니다. 종목들의 가격이 겹치는 거래일이 최소 2일 필요합니다.")

    current_weights = np.array([weights[ticker] for ticker in data.columns])
    # 비중 합이 1이 아니면 리밸런싱할 때마다 자산이 줄거나 늘어나므로 정규화한다
    current_weights = current_weights / current_weights.sum()

    portfolio_history = []
    dates = returns.index

    # 리밸런싱 날짜 설정
    rebalance_dates = get_rebalance_dates(data.index, rebalance_freq)

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
    if history_df is None or len(history_df) < 2:
        raise ValidationError("성과 지표를 계산하려면 포트폴리오 가치가 최소 2일치 필요합니다(가격 데이터 최소 3거래일).")
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
