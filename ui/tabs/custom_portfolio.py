"""탭2: 사용자 정의 백테스트. 표에서 비중을 입력해 백테스트하고, 포트폴리오를 저장/불러온다."""
import pandas as pd
import streamlit as st

import market_data as md
import rebalance_engine as backtest_engine
import storage as ps
from alignment import align_prices
from config import DEFAULT_TARGET_WEIGHTS, SHARPE_LABEL, format_sharpe
from ui import state
from ui.charts import allocation_chart, performance_charts, price_data_section
from ui.components import backtest_settings, row_controls, show_analysis_window, show_error, ticker_name, \
    ticker_table_editor

TARGET_WEIGHTS_PCT = {t: round(w * 100, 1) for t, w in DEFAULT_TARGET_WEIGHTS.items()}


def _default_table():
    tickers = list(DEFAULT_TARGET_WEIGHTS)
    return pd.DataFrame({
        "티커": tickers,
        "종목명": [ticker_name(t) for t in tickers],
        "비중(%)": [float(TARGET_WEIGHTS_PCT[t]) for t in tickers],
    })


def _render_load_controls(ctx):
    saved_list = st.session_state[state.SAVED_PORTFOLIOS]
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
        st.session_state[state.BT_TABLE] = pd.DataFrame({
            "티커": chosen["tickers"],
            "종목명": [ticker_name(t) for t in chosen["tickers"]],
            "비중(%)": [round(chosen["weights"][t] * 100, 4) for t in chosen["tickers"]],
        })
        st.session_state[state.BT_VERSION] += 1
        st.session_state[state.BT_LOADED] = saved_labels[load_id]
        mine = ps.can_modify(chosen, ctx.identity.key)
        st.session_state[state.SAVE_NAME] = chosen["name"] if mine else f"{chosen['name']} (내 복사본)"
        st.rerun()
    if load_col3.button("기본 구성으로 초기화", key="bt_reset_button"):
        st.session_state[state.BT_TABLE] = _default_table()
        st.session_state[state.BT_VERSION] += 1
        st.session_state.pop(state.BT_LOADED, None)
        st.rerun()


def _render_save_controls(ctx, weights_custom):
    save_col1, save_col2 = st.columns([3, 1])
    save_name = save_col1.text_input("포트폴리오 이름 (같은 이름이면 덮어씁니다)", key=state.SAVE_NAME, placeholder="예: DC 기본안")
    save_col2.write("")
    if not save_col2.button("현재 구성 저장", key="save_portfolio_button"):
        return
    total_weight = sum(weights_custom.values())
    if not save_name.strip():
        st.error("저장할 이름을 입력하세요.")
        return
    if abs(total_weight - 1) > 0.005:
        st.error(f"비중 합계가 {total_weight:.1%}입니다. 100%로 맞춘 뒤 저장하세요.")
        return
    try:
        data = ps.upsert_portfolio(ctx.store, ps.make_portfolio(save_name, weights_custom, ctx.identity.key, ctx.identity.name))
        st.session_state[state.SAVED_PORTFOLIOS] = data["portfolios"]
        saved_id = next(p["id"] for p in data["portfolios"] if p["name"] == save_name.strip())
        current = [i for i in st.session_state.get(state.COMPARE_SELECTED, []) if i in {p["id"] for p in data["portfolios"]}]
        st.session_state[state.COMPARE_SELECTED] = current + ([saved_id] if saved_id not in current else [])
        st.session_state[state.BT_FLASH] = f"'{save_name.strip()}' 저장 완료 → '포트폴리오 비교' 탭에서 비교할 수 있습니다. ({ctx.store.label})"
        st.rerun()
    except ps.StoreError as e:
        st.error(f"저장 실패: {e}")


def render(ctx):
    st.header("사용자 정의 포트폴리오 백테스트")
    st.markdown("표에서 종목별 비중을 입력해 백테스트합니다. 저장한 포트폴리오를 불러와 수정하거나, 새로 구성해 저장할 수 있습니다.")
    if st.session_state.get(state.BT_FLASH):
        st.success(st.session_state.pop(state.BT_FLASH))

    state.ensure(state.BT_TABLE, _default_table)
    state.ensure(state.BT_VERSION, lambda: 0)

    _render_load_controls(ctx)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("포트폴리오 구성")
        if st.session_state.get(state.BT_LOADED):
            st.caption(f"불러온 포트폴리오: {st.session_state[state.BT_LOADED]} (표를 수정해도 저장하기 전에는 원본이 바뀌지 않습니다)")
        edited = ticker_table_editor(
            state.BT_TABLE, state.BT_VERSION,
            {"비중(%)": st.column_config.NumberColumn("비중(%)", min_value=0.0, max_value=100.0, step=0.5, format="%.1f")},
            "bt",
        )

        weights_custom = {row["티커"]: float(row["비중(%)"]) / 100 for _, row in edited.iterrows() if row["비중(%)"] > 0}
        tickers_list = list(weights_custom)
        bt_total = edited["비중(%)"].sum()
        if abs(bt_total - 100) > 0.05:
            st.warning(f"비중 합계가 {bt_total:.1f}%입니다. 백테스트는 비율에 맞춰 계산하지만, 저장하려면 100%로 맞추세요.")
        else:
            st.caption(f"비중 합계: {bt_total:.1f}%")

        row_controls(state.BT_TABLE, state.BT_VERSION, edited,
                     lambda t: {"티커": t, "종목명": ticker_name(t), "비중(%)": 0.0}, "bt")

    with col2:
        st.subheader("백테스트 설정")
        start_date, end_date, initial_capital, rebalance_freq = backtest_settings("custom")

    _render_save_controls(ctx, weights_custom)

    run_backtest = st.button("백테스트 실행", key="custom_button")
    if run_backtest and not tickers_list:
        st.error("비중이 0보다 큰 종목이 없습니다. 표에 비중을 입력하세요.")
    elif run_backtest:
        with st.spinner("백테스트 중입니다..."):
            try:
                data = md.get_prices(tickers_list, start_date, end_date)
                aligned = align_prices(data)
                data = aligned.prices
                show_analysis_window(aligned, start_date)

                history = backtest_engine.backtest_custom_portfolio(data, weights_custom, rebalance_freq, initial_capital)
                metrics = backtest_engine.calculate_metrics(history)

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("총 수익률", f"{metrics['Total Return']:.2%}")
                m2.metric("연환산 수익률", f"{metrics['Annualized Return']:.2%}")
                m3.metric(SHARPE_LABEL, format_sharpe(metrics['Sharpe Ratio']))
                m4.metric("최대 낙폭 (MDD)", f"{metrics['Max Drawdown']:.2%}")

                tab_perf, tab_alloc, tab_data = st.tabs(["성과 분석", "자산 배분", "데이터"])

                with tab_perf:
                    performance_charts(history, metrics)

                with tab_alloc:
                    allocation_chart(weights_custom, ticker_name, "포트폴리오 구성")

                with tab_data:
                    price_data_section(data)
            except Exception as e:
                show_error(e)
    else:
        st.info("포트폴리오 설정을 완료하고 '백테스트 실행' 버튼을 눌러주세요.")
