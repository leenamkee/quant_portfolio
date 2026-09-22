import datetime as dt
import math

import pandas as pd

from errors import MarketDataError, ValidationError

REBALANCE_FREQUENCIES = (None, "M", "Q", "Y")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_weights(weights, label="비중"):
    """티커별 비중이 유한한 0 이상의 수이고 합계가 0보다 큰지 검사한다. 비중을 float로 바꿔 돌려준다."""
    if not weights:
        raise ValidationError(f"{label}이(가) 비어 있습니다.")
    cleaned = {}
    for ticker, weight in weights.items():
        try:
            number = float(weight)
        except (TypeError, ValueError):
            raise ValidationError(f"{ticker}의 {label}이(가) 숫자가 아닙니다: {weight!r}") from None
        if not _is_number(number):
            raise ValidationError(f"{ticker}의 {label}이(가) 숫자가 아닙니다: {weight!r}")
        if number < 0:
            raise ValidationError(f"{ticker}의 {label}이(가) 음수입니다({number:g}). 공매도는 지원하지 않습니다.")
        cleaned[ticker] = number
    if sum(cleaned.values()) <= 0:
        raise ValidationError(f"{label} 합계가 0입니다. 0보다 큰 {label}을(를) 입력하세요.")
    return cleaned


def validate_holdings(holdings):
    """보유 수량이 0 이상의 수인지 검사한다."""
    cleaned = {}
    for ticker, shares in (holdings or {}).items():
        if not _is_number(shares) or shares < 0:
            raise ValidationError(f"{ticker}의 보유 수량이 올바르지 않습니다: {shares!r} (0 이상의 수여야 합니다)")
        cleaned[ticker] = shares
    return cleaned


def validate_capital(capital):
    if not _is_number(capital) or capital <= 0:
        raise ValidationError(f"초기 자본은 0보다 커야 합니다: {capital!r}")
    return capital


def validate_frequency(freq):
    if freq not in REBALANCE_FREQUENCIES:
        raise ValidationError(f"리밸런싱 주기는 None, 'M', 'Q', 'Y' 중 하나여야 합니다: {freq!r}")
    return freq


def validate_prices_frame(data):
    """가격 DataFrame이 비어 있지 않고, 전부 결측인 종목이 없는지 검사한다."""
    if data is None or not isinstance(data, pd.DataFrame) or data.empty or data.shape[1] == 0:
        raise ValidationError("가격 데이터가 비어 있습니다. 티커와 기간을 확인하세요.")
    all_missing = [str(c) for c in data.columns if data[c].isna().all()]
    if all_missing:
        raise ValidationError(f"가격 데이터가 전혀 없는 종목이 있습니다: {', '.join(all_missing)}")
    return data


def validate_dates(start, end, today=None):
    """
    시작일·종료일을 검사하고 (시작일, 종료일 다음 날)을 돌려준다.
    yfinance의 종료일은 그 날을 포함하지 않으므로, 사용자가 고른 종료일이 결과에 들어가도록 하루를 더한다.
    서버(UTC)와 사용자(KST)의 날짜가 하루 어긋날 수 있어, 오늘보다 이틀 이상 뒤일 때만 미래 날짜로 본다.
    """
    try:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    except (TypeError, ValueError):
        raise ValidationError(f"날짜를 해석할 수 없습니다: {start!r}, {end!r}") from None
    if pd.isna(start_ts) or pd.isna(end_ts):
        raise ValidationError("시작일과 종료일을 모두 입력하세요.")
    start_ts, end_ts = start_ts.normalize(), end_ts.normalize()
    if start_ts > end_ts:
        raise ValidationError(f"시작일({start_ts:%Y-%m-%d})이 종료일({end_ts:%Y-%m-%d})보다 늦습니다.")
    today_ts = pd.Timestamp(today or dt.date.today()).normalize()
    if end_ts > today_ts + pd.Timedelta(days=1):
        raise ValidationError(f"종료일({end_ts:%Y-%m-%d})이 오늘 이후입니다.")
    return start_ts, end_ts + pd.Timedelta(days=1)


def extract_close(raw, tickers):
    """yfinance.download 결과에서 종가 표를 꺼낸다. 비었거나 종가가 없으면 MarketDataError."""
    try:
        data = raw["Close"]
    except (KeyError, TypeError):
        raise MarketDataError("시세 조회 결과가 비어 있습니다. 티커와 기간을 확인하세요.") from None
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0])
    if data is None or data.empty:
        raise MarketDataError("시세 조회 결과가 비어 있습니다. 티커와 기간을 확인하세요.")
    return data
