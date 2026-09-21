import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import portfolio_engine as pe
import rebalance_engine as re
import custom_backtest as cb
import rebalancing_guide as rg
import portfolio_store as ps
import auth

st.set_page_config(page_title="Quant Portfolio Manager", layout="wide")

TICKER_NAMES = pe.TICKER_NAMES
TARGET_WEIGHTS_PCT = {t: round(w * 100, 1) for t, w in pe.DEFAULT_TARGET_WEIGHTS.items()}
DEFAULT_TICKERS = ", ".join(sorted(pe.DEFAULT_TARGET_WEIGHTS))


@st.cache_resource
def get_store():
    return ps.get_backend(st.secrets)


@st.cache_data(ttl=3600, show_spinner=False)
def load_prices(tickers, start, end):
    return pe.get_stock_data(list(tickers), start, end)


store = get_store()

identity = auth.resolve_identity(st.user, st.secrets, store.persistent)
if identity.status == "login":
    st.title("📈 퀀트 포트폴리오 매니저")
    st.info("허용된 Google 계정으로 로그인해야 사용할 수 있습니다.")
    st.button("Google로 로그인", on_click=st.login, type="primary")
    st.stop()
if identity.status in ("denied", "misconfigured"):
    st.error(identity.message)
    if identity.status == "denied":
        st.button("다른 계정으로 로그인", on_click=st.logout)
    st.stop()


@st.cache_resource
def get_user_store(key):
    return ps.get_backend(st.secrets, ps.user_path(key))


user_store = get_user_store(identity.key)

st.sidebar.markdown(f"👤 **{identity.name}**")
if identity.dev:
    st.sidebar.caption("로그인 미설정: 로컬 개발 모드")
else:
    st.sidebar.caption(identity.email)
    st.sidebar.button("로그아웃", on_click=st.logout, key="logout_button")


def refresh_saved_portfolios():
    try:
        st.session_state["saved_portfolios"] = ps.load(store)["portfolios"]
        st.session_state["store_error"] = None
    except ps.StoreError as e:
        st.session_state.setdefault("saved_portfolios", [])
        st.session_state["store_error"] = str(e)


def ticker_name(ticker):
    return TICKER_NAMES.get(ticker, "(미등록)")


def normalize_ticker(text):
    ticker = text.strip().upper()
    if len(ticker) == 6 and ticker.isdigit():
        ticker += ".KS"
    return ticker


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


if "saved_portfolios" not in st.session_state:
    refresh_saved_portfolios()

st.title("📈 퀀트 포트폴리오 구성 및 리밸런싱")
st.markdown("""
이 앱은 주식 포트폴리오를 최적화하고 리밸런싱 전략에 따른 성과를 시뮬레이션합니다.
또한 사용자 정의 포트폴리오의 백테스트와 현재 보유 수량 기반 리밸런싱 가이드를 제공합니다.
""")

# 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["자동 최적화", "사용자 정의 백테스트", "리밸런싱 가이드", "포트폴리오 비교"])

