"""탭 여러 곳에서 반복되는 작은 화면 조각들. 종목 표 편집기, 행 추가/제거, 오류 표시, 공통 백테스트 설정 입력."""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import market_data as md
from config import (CAPITAL_STEP, DEFAULT_INITIAL_CAPITAL, DEFAULT_LOOKBACK_DAYS, DEFAULT_REBALANCE,
                    REBALANCE_OPTIONS, TICKER_NAMES, frequency_from_option, rebalance_index)
from errors import MarketDataError, ValidationError


def ticker_name(ticker):
    """config.TICKER_NAMES(국내 종목 한글명)에 없으면 yfinance에서 받은 이름으로 보완한다."""
    if ticker in TICKER_NAMES:
        return TICKER_NAMES[ticker]
    return md.get_ticker_name(ticker) or "(미등록)"


def normalize_ticker(text):
    """사용자가 입력한 티커 문자열을 정리한다. 6자리 숫자만 입력하면 국내 상장 종목(.KS)으로 본다."""
    ticker = text.strip().upper()
    if len(ticker) == 6 and ticker.isdigit():
        ticker += ".KS"
    return ticker


def show_error(error):
    """오류 종류에 따라 사용자에게 원인이 드러나는 메시지를 보여준다."""
    if isinstance(error, ValidationError):
        st.error(str(error))
    elif isinstance(error, MarketDataError):
        st.error(f"시세를 가져오지 못했습니다: {error}")
    else:
        st.error(f"예상하지 못한 오류가 발생했습니다: {error}")


def show_analysis_window(aligned, requested_start):
    """실제 분석 구간과, 요청과 달라진 이유를 보여준다."""
    st.caption(f"분석 구간: {aligned.start:%Y-%m-%d} ~ {aligned.end:%Y-%m-%d} ({aligned.days}거래일)")
    if aligned.limiting_ticker:
        first = aligned.first_valid[aligned.limiting_ticker]
        st.info(f"{ticker_name(aligned.limiting_ticker)}({aligned.limiting_ticker})의 가격이 {first:%Y-%m-%d}부터 있어 "
                f"분석 시작일이 요청({requested_start})보다 늦어졌습니다. 모든 종목에 가격이 있는 구간만 사용합니다.")
    if aligned.dropped_days:
        st.warning(f"일부 종목의 가격이 없는 {aligned.dropped_days}거래일은 제외했습니다(앞 값으로 채우지 않음).")


def backtest_settings(key_prefix, containers=None, default_rebalance=DEFAULT_REBALANCE):
    """시작일·종료일·초기 자본·리밸런싱 주기 입력 네 개를 만든다. containers를 주면 그 자리(예: st.columns)에 하나씩 그린다."""
    c1, c2, c3, c4 = containers or (st, st, st, st)
    start = c1.date_input("시작일", datetime.now() - timedelta(days=DEFAULT_LOOKBACK_DAYS), key=f"{key_prefix}_start")
    end = c2.date_input("종료일", datetime.now(), key=f"{key_prefix}_end")
    capital = c3.number_input("초기 자본 (원)", value=DEFAULT_INITIAL_CAPITAL, step=CAPITAL_STEP, key=f"{key_prefix}_capital")
    freq = frequency_from_option(c4.selectbox(
        "리밸런싱 주기", REBALANCE_OPTIONS, index=rebalance_index(default_rebalance), key=f"{key_prefix}_rebalance"))
    return start, end, capital, freq


def ticker_table_editor(table_key, version_key, column_config, key_prefix):
    """티커/종목명은 고정하고 나머지 열만 편집할 수 있는 표. version_key가 바뀌면(행 추가/제거) 편집 상태가 초기화된다."""
    version = st.session_state[version_key]
    return st.data_editor(
        st.session_state[table_key],
        key=f"{key_prefix}_editor_{version}",
        hide_index=True,
        width="stretch",
        disabled=["티커", "종목명"],
        column_config=column_config,
    ).fillna(0)


def row_controls(table_key, version_key, edited, new_row, prefix):
    """표 아래의 종목 추가/제거 UI. 표를 바꾸면 에디터 키(version)를 올려 편집 상태를 초기화한다."""
    version = st.session_state[version_key]
    add_col, remove_col = st.columns(2)
    with add_col:
        new_ticker = st.text_input("종목 추가 (티커 또는 6자리 종목코드)", key=f"{prefix}_new_{version}", placeholder="예: 360750.KS 또는 360750")
        if st.button("종목 추가", key=f"{prefix}_add_button"):
            ticker = normalize_ticker(new_ticker)
            if not ticker:
                st.error("추가할 티커를 입력하세요.")
            elif ticker in edited["티커"].values:
                st.warning(f"{ticker}은(는) 이미 표에 있습니다.")
            else:
                st.session_state[table_key] = pd.concat([edited, pd.DataFrame([new_row(ticker)])], ignore_index=True)
                st.session_state[version_key] += 1
                st.rerun()
    with remove_col:
        to_remove = st.multiselect("종목 제거", list(edited["티커"]), format_func=lambda t: f"{t} · {ticker_name(t)}", key=f"{prefix}_remove_{version}")
        if st.button("선택 종목 제거", key=f"{prefix}_remove_button") and to_remove:
            st.session_state[table_key] = edited[~edited["티커"].isin(to_remove)].reset_index(drop=True)
            st.session_state[version_key] += 1
            st.rerun()
