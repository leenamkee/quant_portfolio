import pandas as pd
import numpy as np
import yfinance as yf

def get_current_prices(tickers):
    """
    현재 주가를 가져옵니다.
    """
    try:
        data = yf.download(tickers, period='1mo', progress=False)['Close']
        # data = pd.DataFrame(data.iloc[-2])
        # data = data.iloc[-2,0:4]
        data = data.iloc[[-2]]
        if isinstance(data, pd.Series):
            return {tickers[0]: data.iloc[-1]}
        return data.iloc[-1].to_dict()
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}

def calculate_rebalancing_guide(current_holdings, target_weights, current_prices):
    """
    현재 보유 수량과 목표 가중치를 기반으로 리밸런싱 가이드를 생성합니다.
    
    Parameters:
    - current_holdings: 현재 보유 수량 (dict: {ticker: shares})
    - target_weights: 목표 가중치 (dict: {ticker: weight})
    - current_prices: 현재 주가 (dict: {ticker: price})
    
    Returns:
    - rebalancing_df: 리밸런싱 가이드 DataFrame
    """
    # 현재 포트폴리오 가치 계산
    current_values = {}
    total_value = 0
    
    for ticker, shares in current_holdings.items():
        price = current_prices.get(ticker, 0)
        value = shares * price
        current_values[ticker] = value
        total_value += value
    
    # 목표 가중치 정규화
    total_weight = sum(target_weights.values())
    normalized_weights = {ticker: w / total_weight for ticker, w in target_weights.items()}
    
    # 리밸런싱 계산
    rebalancing_data = []
    total_cash_needed = 0
    
    for ticker in set(list(current_holdings.keys()) + list(target_weights.keys())):
        current_shares = current_holdings.get(ticker, 0)
        current_price = current_prices.get(ticker, 0)
        current_value = current_values.get(ticker, 0)
        
        target_weight = normalized_weights.get(ticker, 0)
        target_value = total_value * target_weight
        
        # 필요한 변화량
        value_diff = target_value - current_value
        shares_diff = value_diff / current_price if current_price > 0 else 0
        
        target_shares = current_shares + shares_diff
        
        # 현재 가중치
        current_weight = current_value / total_value if total_value > 0 else 0
        
        rebalancing_data.append({
            'Ticker': ticker,
            'Current Shares': int(current_shares),
            'Current Price': f"${current_price:.2f}",
            'Current Value': f"${current_value:.2f}",
            'Current Weight': f"{current_weight:.2%}",
            'Target Weight': f"{target_weight:.2%}",
            'Target Shares': int(np.round(target_shares)),
            'Shares to Buy/Sell': int(np.round(shares_diff)),
            'Transaction Value': f"${abs(value_diff):.2f}"
        })
        
        if shares_diff > 0:
            total_cash_needed += value_diff
    
    rebalancing_df = pd.DataFrame(rebalancing_data)
    
    return rebalancing_df, total_value, total_cash_needed

def calculate_rebalancing_cost(current_holdings, target_weights, current_prices, transaction_cost_pct=0.001):
    """
    리밸런싱에 필요한 거래 비용을 계산합니다.
    
    Parameters:
    - transaction_cost_pct: 거래 수수료 비율 (기본값 0.1%)
    
    Returns:
    - total_cost: 총 거래 비용
    """
    current_values = {}
    total_value = 0
    
    for ticker, shares in current_holdings.items():
        price = current_prices.get(ticker, 0)
        value = shares * price
        current_values[ticker] = value
        total_value += value
    
    # 목표 가중치 정규화
    total_weight = sum(target_weights.values())
    normalized_weights = {ticker: w / total_weight for ticker, w in target_weights.items()}
    
    total_transaction_value = 0
    
    for ticker in set(list(current_holdings.keys()) + list(target_weights.keys())):
        current_value = current_values.get(ticker, 0)
        target_weight = normalized_weights.get(ticker, 0)
        target_value = total_value * target_weight
        
        value_diff = abs(target_value - current_value)
        total_transaction_value += value_diff
    
    # 거래 비용은 양방향 거래의 절반만 계산 (매도/매수 한 번씩)
    total_cost = (total_transaction_value / 2) * transaction_cost_pct
    
    return total_cost

def get_rebalancing_summary(current_holdings, target_weights, current_prices):
    """
    리밸런싱 요약 정보를 생성합니다.
    """
    rebalancing_df, total_value, cash_needed = calculate_rebalancing_guide(
        current_holdings, target_weights, current_prices
    )
    
    # 매수/매도 분류
    buy_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] > 0]
    sell_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] < 0]
    
    summary = {
        'Total Portfolio Value': total_value,
        'Cash Needed for Buying': cash_needed,
        'Number of Buys': len(buy_actions),
        'Number of Sells': len(sell_actions),
        'Rebalancing Guide': rebalancing_df
    }
    
    return summary

if __name__ == "__main__":
    # 테스트
    # current_holdings = {"AAPL": 10, "MSFT": 5, "GOOGL": 3}
    # target_weights = {"AAPL": 0.5, "MSFT": 0.3, "GOOGL": 0.2}
    current_holdings = {"360750.KS": 14, "439870.KS": 16, "411060.KS": 21, "445680.KS": 33}
    target_weights = {"360750.KS": 0.25, "439870.KS": 0.25, "411060.KS": 0.25, "445680.KS": 0.25}
    
    tickers = list(current_holdings.keys())
    current_prices = get_current_prices(tickers)
    
    print("Current Prices:", current_prices)
    
    rebalancing_df, total_value, cash_needed = calculate_rebalancing_guide(
        current_holdings, target_weights, current_prices
    )
    
    print("\nRebalancing Guide:")
    print(rebalancing_df)
    print(f"\nTotal Portfolio Value: ${total_value:.2f}")
    print(f"Cash Needed: ${cash_needed:.2f}")