# ============ TAB 1: 자동 최적화 ============
with tab1:
    st.header("자동 포트폴리오 최적화")
    
    # 사이드바 설정
    st.sidebar.header("⚙️ 자동 최적화 설정")
    tickers_input = st.sidebar.text_input("티커 입력 (쉼표로 구분)", DEFAULT_TICKERS, key="tab1_tickers")
    tickers = [t.strip() for t in tickers_input.split(",")]
    
    start_date = st.sidebar.date_input("시작일", datetime.now() - timedelta(days=365*2), key="tab1_start")
    end_date = st.sidebar.date_input("종료일", datetime.now(), key="tab1_end")
    
    initial_capital = st.sidebar.number_input("초기 자본 (원)", value=10000000, step=1000000, key="tab1_capital")
    rebalance_freq = st.sidebar.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=1, key="tab1_rebalance")
    if rebalance_freq == "None": rebalance_freq = None
    
    opt_method = st.sidebar.selectbox("최적화 방법", ["max_sharpe", "min_volatility", "equal_weight", "target_weight"], key="tab1_method")
    
    if st.sidebar.button("분석 실행", key="tab1_button"):
        with st.spinner("데이터를 가져오고 분석 중입니다..."):
            try:
                # 1. 데이터 가져오기
                data = pe.get_stock_data(tickers, start_date, end_date)
                
                if data.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 확인해주세요.")
                else:
                    # 2. 포트폴리오 최적화
                    weights = pe.optimize_portfolio(data, method=opt_method)
                    
                    # 3. 백테스트 수행
                    history = re.backtest_rebalancing(data, weights, rebalance_freq, initial_capital)
                    metrics = re.calculate_metrics(history)
                    
                    # 결과 표시
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("총 수익률", f"{metrics['Total Return']:.2%}")
                    col2.metric("연환산 수익률", f"{metrics['Annualized Return']:.2%}")
                    col3.metric("샤프 지수", f"{metrics['Sharpe Ratio']:.2f}")
                    col4.metric("최대 낙폭 (MDD)", f"{metrics['Max Drawdown']:.2%}")
                    
                    # 탭 구성
                    tab1_1, tab1_2, tab1_3 = st.tabs(["성과 분석", "자산 배분", "데이터"])
                    
                    with tab1_1:
                        st.subheader("포트폴리오 가치 추이 (CAGR 반영)")
                        history['Daily Return'] = history['Portfolio Value'].pct_change()
                        
                        fig_line = px.line(history, y="Portfolio Value", title=f"Portfolio Value Over Time (CAGR: {metrics['Annualized Return']:.2%})")
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                        st.subheader("낙폭 (Drawdown) 시각화")
                        history['Cumulative Max'] = history['Portfolio Value'].cummax()
                        history['Drawdown'] = (history['Portfolio Value'] - history['Cumulative Max']) / history['Cumulative Max']
                        
                        fig_dd = px.area(history, y="Drawdown", title=f"Portfolio Drawdown (MDD: {metrics['Max Drawdown']:.2%})", color_discrete_sequence=['red'])
                        fig_dd.update_yaxes(tickformat=".2%")
                        st.plotly_chart(fig_dd, use_container_width=True)
                        
                        st.subheader("일간 수익률 분포")
                        fig_hist = px.histogram(history, x="Daily Return", nbins=50, title="Daily Return Distribution")
                        st.plotly_chart(fig_hist, use_container_width=True)
                    
                    with tab1_2:
                        st.subheader("최적화된 자산 배분")
                        weight_df = pd.DataFrame(list(weights.items()), columns=['Ticker', 'Weight'])
                        fig_pie = px.pie(weight_df, values='Weight', names='Ticker', title=f"Portfolio Weights ({opt_method})")
                        st.plotly_chart(fig_pie, use_container_width=True)
                        
                        st.table(weight_df.style.format({'Weight': '{:.2%}'}))
                        
                        # 실제 주식 수 계산
                        latest_prices = data.iloc[-1]
                        allocation, leftover = pe.get_discrete_allocation(weights, latest_prices, initial_capital)
                        st.subheader("추천 매수 수량 (현재가 기준)")
                        st.write(f"남은 현금: {leftover:,.0f}원")
                        st.table(pd.DataFrame(list(allocation.items()), columns=['Ticker', 'Shares']))
                    
                    with tab1_3:
                        st.subheader("주가 데이터 (Adj Close)")
                        st.dataframe(data)
                        
                        st.subheader("자산 간 상관관계")
                        corr = data.pct_change().corr()
                        fig_corr = px.imshow(corr, text_auto=True, title="Asset Correlation Matrix")
                        st.plotly_chart(fig_corr, use_container_width=True)
                        
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
    else:
        st.info("왼쪽 사이드바에서 설정을 완료하고 '분석 실행' 버튼을 눌러주세요.")


