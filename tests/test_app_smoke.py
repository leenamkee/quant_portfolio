"""앱 스모크 테스트. 실제 Streamlit 스크립트를 임시 복사본에서 AppTest로 실행한다(네트워크 없음).

AppTest의 한계: data_editor 셀 직접 편집은 시뮬레이션할 수 없어 세션 상태의 표를 직접 세팅하고,
selectbox는 선택지가 바뀐 뒤 select()가 실패할 수 있어 위젯 키에 값을 직접 대입한다.
"""
import json
import os

import pytest
from streamlit.testing.v1 import AppTest


def errors(at):
    return [e.value for e in at.exception]


AUTH_SECRETS = {
    "auth": {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "x", "client_id": "i",
             "client_secret": "s", "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"},
    "ALLOWED_EMAILS": ["a@gmail.com"],
}


# ---------- 접근 제어 ----------

def test_dev_mode_boots_with_four_tabs(run_app):
    at = run_app()
    assert errors(at) == []
    assert len(at.tabs) == 4
    assert any("로컬 개발 모드" in c.value for c in at.sidebar.caption)


def test_login_screen_is_shown_when_auth_is_configured(run_app):
    at = run_app(AUTH_SECRETS)
    assert errors(at) == []
    assert [b.label for b in at.button] == ["Google로 로그인"]
    assert len(at.tabs) == 0


def test_github_store_without_auth_is_blocked(run_app):
    at = run_app({"GITHUB_TOKEN": "t", "GITHUB_REPO": "o/r"})
    assert errors(at) == []
    assert len(at.tabs) == 0
    assert any("로그인" in e.value for e in at.error)


# ---------- 기본 화면 값 ----------

def test_default_tables_use_default_portfolio(run_app):
    import config
    at = run_app()
    backtest, guide = at.session_state["bt_table"], at.session_state["rb_table"]
    assert list(backtest["티커"]) == list(config.DEFAULT_TARGET_WEIGHTS)
    assert backtest["비중(%)"].sum() == pytest.approx(100.0)
    assert all(name != "(미등록)" for name in backtest["종목명"])
    assert (guide["현재 수량"] == 0).all()  # 코드에 실제 보유 수량을 넣지 않는다


# ---------- 탭1: 자동 최적화 ----------

def test_tab1_optimization_runs(run_app):
    at = run_app()
    at.button(key="tab1_button").click().run()
    assert errors(at) == [] and not at.error
    assert [m.label for m in at.metric][:2] == ["총 수익률", "연환산 수익률"]


# ---------- 탭2: 사용자 정의 백테스트 ----------

def test_tab2_backtest_runs_with_default_table(run_app):
    at = run_app()
    at.button(key="custom_button").click().run()
    assert errors(at) == [] and not at.error
    assert len(at.metric) >= 4


def test_tab2_empty_table_shows_error_instead_of_running(run_app):
    at = run_app()
    table = at.session_state["bt_table"].copy()
    table["비중(%)"] = 0.0
    at.session_state["bt_table"] = table
    at.run()
    at.button(key="custom_button").click().run()
    assert errors(at) == []
    assert any("비중이 0보다 큰 종목이 없습니다" in e.value for e in at.error)


def test_tab2_save_then_load_portfolio(run_app):
    at = run_app()
    at.text_input(key="save_name").set_value("안A").run()
    at.button(key="save_portfolio_button").click().run()
    assert errors(at) == []
    saved = at.session_state["saved_portfolios"]
    assert [p["name"] for p in saved] == ["안A"] and saved[0]["owner_name"] == "로컬 사용자"

    table = at.session_state["bt_table"].copy()
    table.loc[table["티커"] == "360750.KS", "비중(%)"] = 35.0
    table.loc[table["티커"] == "273130.KS", "비중(%)"] = 20.0
    at.session_state["bt_table"] = table
    at.run()
    at.session_state["bt_load_select"] = saved[0]["id"]
    at.run()
    at.button(key="bt_load_button").click().run()
    loaded = at.session_state["bt_table"]
    assert float(loaded.loc[loaded["티커"] == "360750.KS", "비중(%)"].iloc[0]) == 25.0
    assert at.text_input(key="save_name").value == "안A"


def test_tab2_rejects_saving_when_weights_do_not_sum_to_100(run_app):
    at = run_app()
    table = at.session_state["bt_table"].copy()
    table.loc[0, "비중(%)"] = 10.0
    at.session_state["bt_table"] = table
    at.run()
    at.text_input(key="save_name").set_value("합계불일치").run()
    at.button(key="save_portfolio_button").click().run()
    assert at.session_state["saved_portfolios"] == []
    assert any("100%로 맞춘 뒤 저장" in e.value for e in at.error)


