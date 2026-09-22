import pandas as pd
import numpy as np

from alignment import align_prices, daily_returns
from config import TRADING_DAYS_PER_YEAR, VOLATILITY_EPSILON
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

    # 공통 관측 구간만 사용하고 가격이 없는 날은 제외한다(앞 값으로 채우지 않음). 2거래일 미만이면 ValidationError
    data = align_prices(data).prices
    returns = daily_returns(data)

    current_weights = np.array([weights[ticker] for ticker in data.columns])
    # 비중 합이 1이 아니면 리밸런싱할 때마다 자산이 줄거나 늘어나므로 정규화한다
    current_weights = current_weights / current_weights.sum()

    # 시작일의 초기 자본을 시계열의 첫 점으로 남긴다(A1). 이렇게 해야 총수익률에 첫 거래일의 수익률이
    # 포함된다: 시작일=초기 자본, 그 다음 거래일부터 수익률을 반영한다.
    portfolio_history = [{'Date': data.index[0], 'Portfolio Value': initial_capital}]
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

def backtest_custom_portfolio(data, weights, rebalance_freq=None, initial_capital=10000):
    """
    사용자가 직접 정한 비중으로 백테스트를 수행합니다. backtest_rebalancing과 달리 비중이 data의 모든
    종목을 다루지 않아도 되고(누락분은 0으로 간주), 비중이 0보다 큰 종목의 가격을 못 받으면 다른 구성으로
    조용히 계산하지 않고 ValidationError를 발생시킵니다.
    """
    weights = validate_weights(weights)
    missing = [t for t, w in weights.items() if w > 0 and t not in data.columns]
    if missing:
        raise ValidationError(f"가격 데이터를 받지 못한 종목이 있습니다: {', '.join(missing)}. 티커를 확인하세요.")

    total_weight = sum(weights.values())
    normalized_weights = {ticker: weights.get(ticker, 0) / total_weight for ticker in data.columns}
    return backtest_rebalancing(data, normalized_weights, rebalance_freq, initial_capital)

def calculate_metrics(history_df):
    """
    포트폴리오 성과 지표를 계산합니다.
    """
    if history_df is None or len(history_df) < 2:
        raise ValidationError("성과 지표를 계산하려면 포트폴리오 가치가 최소 2일치 필요합니다(가격 데이터 최소 3거래일).")
    df = history_df.copy()
    df['Daily Return'] = df['Portfolio Value'].pct_change()

    total_return = (df['Portfolio Value'].iloc[-1] / df['Portfolio Value'].iloc[0]) - 1
    # 수익률이 적용된 거래일 수(시계열 첫 점은 초기 자본이라 수익률이 없음). calculate_metrics 진입 시
    # len(df) >= 2를 이미 보장하므로 이 값은 항상 1 이상이다.
    applied_days = len(df) - 1
    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / applied_days) - 1
    annualized_vol = df['Daily Return'].std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    # 변동성이 부동소수 오차 수준(예: 매일 똑같은 비율로만 오르는 포트폴리오)이면 나눗셈이 무의미하게
    # 커지므로(A3), 정의되지 않음(NaN)으로 처리한다.
    sharpe_ratio = annualized_return / annualized_vol if annualized_vol >= VOLATILITY_EPSILON else float('nan')

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
