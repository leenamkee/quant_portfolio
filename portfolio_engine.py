import yfinance as yf
import pandas as pd
from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.discrete_allocation import DiscreteAllocation

from errors import MarketDataError, ValidationError
from validation import extract_close, validate_dates


def clean_tickers(tickers):
    """공백 제거, 빈 값 제거, 중복 제거(입력 순서 유지)."""
    cleaned = list(dict.fromkeys(str(t).strip() for t in tickers if str(t).strip()))
    if not cleaned:
        raise ValidationError("티커를 입력하세요.")
    return cleaned


def get_stock_data(tickers, start_date, end_date):
    """
    주어진 티커 리스트에 대한 종가 데이터를 가져옵니다.
    종료일은 결과에 포함됩니다(yfinance의 종료일은 배타적이라 하루를 더해 요청).
    입력이 올바르지 않으면 ValidationError, 시세를 받지 못했으면 MarketDataError를 발생시킵니다.
    """
    tickers = clean_tickers(tickers)
    start, end_exclusive = validate_dates(start_date, end_date)
    try:
        raw = yf.download(tickers, start=start, end=end_exclusive)
    except Exception as e:
        raise MarketDataError(f"시세 조회에 실패했습니다: {e}") from e
    data = extract_close(raw, tickers)
    no_data = [t for t in tickers if t not in data.columns or data[t].isna().all()]
    if no_data:
        raise MarketDataError(f"가격 데이터를 받지 못한 종목이 있습니다: {', '.join(no_data)}. 티커를 확인하세요.")
    return data

TICKER_NAMES = {
    "273130.KS": "KODEX 종합채권(AA-이상)액티브",
    "284430.KS": "KODEX 200미국채혼합50",
    "360750.KS": "TIGER 미국S&P500",
    "411060.KS": "ACE KRX 금현물",
    "441640.KS": "KODEX 미국배당커버드콜액티브",
    "458730.KS": "TIGER 미국배당다우존스",
}

# DC형 퇴직연금 위험자산 70% 한도 준수: 안전자산(채권형, 주식 0%) 30% + 위험자산 70%
# 앱의 기본 티커/비중 입력값도 이 딕셔너리에서 만들어지므로 여기만 수정하면 된다.
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