# ============ TAB 2: 사용자 정의 백테스트 ============
with tab2:
    st.header("사용자 정의 포트폴리오 백테스트")
    st.markdown("표에서 종목별 비중을 입력해 백테스트합니다. 저장한 포트폴리오를 불러와 수정하거나, 새로 구성해 저장할 수 있습니다.")
    if st.session_state.get("bt_flash"):
        st.success(st.session_state.pop("bt_flash"))

    def bt_default_table():
        tickers = list(pe.DEFAULT_TARGET_WEIGHTS)
        return pd.DataFrame({
            "티커": tickers,
            "종목명": [ticker_name(t) for t in tickers],
            "비중(%)": [float(TARGET_WEIGHTS_PCT[t]) for t in tickers],
        })

    if "bt_table" not in st.session_state:
        st.session_state["bt_table"] = bt_default_table()
        st.session_state["bt_version"] = 0

    saved_list = st.session_state["saved_portfolios"]
    saved_labels = {p["id"]: f"{p['name']} · {p.get('owner_name') or '작성자 없음'}" for p in saved_list}
    load_col1, load_col2, load_col3 = st.columns([3, 1, 1])
    load_id = load_col1.selectbox(
        "저장된 포트폴리오 불러오기", list(saved_labels), format_func=saved_labels.get, index=None,
        placeholder="저장된 포트폴리오를 선택하세요" if saved_list else "저장된 포트폴리오가 없습니다", key="bt_load_select",
    )
    load_col2.write("")
    load_col3.write("")
    if load_col2.button("불러오기", key="bt_load_button", disabled=load_id is None):
        chosen = next(p for p in saved_list if p["id"] == load_id)
        st.session_state["bt_table"] = pd.DataFrame({
            "티커": chosen["tickers"],
            "종목명": [ticker_name(t) for t in chosen["tickers"]],
            "비중(%)": [round(chosen["weights"][t] * 100, 4) for t in chosen["tickers"]],
        })
        st.session_state["bt_version"] += 1
        st.session_state["bt_loaded"] = saved_labels[load_id]
        mine = ps.can_modify(chosen, identity.key)
        st.session_state["save_name"] = chosen["name"] if mine else f"{chosen['name']} (내 복사본)"
        st.rerun()
    if load_col3.button("기본 구성으로 초기화", key="bt_reset_button"):
        st.session_state["bt_table"] = bt_default_table()
        st.session_state["bt_version"] += 1
        st.session_state.pop("bt_loaded", None)
        st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("포트폴리오 구성")
        if st.session_state.get("bt_loaded"):
            st.caption(f"불러온 포트폴리오: {st.session_state['bt_loaded']} (표를 수정해도 저장하기 전에는 원본이 바뀌지 않습니다)")
        bt_edited = st.data_editor(
            st.session_state["bt_table"],
            key=f"bt_editor_{st.session_state['bt_version']}",
            hide_index=True,
            use_container_width=True,
            disabled=["티커", "종목명"],
            column_config={
                "비중(%)": st.column_config.NumberColumn("비중(%)", min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
            },
        ).fillna(0)

        weights_custom = {row["티커"]: float(row["비중(%)"]) / 100 for _, row in bt_edited.iterrows() if row["비중(%)"] > 0}
        tickers_list = list(weights_custom)
        bt_total = bt_edited["비중(%)"].sum()
        if abs(bt_total - 100) > 0.05:
            st.warning(f"비중 합계가 {bt_total:.1f}%입니다. 백테스트는 비율에 맞춰 계산하지만, 저장하려면 100%로 맞추세요.")
        else:
            st.caption(f"비중 합계: {bt_total:.1f}%")

        row_controls(
            "bt_table", "bt_version", bt_edited,
            lambda t: {"티커": t, "종목명": ticker_name(t), "비중(%)": 0.0},
            "bt",
        )

    with col2:
        st.subheader("백테스트 설정")
        custom_start_date = st.date_input("시작일", datetime.now() - timedelta(days=365*2), key="custom_start")
        custom_end_date = st.date_input("종료일", datetime.now(), key="custom_end")
        custom_initial_capital = st.number_input("초기 자본 (원)", value=10000000, step=1000000, key="custom_capital")
        custom_rebalance_freq = st.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=1, key="custom_rebalance")
        if custom_rebalance_freq == "None": custom_rebalance_freq = None

    save_col1, save_col2 = st.columns([3, 1])
    save_name = save_col1.text_input("포트폴리오 이름 (같은 이름이면 덮어씁니다)", key="save_name", placeholder="예: DC 기본안")
    save_col2.write("")
    if save_col2.button("현재 구성 저장", key="save_portfolio_button"):
        total_weight = sum(weights_custom.values())
        if not save_name.strip():
            st.error("저장할 이름을 입력하세요.")
        elif abs(total_weight - 1) > 0.005:
            st.error(f"비중 합계가 {total_weight:.1%}입니다. 100%로 맞춘 뒤 저장하세요.")
        else:
            try:
                data = ps.upsert_portfolio(store, ps.make_portfolio(save_name, weights_custom, identity.key, identity.name))
                st.session_state["saved_portfolios"] = data["portfolios"]
                saved_id = next(p["id"] for p in data["portfolios"] if p["name"] == save_name.strip())
                current = [i for i in st.session_state.get("compare_selected", []) if i in {p["id"] for p in data["portfolios"]}]
                st.session_state["compare_selected"] = current + ([saved_id] if saved_id not in current else [])
                st.session_state["bt_flash"] = f"'{save_name.strip()}' 저장 완료 → '포트폴리오 비교' 탭에서 비교할 수 있습니다. ({store.label})"
                st.rerun()
            except ps.StoreError as e:
                st.error(f"저장 실패: {e}")

    run_backtest = st.button("백테스트 실행", key="custom_button")
    if run_backtest and not tickers_list:
        st.error("비중이 0보다 큰 종목이 없습니다. 표에 비중을 입력하세요.")
    elif run_backtest:
        with st.spinner("백테스트 중입니다..."):
            try:
                # 데이터 가져오기
                data = cb.get_stock_data(tickers_list, custom_start_date, custom_end_date)
                
                if data.empty:
                    st.error("데이터를 가져오지 못했습니다. 티커를 확인해주세요.")
                else:
                    # 백테스트 수행
                    history = cb.backtest_custom_portfolio(
                        data, weights_custom, custom_rebalance_freq, custom_initial_capital
                    )
                    metrics = cb.calculate_metrics(history)
                    
                    # 결과 표시
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("총 수익률", f"{metrics['Total Return']:.2%}")
                    col2.metric("연환산 수익률", f"{metrics['Annualized Return']:.2%}")
                    col3.metric("샤프 지수", f"{metrics['Sharpe Ratio']:.2f}")
                    col4.metric("최대 낙폭 (MDD)", f"{metrics['Max Drawdown']:.2%}")
                    
                    # 차트
                    tab2_1, tab2_2, tab2_3 = st.tabs(["성과 분석", "자산 배분", "데이터"])
                    
                    with tab2_1:
                        st.subheader("포트폴리오 가치 추이")
                        history['Daily Return'] = history['Portfolio Value'].pct_change()
                        
                        fig_line = px.line(history, y="Portfolio Value", title=f"Portfolio Value Over Time (CAGR: {metrics['Annualized Return']:.2%})")
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                        st.subheader("낙폭 (Drawdown) 시각화")
                        history['Cumulative Max'] = history['Portfolio Value'].cummax()
                        history['Drawdown'] = (history['Portfolio Value'] - history['Cumulative Max']) / history['Cumulative Max']
                        
                        fig_dd = px.area(history, y="Drawdown", title=f"Portfolio Drawdown (MDD: {metrics['Max Drawdown']:.2%})", color_discrete_sequence=['red'])
                        fig_dd.update_yaxes(tickformat=".2%")
                        st.plotly_chart(fig_dd, use_container_width=True)
                        
                        st.subheader("일간 수익률 분포")
                        fig_hist = px.histogram(history, x="Daily Return", nbins=50, title="Daily Return Distribution")
                        st.plotly_chart(fig_hist, use_container_width=True)
                    
                    with tab2_2:
                        st.subheader("포트폴리오 구성")
                        weight_df = pd.DataFrame(list(weights_custom.items()), columns=['Ticker', 'Weight'])
                        weight_df.insert(1, '종목명', weight_df['Ticker'].map(TICKER_NAMES).fillna(weight_df['Ticker']))
                        fig_pie = px.pie(weight_df, values='Weight', names='종목명', title="Portfolio Weights")
                        st.plotly_chart(fig_pie, use_container_width=True)

                        st.table(weight_df.style.format({'Weight': '{:.2%}'}))
                    
                    with tab2_3:
                        st.subheader("주가 데이터 (Adj Close)")
                        st.dataframe(data)
                        
                        st.subheader("자산 간 상관관계")
                        corr = data.pct_change().corr()
                        fig_corr = px.imshow(corr, text_auto=True, title="Asset Correlation Matrix")
                        st.plotly_chart(fig_corr, use_container_width=True)
                        
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
    else:
        st.info("포트폴리오 설정을 완료하고 '백테스트 실행' 버튼을 눌러주세요.")