def test_tab2_add_and_remove_ticker_rows(run_app):
    at = run_app()
    at.text_input(key="bt_new_0").set_value("069500").run()
    at.button(key="bt_add_button").click().run()
    table = at.session_state["bt_table"]
    assert list(table["티커"])[-1] == "069500.KS" and table["종목명"].iloc[-1] == "(미등록)"
    version = at.session_state["bt_version"]
    at.multiselect(key=f"bt_remove_{version}").set_value(["069500.KS"]).run()
    at.button(key="bt_remove_button").click().run()
    assert "069500.KS" not in list(at.session_state["bt_table"]["티커"])


def test_tab2_new_ticker_name_is_filled_in_from_yfinance_when_available(run_app, monkeypatch):
    import yfinance

    class _NamedTicker:
        def __init__(self, ticker):
            self.info = {"longName": "Vanguard Total Stock Market ETF"} if ticker == "VTI" else {}
    monkeypatch.setattr(yfinance, "Ticker", _NamedTicker)

    at = run_app()
    at.text_input(key="bt_new_0").set_value("VTI").run()
    at.button(key="bt_add_button").click().run()
    table = at.session_state["bt_table"]
    assert list(table["티커"])[-1] == "VTI" and table["종목명"].iloc[-1] == "Vanguard Total Stock Market ETF"


# ---------- 탭3: 리밸런싱 가이드 ----------

def test_tab3_generates_guide_with_names(run_app):
    at = run_app()
    table = at.session_state["rb_table"].copy()
    for ticker, shares in {"360750.KS": 100, "411060.KS": 50, "273130.KS": 10}.items():
        table.loc[table["티커"] == ticker, "현재 수량"] = shares
    at.session_state["rb_table"] = table
    at.run()
    at.button(key="rebalancing_button").click().run()
    assert errors(at) == [] and not at.error
    frames = [d.value for d in at.dataframe if {"Ticker", "종목명"} <= set(d.value.columns)]
    assert frames and "TIGER 미국S&P500" in set(frames[0]["종목명"])
    assert list(frames[0]["Ticker"]) == list(table["티커"])  # 입력 순서 유지


def test_tab3_warns_when_all_holdings_are_zero(run_app):
    at = run_app()
    at.button(key="rebalancing_button").click().run()
    assert errors(at) == []
    assert any("보유 수량이 모두 0" in w.value for w in at.warning)


def test_tab3_holdings_are_saved_per_user_and_reloaded(run_app):
    at = run_app()
    table = at.session_state["rb_table"].copy()
    table.loc[table["티커"] == "360750.KS", "현재 수량"] = 120
    at.session_state["rb_table"] = table
    at.run()
    at.button(key="save_holdings_button").click().run()
    assert any("보유 수량을 저장했습니다" in s.value for s in at.success)

    fresh = run_app()  # 새 세션
    reloaded = fresh.session_state["rb_table"]
    assert int(reloaded.loc[reloaded["티커"] == "360750.KS", "현재 수량"].iloc[0]) == 120
    users_dir = os.path.join(run_app.app_env, "data", "users")
    assert len(os.listdir(users_dir)) == 1  # 이메일이 아닌 해시 파일명
    assert "@" not in os.listdir(users_dir)[0]


# ---------- 탭4: 비교 ----------

def test_tab4_compares_saved_portfolios(run_app):
    at = run_app()
    for name in ("안A", "안B"):
        at.text_input(key="save_name").set_value(name).run()
        at.button(key="save_portfolio_button").click().run()
    at.button(key="compare_button").click().run()
    assert errors(at) == [] and not at.error
    metrics = at.dataframe[-1].value
    assert list(metrics["포트폴리오"]) == ["안A", "안B"]


def test_tab4_delete_removes_only_selected(run_app):
    at = run_app()
    for name in ("안A", "안B"):
        at.text_input(key="save_name").set_value(name).run()
        at.button(key="save_portfolio_button").click().run()
    first = at.session_state["saved_portfolios"][0]["id"]
    at.multiselect(key="delete_selected").set_value([first]).run()
    at.button(key="delete_button").click().run()
    assert [p["name"] for p in at.session_state["saved_portfolios"]] == ["안B"]


