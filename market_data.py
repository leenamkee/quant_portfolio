"""시세 조회의 단일 진입점. 앱은 시세를 이 모듈로만 받는다.

- 종가 기준: 과거 구간은 종가 표, 현재가는 "마지막 사용 가능한 거래일 종가"와 기준일.
- 종료일은 결과에 포함된다(yfinance의 종료일이 배타적이라 하루를 더해 요청).
- 실패는 조용히 넘기지 않고 ValidationError / MarketDataError로 전달한다.
- 결과는 프로세스 안에서 TTL 캐시로 공유된다(오류는 캐시하지 않음). TTL은 config에 있다.
"""
import threading
import time
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from config import LATEST_PRICE_TTL_SECONDS, PRICE_HISTORY_TTL_SECONDS
from errors import MarketDataError, ValidationError
from validation import extract_close, validate_dates

MAX_CACHE_ENTRIES = 64

_cache = {}
_lock = threading.RLock()


def _now():
    return time.monotonic()


def _cache_get(key, ttl):
    with _lock:
        entry = _cache.get(key)
        if entry and _now() - entry[0] < ttl:
            return entry[1]
        _cache.pop(key, None)
        return None


def _cache_put(key, value):
    with _lock:
        _cache[key] = (_now(), value)
        while len(_cache) > MAX_CACHE_ENTRIES:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))


def clear_cache():
    with _lock:
        _cache.clear()


def clean_tickers(tickers):
    """공백 제거, 빈 값 제거, 중복 제거(입력 순서 유지)."""
    cleaned = list(dict.fromkeys(str(t).strip() for t in tickers if str(t).strip()))
    if not cleaned:
        raise ValidationError("티커를 입력하세요.")
    return cleaned


def get_prices(tickers, start_date, end_date):
    """
    티커별 종가 표(DataFrame)를 가져온다. 종료일은 결과에 포함된다.
    입력이 올바르지 않으면 ValidationError, 시세를 받지 못했으면 MarketDataError(종목명 포함).
    """
    tickers = clean_tickers(tickers)
    start, end_exclusive = validate_dates(start_date, end_date)
    # 같은 종목 집합이면 요청 순서와 무관하게 캐시를 공유하고, 결과는 요청한 순서로 돌려준다
    key = ("prices", tuple(sorted(tickers)), start, end_exclusive)
    cached = _cache_get(key, PRICE_HISTORY_TTL_SECONDS)
    if cached is not None:
        return cached.reindex(columns=tickers)

    try:
        raw = yf.download(tickers, start=start, end=end_exclusive)
    except Exception as e:
        raise MarketDataError(f"시세 조회에 실패했습니다: {e}") from e
    data = extract_close(raw, tickers)
    no_data = [t for t in tickers if t not in data.columns or data[t].isna().all()]
    if no_data:
        raise MarketDataError(f"가격 데이터를 받지 못한 종목이 있습니다: {', '.join(no_data)}. 티커를 확인하세요.")
    _cache_put(key, data.copy())
    return data.reindex(columns=tickers)


@dataclass
class LatestPrices:
    """티커별 마지막 사용 가능한 거래일 종가와 그 기준일."""
    prices: dict = field(default_factory=dict)   # {ticker: 종가}
    as_of: dict = field(default_factory=dict)    # {ticker: 기준일(Timestamp)}
    missing: list = field(default_factory=list)  # 가격을 얻지 못한 티커

    def distinct_dates(self):
        return sorted({d.date() for d in self.as_of.values()})

    def copy(self):
        return LatestPrices(dict(self.prices), dict(self.as_of), list(self.missing))


def fetch_latest_prices(tickers):
    """
    티커별 마지막 유효 종가와 기준일을 가져온다.
    조회 자체가 실패하거나 결과가 비어 있으면 MarketDataError. 일부 티커만 가격이 없으면 결과의 missing에 담는다.
    """
    tickers = list(dict.fromkeys(str(t).strip() for t in tickers if str(t).strip()))
    if not tickers:
        raise ValidationError("현재가를 조회할 티커가 없습니다.")
    key = ("latest", tuple(sorted(tickers)))
    cached = _cache_get(key, LATEST_PRICE_TTL_SECONDS)
    if cached is not None:
        return cached.copy()

    try:
        raw = yf.download(tickers, period="1mo", progress=False)
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
    _cache_put(key, result)
    return result.copy()


def get_current_prices(tickers):
    """마지막 사용 가능한 거래일 종가({ticker: 가격}). 하나도 얻지 못하면 MarketDataError."""
    result = fetch_latest_prices(tickers)
    if not result.prices:
        raise MarketDataError(f"현재가를 얻지 못했습니다: {', '.join(result.missing)}")
    return result.prices
