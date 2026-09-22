import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

from errors import MarketDataError, ValidationError
from validation import extract_close, validate_holdings, validate_weights


@dataclass
class LatestPrices:
    """티커별 마지막 사용 가능한 거래일 종가와 그 기준일."""
    prices: dict = field(default_factory=dict)   # {ticker: 종가}
    as_of: dict = field(default_factory=dict)    # {ticker: 기준일(Timestamp)}
    missing: list = field(default_factory=list)  # 가격을 얻지 못한 티커

    def distinct_dates(self):
        return sorted({d.date() for d in self.as_of.values()})


def fetch_latest_prices(tickers):
    """
    티커별 마지막 유효 종가와 기준일을 가져옵니다.
    조회 자체가 실패하거나 결과가 비어 있으면 MarketDataError를 발생시킵니다.
    일부 티커만 가격이 없는 경우는 결과의 missing에 담아 돌려주므로 호출자가 필요 여부를 판단합니다.
    """
    tickers = list(dict.fromkeys(str(t).strip() for t in tickers if str(t).strip()))
    if not tickers:
        raise ValidationError("현재가를 조회할 티커가 없습니다.")
    try:
        raw = yf.download(tickers, period='1mo', progress=False)
    except Exception as e:
        raise MarketDataError(f"현재가 조회에 실패했습니다: {e}") from e
    data = extract_close(raw, tickers)

    result = LatestPrices()
    for ticker in tickers:
        valid = data[ticker].dropna() if ticker in data.columns else pd.Series(dtype=float)
        valid = valid[valid > 0]
        if valid.empty:
            result.missing.append(ticker)
            continue
        result.prices[ticker] = float(valid.iloc[-1])
        result.as_of[ticker] = valid.index[-1]
    return result


def get_current_prices(tickers):
    """마지막 사용 가능한 거래일 종가({ticker: 가격}). 하나도 얻지 못하면 MarketDataError를 발생시킵니다."""
    result = fetch_latest_prices(tickers)
    if not result.prices:
        raise MarketDataError(f"현재가를 얻지 못했습니다: {', '.join(result.missing)}")
    return result.prices


def _is_valid_price(price):
    return isinstance(price, (int, float, np.floating)) and not isinstance(price, bool) and math.isfinite(price) and price > 0


def _prepare(current_holdings, target_weights, current_prices):
    """
    입력을 검사하고 정리합니다. 보유 수량이나 목표 비중이 있는 종목의 가격이 없거나 올바르지 않으면
    다른 종목의 매매 안내를 왜곡하므로 계산하지 않고 ValidationError를 발생시킵니다.
    """
    holdings = validate_holdings(current_holdings)
    weights = validate_weights(target_weights, "목표 비중")
    needed = [t for t in dict.fromkeys(list(holdings) + list(weights)) if holdings.get(t, 0) > 0 or weights.get(t, 0) > 0]
    bad = [t for t in needed if not _is_valid_price(current_prices.get(t))]
    if bad:
        raise ValidationError(f"가격을 알 수 없는 종목이 있어 리밸런싱을 계산할 수 없습니다: {', '.join(bad)}")
    return holdings, weights


def calculate_rebalancing_guide(current_holdings, target_weights, current_prices):
    """
    현재 보유 수량과 목표 가중치를 기반으로 리밸런싱 가이드를 생성합니다.

    Parameters:
    - current_holdings: 현재 보유 수량 (dict: {ticker: shares})
    - target_weights: 목표 가중치 (dict: {ticker: weight}), 합이 1이 아니어도 비율에 맞춰 정규화
    - current_prices: 현재 주가 (dict: {ticker: price})

    Returns:
    - rebalancing_df: 리밸런싱 가이드 DataFrame

    입력이 올바르지 않거나 필요한 종목의 가격이 없으면 ValidationError를 발생시킵니다.
    """
    current_holdings, target_weights = _prepare(current_holdings, target_weights, current_prices)

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

    # set()은 순서가 매번 달라지므로, 입력한 순서를 유지하며 중복만 제거한다
    for ticker in dict.fromkeys(list(current_holdings.keys()) + list(target_weights.keys())):
        current_shares = current_holdings.get(ticker, 0)
        current_price = current_prices.get(ticker, 0)
        current_value = current_values.get(ticker, 0)

        target_weight = normalized_weights.get(ticker, 0)
        target_value = total_value * target_weight

        # 필요한 변화량 (보유도 목표도 없는 종목은 가격이 없어도 변화 0)
        value_diff = target_value - current_value
        shares_diff = value_diff / current_price if _is_valid_price(current_price) else 0

        target_shares = current_shares + shares_diff

        # 현재 가중치
        current_weight = current_value / total_value if total_value > 0 else 0

        rebalancing_data.append({
            'Ticker': ticker,
            'Current Shares': int(current_shares),
            'Current Price': f"{current_price:,.0f}원",
            'Current Value': f"{current_value:,.0f}원",
            'Current Weight': f"{current_weight:.2%}",
            'Target Weight': f"{target_weight:.2%}",
            'Target Shares': int(np.round(target_shares)),
            'Shares to Buy/Sell': int(np.round(shares_diff)),
            'Transaction Value': f"{abs(value_diff):,.0f}원"
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
    current_holdings, target_weights = _prepare(current_holdings, target_weights, current_prices)

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

    for ticker in dict.fromkeys(list(current_holdings.keys()) + list(target_weights.keys())):
        current_value = current_values.get(ticker, 0)
        target_weight = normalized_weights.get(ticker, 0)
        target_value = total_value * target_weight

        value_diff = abs(target_value - current_value)
        total_transaction_value += value_diff

    # 거래 비용은 양방향 거래의 절반만 계산 (매도/매수 한 번씩)
    total_cost = (total_transaction_value / 2) * transaction_cost_pct

    return total_cost