# ---------- 입력 검증·실패 처리 (단계 1) ----------

def test_tab3_blocks_guide_and_names_the_ticker_when_a_price_is_missing(run_app, krx_prices, monkeypatch):
    import yfinance
    from fakes import make_download
    monkeypatch.setattr(yfinance, "download", make_download(krx_prices.drop(columns=["411060.KS"])))
    at = run_app()
    table = at.session_state["rb_table"].copy()
    for ticker in ("360750.KS", "411060.KS"):
        table.loc[table["티커"] == ticker, "현재 수량"] = 10
    at.session_state["rb_table"] = table
    at.run()
    at.button(key="rebalancing_button").click().run()
    assert errors(at) == []
    assert any("411060.KS" in e.value for e in at.error)
    assert not [d for d in at.dataframe if "Ticker" in d.value.columns]  # 잘못된 매매 안내표가 만들어지지 않는다


def test_tab3_shows_the_price_basis_date(run_app):
    at = run_app()
    table = at.session_state["rb_table"].copy()
    table.loc[table["티커"] == "360750.KS", "현재 수량"] = 100
    at.session_state["rb_table"] = table
    at.run()
    at.button(key="rebalancing_button").click().run()
    assert any(c.value.startswith("가격 기준: 마지막 거래일 종가") for c in at.caption)


def test_tab1_reports_a_ticker_without_price_data(run_app):
    at = run_app()
    at.text_input(key="tab1_tickers").set_value("273130.KS, NOPE.KS").run()
    at.button(key="tab1_button").click().run()
    assert errors(at) == []
    assert any("NOPE.KS" in e.value for e in at.error)


def test_tab2_reports_start_after_end_with_a_clear_message(run_app):
    import datetime as dt
    at = run_app()
    at.date_input(key="custom_start").set_value(dt.date(2026, 6, 1))
    at.date_input(key="custom_end").set_value(dt.date(2026, 1, 1))
    at.run()
    at.button(key="custom_button").click().run()
    assert errors(at) == []
    assert any("시작일" in e.value and "종료일" in e.value for e in at.error)


def test_unexpected_errors_are_labeled_differently_from_input_errors(run_app, monkeypatch):
    import market_data  # 앱이 실제로 호출하는 이름(md.get_prices)을 패치한다
    at = run_app()
    monkeypatch.setattr(market_data, "get_prices", lambda *a, **k: (_ for _ in ()).throw(KeyError("boom")))
    at.button(key="custom_button").click().run()
    assert any("예상하지 못한 오류" in e.value for e in at.error)


# ---------- 데이터 계약: 분석 구간, 캐시 (단계 2) ----------

def test_analysis_window_is_shown_and_explains_a_late_starting_ticker(run_app, krx_prices, monkeypatch):
    import numpy as np
    import yfinance
    from fakes import make_download
    late = krx_prices.copy()
    late.loc[late.index[:50], "458730.KS"] = np.nan  # 이 종목만 50거래일 늦게 시작
    monkeypatch.setattr(yfinance, "download", make_download(late))
    at = run_app()
    at.button(key="custom_button").click().run()
    assert errors(at) == [] and not at.error
    assert any(c.value.startswith("분석 구간:") and "250거래일" in c.value for c in at.caption)
    assert any("458730.KS" in i.value and "분석 시작일" in i.value for i in at.info)


def test_missing_days_are_reported_when_excluded(run_app, krx_prices, monkeypatch):
    import numpy as np
    import yfinance
    from fakes import make_download
    gappy = krx_prices.copy()
    gappy.loc[gappy.index[100], "411060.KS"] = np.nan  # 중간 하루 결측
    monkeypatch.setattr(yfinance, "download", make_download(gappy))
    at = run_app()
    at.button(key="custom_button").click().run()
    assert errors(at) == [] and not at.error
    assert any("1거래일은 제외" in w.value for w in at.warning)


def test_price_downloads_are_shared_between_tabs_through_the_cache(run_app, krx_prices, monkeypatch):
    import yfinance
    from fakes import make_download
    calls = []
    monkeypatch.setattr(yfinance, "download", make_download(krx_prices, calls))
    at = run_app()
    at.button(key="custom_button").click().run()   # 탭2: 기본 6종목, 기본 기간
    at.button(key="tab1_button").click().run()  # 탭1: 같은 티커·기간
    history_calls = [c for c in calls if "start" in c]
    assert len(history_calls) == 1  # 두 탭이 같은 요청을 한 번만 보냈다