# ============ TAB 3: 리밸런싱 가이드 ============
with tab3:
    st.header("리밸런싱 가이드")
    st.markdown("현재 보유 수량을 입력하고 목표 비중을 설정하면 리밸런싱 가이드를 제공합니다.")
    
    if "rb_table" not in st.session_state:
        try:
            saved_holdings = ps.load_holdings(user_store)
        except ps.StoreError as e:
            saved_holdings = {}
            st.warning(f"저장된 보유 수량을 불러오지 못했습니다: {e}")
        initial_tickers = list(pe.DEFAULT_TARGET_WEIGHTS) + [t for t in saved_holdings if t not in pe.DEFAULT_TARGET_WEIGHTS]
        st.session_state["rb_table"] = pd.DataFrame({
            "티커": initial_tickers,
            "종목명": [ticker_name(t) for t in initial_tickers],
            "현재 수량": [int(saved_holdings.get(t, 0)) for t in initial_tickers],
            "목표 비중(%)": [float(TARGET_WEIGHTS_PCT.get(t, 0.0)) for t in initial_tickers],
        })
        st.session_state["rb_version"] = 0

    version = st.session_state["rb_version"]
    st.subheader("현재 수량 · 목표 비중")
    st.caption("표에서 현재 수량(주)과 목표 비중(%)을 직접 수정하세요. 현재 수량은 '내 보유 수량 저장'으로 저장하면 나만 볼 수 있고 다음 접속 때 자동으로 불러옵니다.")
    edited = st.data_editor(
        st.session_state["rb_table"],
        key=f"rb_editor_{version}",
        hide_index=True,
        use_container_width=True,
        disabled=["티커", "종목명"],
        column_config={
            "현재 수량": st.column_config.NumberColumn("현재 수량(주)", min_value=0, step=1, format="%d"),
            "목표 비중(%)": st.column_config.NumberColumn("목표 비중(%)", min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
        },
    ).fillna(0)

    current_holdings = {row["티커"]: int(row["현재 수량"]) for _, row in edited.iterrows()}
    target_weights = {row["티커"]: float(row["목표 비중(%)"]) / 100 for _, row in edited.iterrows()}
    total_pct = edited["목표 비중(%)"].sum()
    if total_pct == 0:
        st.error("목표 비중 합계가 0%입니다. 목표 비중을 입력하세요.")
    elif abs(total_pct - 100) > 0.05:
        st.warning(f"목표 비중 합계가 {total_pct:.1f}%입니다. 리밸런싱 가이드는 합계가 100%가 되도록 비율에 맞춰 계산합니다.")
    else:
        st.caption(f"목표 비중 합계: {total_pct:.1f}%")

    row_controls(
        "rb_table", "rb_version", edited,
        lambda t: {"티커": t, "종목명": ticker_name(t), "현재 수량": 0, "목표 비중(%)": 0.0},
        "rb",
    )

    if st.button("내 보유 수량 저장", key="save_holdings_button"):
        try:
            ps.save_holdings(user_store, current_holdings)
            st.success("보유 수량을 저장했습니다. 다음에 접속하면 자동으로 불러옵니다.")
        except ps.StoreError as e:
            st.error(f"저장 실패: {e}")

    if st.button("리밸런싱 가이드 생성", key="rebalancing_button"):
        with st.spinner("리밸런싱 가이드를 생성 중입니다..."):
            try:
                # 현재 주가 가져오기
                tickers_for_prices = list(set(list(current_holdings.keys()) + list(target_weights.keys())))
                current_prices = rg.get_current_prices(tickers_for_prices)
                
                if not current_prices:
                    st.error("현재 주가를 가져오지 못했습니다.")
                elif sum(current_holdings.values()) == 0:
                    st.warning("보유 수량이 모두 0입니다. 현재 보유 수량을 입력한 뒤 다시 생성하세요.")
                elif sum(target_weights.values()) == 0:
                    st.error("목표 비중 합계가 0%입니다. 목표 비중을 입력한 뒤 다시 생성하세요.")
                else:
                    # 리밸런싱 가이드 생성
                    rebalancing_df, total_value, cash_needed = rg.calculate_rebalancing_guide(
                        current_holdings, target_weights, current_prices
                    )
                    
                    # 거래 비용 계산
                    transaction_cost = rg.calculate_rebalancing_cost(
                        current_holdings, target_weights, current_prices
                    )
                    
                    # 요약 정보
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("포트폴리오 총 가치", f"{total_value:,.0f}원")
                    col2.metric("필요한 현금", f"{max(0, cash_needed):,.0f}원")
                    col3.metric("예상 거래 비용", f"{transaction_cost:,.0f}원")
                    col4.metric("순 현금 필요", f"{max(0, cash_needed) + transaction_cost:,.0f}원")
                    
                    rebalancing_df.insert(1, '종목명', rebalancing_df['Ticker'].map(TICKER_NAMES).fillna(rebalancing_df['Ticker']))

                    st.subheader("리밸런싱 액션 테이블")
                    st.dataframe(rebalancing_df, use_container_width=True)

                    # 매수/매도 분류
                    st.subheader("거래 요약")
                    buy_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] > 0]
                    sell_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] < 0]

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**매수 종목**: {len(buy_actions)}개")
                        if len(buy_actions) > 0:
                            st.dataframe(buy_actions[['Ticker', '종목명', 'Shares to Buy/Sell', 'Current Price']], use_container_width=True)

                    with col2:
                        st.write(f"**매도 종목**: {len(sell_actions)}개")
                        if len(sell_actions) > 0:
                            st.dataframe(sell_actions[['Ticker', '종목명', 'Shares to Buy/Sell', 'Current Price']], use_container_width=True)
                    
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
    else:
        st.info("현재 보유 수량과 목표 비중을 입력하고 '리밸런싱 가이드 생성' 버튼을 눌러주세요.")


