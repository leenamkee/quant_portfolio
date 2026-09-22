import datetime as dt

import numpy as np
import pandas as pd
import pytest

import config
import market_data as md
from errors import MarketDataError, ValidationError
from fakes import make_download


# ---------- 과거 종가 ----------

def test_get_prices_returns_close_prices_as_frame(monkeypatch, prices):
    monkeypatch.setattr(md.yf, "download", make_download(prices))
    data = md.get_prices(["AAA.KS", "BBB.KS"], "2024-01-01", "2024-12-31")
    assert list(data.columns) == ["AAA.KS", "BBB.KS"]
    assert data.equals(prices[["AAA.KS", "BBB.KS"]])


def test_a_series_result_is_wrapped_into_a_frame(monkeypatch):
    series = pd.Series([1.0, 2.0], index=pd.bdate_range("2024-01-01", periods=2), name="Close")
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: {"Close": series})
    data = md.get_prices(["AAA.KS"], "2024-01-01", "2024-01-31")
    assert isinstance(data, pd.DataFrame) and list(data.columns) == ["AAA.KS"]


def test_end_date_is_included_by_requesting_the_next_day(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    md.get_prices(["AAA.KS"], dt.date(2024, 1, 2), dt.date(2024, 3, 29))
    assert calls[0]["start"] == pd.Timestamp("2024-01-02") and calls[0]["end"] == pd.Timestamp("2024-03-30")


def test_tickers_are_trimmed_and_deduplicated_in_order(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    data = md.get_prices([" BBB.KS", "AAA.KS", "", "BBB.KS", "AAA.KS "], "2024-01-01", "2024-03-01")
    assert calls[0]["tickers"] == ["BBB.KS", "AAA.KS"] and list(data.columns) == ["BBB.KS", "AAA.KS"]


@pytest.mark.parametrize("tickers", [[], [""], ["  ", ""]])
def test_prices_without_tickers_are_rejected(tickers):
    with pytest.raises(ValidationError, match="티커"):
        md.get_prices(tickers, "2024-01-01", "2024-03-01")


def test_start_after_end_is_rejected():
    with pytest.raises(ValidationError, match="시작일"):
        md.get_prices(["AAA.KS"], "2024-06-01", "2024-01-01")


def test_a_future_end_date_is_rejected():
    with pytest.raises(ValidationError, match="오늘 이후"):
        md.get_prices(["AAA.KS"], "2024-01-01", dt.date.today() + dt.timedelta(days=30))


def test_download_failure_is_reported_as_market_data_error(monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError("network down")
    monkeypatch.setattr(md.yf, "download", broken)
    with pytest.raises(MarketDataError, match="network down"):
        md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")


def test_empty_download_result_is_a_market_data_error(monkeypatch):
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(MarketDataError, match="비어"):
        md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")


def test_ticker_without_any_price_is_reported_by_name(monkeypatch, prices):
    monkeypatch.setattr(md.yf, "download", make_download(prices))
    with pytest.raises(MarketDataError, match="NOPE.KS"):
        md.get_prices(["AAA.KS", "NOPE.KS"], "2024-01-01", "2024-03-01")


# ---------- 현재가 (마지막 사용 가능한 거래일 종가, §9-2 확정) ----------

def close_frame():
    idx = pd.bdate_range("2024-01-01", periods=5)
    return pd.DataFrame({"A": [1.0, 2, 3, 4, 5], "B": [10.0, 20, 30, 40, np.nan]}, index=idx)


def test_current_prices_use_last_available_close(monkeypatch):
    monkeypatch.setattr(md.yf, "download", make_download(close_frame()))
    assert md.get_current_prices(["A", "B"]) == {"A": 5.0, "B": 40.0}


def test_latest_prices_report_the_as_of_date_per_ticker(monkeypatch):
    monkeypatch.setattr(md.yf, "download", make_download(close_frame()))
    latest = md.fetch_latest_prices(["A", "B"])
    assert latest.as_of["A"] == pd.Timestamp("2024-01-05") and latest.as_of["B"] == pd.Timestamp("2024-01-04")
    assert latest.distinct_dates() == [pd.Timestamp("2024-01-04").date(), pd.Timestamp("2024-01-05").date()]


def test_tickers_without_valid_prices_are_reported_as_missing(monkeypatch):
    frame = close_frame()
    frame["C"] = 0.0  # 0 이하 가격은 유효하지 않음
    monkeypatch.setattr(md.yf, "download", make_download(frame))
    latest = md.fetch_latest_prices(["A", "C", "NOPE"])
    assert latest.prices == {"A": 5.0} and latest.missing == ["C", "NOPE"]


def test_price_lookup_failure_is_not_hidden(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(md.yf, "download", broken)
    with pytest.raises(MarketDataError, match="network down"):
        md.get_current_prices(["A"])


def test_empty_price_result_is_an_error(monkeypatch):
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: pd.concat({"Close": pd.DataFrame()}, axis=1))
    with pytest.raises(MarketDataError, match="비어"):
        md.fetch_latest_prices(["A"])


def test_no_price_for_any_ticker_is_an_error(monkeypatch):
    monkeypatch.setattr(md.yf, "download", make_download(close_frame()))
    with pytest.raises(MarketDataError, match="NOPE"):
        md.get_current_prices(["NOPE"])


def test_no_tickers_for_latest_prices_is_a_validation_error():
    with pytest.raises(ValidationError):
        md.fetch_latest_prices([" ", ""])


def test_single_ticker_series_result_is_supported(monkeypatch):
    series = pd.Series([1.0, 2.0], index=pd.bdate_range("2024-01-01", periods=2), name="Close")
    monkeypatch.setattr(md.yf, "download", lambda *a, **k: {"Close": series})
    assert md.get_current_prices(["A"]) == {"A": 2.0}


# ---------- 캐시 (D1) ----------

@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(md, "_now", lambda: now["t"])
    return now


def test_repeated_price_requests_hit_the_cache(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    first = md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    second = md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    assert len(calls) == 1 and first.equals(second)


def test_cached_frames_are_independent_copies(monkeypatch, prices):
    monkeypatch.setattr(md.yf, "download", make_download(prices))
    first = md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    first.iloc[:, :] = 0.0  # 호출자가 결과를 바꿔도
    assert (md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01") != 0).all().all()  # 캐시는 영향 없음


def test_different_arguments_are_cached_separately(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    md.get_prices(["BBB.KS"], "2024-01-01", "2024-03-01")
    md.get_prices(["AAA.KS"], "2024-01-01", "2024-04-01")
    assert len(calls) == 3


def test_history_cache_expires_after_ttl(monkeypatch, prices, clock):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    clock["t"] += config.PRICE_HISTORY_TTL_SECONDS - 1
    md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    assert len(calls) == 1
    clock["t"] += 2
    md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    assert len(calls) == 2


def test_latest_prices_use_a_shorter_ttl_than_history(monkeypatch, clock):
    assert config.LATEST_PRICE_TTL_SECONDS < config.PRICE_HISTORY_TTL_SECONDS
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(close_frame(), calls))
    md.fetch_latest_prices(["A"])
    clock["t"] += config.LATEST_PRICE_TTL_SECONDS - 1
    md.fetch_latest_prices(["A"])
    assert len(calls) == 1
    clock["t"] += 2
    md.fetch_latest_prices(["A"])
    assert len(calls) == 2


def test_errors_are_not_cached(monkeypatch, prices):
    state = {"fail": True, "calls": 0}
    good = make_download(prices)

    def flaky(*args, **kwargs):
        state["calls"] += 1
        if state["fail"]:
            raise ConnectionError("down")
        return good(*args, **kwargs)
    monkeypatch.setattr(md.yf, "download", flaky)
    with pytest.raises(MarketDataError):
        md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01")
    state["fail"] = False
    assert not md.get_prices(["AAA.KS"], "2024-01-01", "2024-03-01").empty
    assert state["calls"] == 2


def test_cache_is_bounded(monkeypatch, prices):
    monkeypatch.setattr(md.yf, "download", make_download(prices))
    for day in range(1, md.MAX_CACHE_ENTRIES + 10):
        md.get_prices(["AAA.KS"], "2024-01-01", pd.Timestamp("2024-02-01") + pd.Timedelta(days=day))
    assert len(md._cache) <= md.MAX_CACHE_ENTRIES


def test_cache_is_shared_regardless_of_ticker_order(monkeypatch, prices):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(prices, calls))
    forward = md.get_prices(["AAA.KS", "BBB.KS"], "2024-01-01", "2024-03-01")
    backward = md.get_prices(["BBB.KS", "AAA.KS"], "2024-01-01", "2024-03-01")
    assert len(calls) == 1
    assert list(forward.columns) == ["AAA.KS", "BBB.KS"] and list(backward.columns) == ["BBB.KS", "AAA.KS"]
    assert backward["AAA.KS"].equals(forward["AAA.KS"])


def test_latest_price_cache_is_shared_regardless_of_ticker_order(monkeypatch):
    calls = []
    monkeypatch.setattr(md.yf, "download", make_download(close_frame(), calls))
    md.fetch_latest_prices(["A", "B"])
    md.fetch_latest_prices(["B", "A"])
    assert len(calls) == 1


# ---------- 종목명 (config.TICKER_NAMES에 없는 티커를 yfinance로 보완) ----------

def _fake_ticker_class(info_by_ticker, calls=None):
    class _Ticker:
        def __init__(self, ticker):
            if calls is not None:
                calls.append(ticker)
            self.info = info_by_ticker.get(ticker, {})
    return _Ticker


def test_ticker_name_uses_long_name(monkeypatch):
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({"VTI": {"longName": "Vanguard Total Stock Market ETF"}}))
    assert md.get_ticker_name("VTI") == "Vanguard Total Stock Market ETF"


def test_ticker_name_falls_back_to_short_name(monkeypatch):
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({"VTI": {"shortName": "Vanguard Total Stock Mkt"}}))
    assert md.get_ticker_name("VTI") == "Vanguard Total Stock Mkt"


def test_ticker_name_is_none_when_info_has_no_name(monkeypatch):
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({"VTI": {}}))
    assert md.get_ticker_name("VTI") is None


def test_ticker_name_is_none_when_lookup_raises(monkeypatch):
    class _Broken:
        def __init__(self, ticker):
            raise ConnectionError("down")
    monkeypatch.setattr(md.yf, "Ticker", _Broken)
    assert md.get_ticker_name("VTI") is None


def test_ticker_name_lookup_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({"VTI": {"longName": "Vanguard Total Stock Market ETF"}}, calls))
    md.get_ticker_name("VTI")
    md.get_ticker_name("VTI")
    assert calls == ["VTI"]


def test_ticker_name_failure_is_also_cached(monkeypatch):
    """가격 조회 오류(test_errors_are_not_cached)와 달리, 이름 조회 실패는 매 요청마다 다시 부르지 않도록 캐시한다."""
    calls = []
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({}, calls))
    md.get_ticker_name("UNKNOWN")
    md.get_ticker_name("UNKNOWN")
    assert calls == ["UNKNOWN"]


def test_ticker_name_cache_expires_after_ttl(monkeypatch, clock):
    calls = []
    monkeypatch.setattr(md.yf, "Ticker", _fake_ticker_class({"VTI": {"longName": "Vanguard Total Stock Market ETF"}}, calls))
    md.get_ticker_name("VTI")
    clock["t"] += config.TICKER_NAME_TTL_SECONDS - 1
    md.get_ticker_name("VTI")
    assert len(calls) == 1
    clock["t"] += 2
    md.get_ticker_name("VTI")
    assert len(calls) == 2