# ============ TAB 4: 포트폴리오 비교 ============
with tab4:
    st.header("저장된 포트폴리오 성과 비교")
    st.caption(f"저장소: {store.label}")
    if not store.persistent:
        st.warning("GitHub 저장소가 설정되지 않아 로컬 파일에 저장 중입니다. Streamlit Cloud에서는 앱이 재시작되면 사라지니, "
                   "Secrets에 GITHUB_TOKEN / GITHUB_REPO를 설정하거나 아래 '백업/복원'으로 JSON을 내려받아 보관하세요.")
    if st.session_state.get("store_error"):
        st.error(f"저장소 읽기 실패: {st.session_state['store_error']}")

    if st.button("저장소에서 다시 불러오기", key="reload_portfolios"):
        refresh_saved_portfolios()
        st.rerun()

    saved = st.session_state["saved_portfolios"]

    if not saved:
        st.info("저장된 포트폴리오가 없습니다. '사용자 정의 백테스트' 탭에서 비중을 입력하고 '현재 구성 저장'을 눌러 추가하세요.")
    else:
        names = {p["id"]: p["name"] for p in saved}
        labels = {p["id"]: f"{p['name']} · {p.get('owner_name') or '작성자 없음'}" for p in saved}
        mine = {p["id"]: p["name"] for p in saved if ps.can_modify(p, identity.key)}

        with st.expander(f"저장된 포트폴리오 구성 ({len(saved)}개)"):
            rows = []
            for p in saved:
                for t, w in p["weights"].items():
                    rows.append({"포트폴리오": p["name"], "작성자": p.get("owner_name") or "-", "티커": t, "종목명": TICKER_NAMES.get(t, t), "비중": f"{w:.1%}"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        selected = st.multiselect("비교할 포트폴리오", list(names), default=list(names)[:4],
                                  format_func=labels.get, key="compare_selected")

        c1, c2, c3, c4 = st.columns(4)
        cmp_start = c1.date_input("시작일", datetime.now() - timedelta(days=365*2), key="cmp_start")
        cmp_end = c2.date_input("종료일", datetime.now(), key="cmp_end")
        cmp_capital = c3.number_input("초기 자본 (원)", value=10000000, step=1000000, key="cmp_capital")
        cmp_freq = c4.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=2, key="cmp_rebalance")
        if cmp_freq == "None": cmp_freq = None

        if st.button("비교 실행", key="compare_button"):
            chosen = [p for p in saved if p["id"] in selected]
            if len(chosen) < 1:
                st.error("비교할 포트폴리오를 선택하세요.")
            else:
                with st.spinner("백테스트 중입니다..."):
                    try:
                        all_tickers = tuple(sorted({t for p in chosen for t in p["tickers"]}))
                        prices = load_prices(all_tickers, cmp_start, cmp_end)
                        curves, metric_rows = {}, []
                        for p in chosen:
                            missing = [t for t in p["tickers"] if t not in prices.columns]
                            if missing:
                                st.warning(f"'{p['name']}': 데이터를 받지 못한 티커가 있어 제외했습니다 ({', '.join(missing)})")
                                continue
                            sub = prices[p["tickers"]].dropna()
                            if len(sub) < 2:
                                st.warning(f"'{p['name']}': 겹치는 거래일 데이터가 부족해 제외했습니다.")
                                continue
                            history = re.backtest_rebalancing(sub, p["weights"], cmp_freq, cmp_capital)
                            m = re.calculate_metrics(history)
                            curves[p["name"]] = history["Portfolio Value"]
                            metric_rows.append({
                                "포트폴리오": p["name"],
                                "기간": f"{sub.index[0]:%Y-%m-%d} ~ {sub.index[-1]:%Y-%m-%d}",
                                "총 수익률": f"{m['Total Return']:.2%}",
                                "연환산 수익률": f"{m['Annualized Return']:.2%}",
                                "연환산 변동성": f"{m['Annualized Volatility']:.2%}",
                                "샤프": f"{m['Sharpe Ratio']:.2f}",
                                "MDD": f"{m['Max Drawdown']:.2%}",
                                "최종 가치(원)": f"{history['Portfolio Value'].iloc[-1]:,.0f}",
                            })
                        if not curves:
                            st.error("비교할 수 있는 포트폴리오가 없습니다.")
                        else:
                            st.subheader("성과 지표")
                            st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)
                            st.subheader("포트폴리오 가치 추이")
                            fig = px.line(pd.DataFrame(curves), labels={"value": "포트폴리오 가치(원)", "variable": "포트폴리오"})
                            st.plotly_chart(fig, use_container_width=True)
                            st.caption("종목별 상장일이 달라 포트폴리오마다 실제 비교 기간이 다를 수 있습니다(위 '기간' 열 참고).")
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")

        with st.expander("삭제 (내가 만든 포트폴리오만)"):
            to_delete = st.multiselect("삭제할 포트폴리오", list(mine), format_func=mine.get, key="delete_selected")
            if st.button("선택 항목 삭제", key="delete_button") and to_delete:
                try:
                    data = ps.delete_portfolios(store, to_delete, identity.key)
                    st.session_state["saved_portfolios"] = data["portfolios"]
                    st.success(f"{len(to_delete)}개 삭제했습니다.")
                    st.rerun()
                except ps.StoreError as e:
                    st.error(f"삭제 실패: {e}")

    with st.expander("백업/복원 (JSON)"):
        st.download_button(
            "JSON 백업 다운로드",
            data=json.dumps({"portfolios": saved}, ensure_ascii=False, indent=2),
            file_name="portfolios.json",
            mime="application/json",
            key="backup_download",
        )
        uploaded = st.file_uploader("백업 JSON 불러오기 (id가 같으면 교체, 없으면 추가)", type="json", key="backup_upload")
        if uploaded is not None and st.button("가져오기", key="import_button"):
            try:
                incoming = ps.validate_import(json.load(uploaded))
                data, skipped = ps.import_portfolios(store, incoming, identity.key, identity.name)
                st.session_state["saved_portfolios"] = data["portfolios"]
                st.success(f"{len(incoming) - skipped}개를 가져왔습니다." + (f" (다른 사용자 소유 {skipped}개는 건너뜀)" if skipped else ""))
                st.rerun()
            except (ps.StoreError, json.JSONDecodeError) as e:
                st.error(f"가져오기 실패: {e}")
