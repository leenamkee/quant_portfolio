"""탭3: 리밸런싱 가이드. 현재 보유 수량과 목표 비중으로 매수/매도 수량을 계산한다."""
import pandas as pd
import streamlit as st

import market_data as md
import rebalancing_guide as rg
import storage as ps
from config import DEFAULT_TARGET_WEIGHTS, TICKER_NAMES
from ui import state
from ui.components import row_controls, show_error, ticker_name, ticker_table_editor

TARGET_WEIGHTS_PCT = {t: round(w * 100, 1) for t, w in DEFAULT_TARGET_WEIGHTS.items()}


def _default_table(user_store):
    try:
        saved_holdings = ps.load_holdings(user_store)
    except ps.StoreError as e:
        saved_holdings = {}
        st.warning(f"저장된 보유 수량을 불러오지 못했습니다: {e}")
    tickers = list(DEFAULT_TARGET_WEIGHTS) + [t for t in saved_holdings if t not in DEFAULT_TARGET_WEIGHTS]
    return pd.DataFrame({
        "티커": tickers,
        "종목명": [ticker_name(t) for t in tickers],
        "현재 수량": [int(saved_holdings.get(t, 0)) for t in tickers],
        "목표 비중(%)": [float(TARGET_WEIGHTS_PCT.get(t, 0.0)) for t in tickers],
    })


def _render_guide(current_holdings, target_weights):
    with st.spinner("리밸런싱 가이드를 생성 중입니다..."):
        try:
            tickers_for_prices = list(dict.fromkeys(list(current_holdings) + list(target_weights)))
            latest = md.fetch_latest_prices(tickers_for_prices)
            current_prices = latest.prices

            if not current_prices:
                st.error(f"현재가를 얻지 못했습니다: {', '.join(latest.missing)}")
                return
            if sum(current_holdings.values()) == 0:
                st.warning("보유 수량이 모두 0입니다. 현재 보유 수량을 입력한 뒤 다시 생성하세요.")
                return
            if sum(target_weights.values()) == 0:
                st.error("목표 비중 합계가 0%입니다. 목표 비중을 입력한 뒤 다시 생성하세요.")
                return

            rebalancing_df, total_value, cash_needed = rg.calculate_rebalancing_guide(
                current_holdings, target_weights, current_prices)
            transaction_cost = rg.calculate_rebalancing_cost(current_holdings, target_weights, current_prices)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("포트폴리오 총 가치", f"{total_value:,.0f}원")
            col2.metric("필요한 현금", f"{max(0, cash_needed):,.0f}원")
            col3.metric("예상 거래 비용", f"{transaction_cost:,.0f}원")
            col4.metric("순 현금 필요", f"{max(0, cash_needed) + transaction_cost:,.0f}원")

            price_dates = latest.distinct_dates()
            st.caption("가격 기준: 마지막 거래일 종가 (" + ", ".join(str(d) for d in price_dates) + ")")
            if len(price_dates) > 1:
                st.warning("종목마다 가격 기준일이 다릅니다: " + ", ".join(f"{t} {d.date()}" for t, d in latest.as_of.items()))
            if latest.missing:
                st.warning(f"현재가를 받지 못한 종목(보유·목표 비중이 없어 계산에는 영향 없음): {', '.join(latest.missing)}")

            rebalancing_df.insert(1, '종목명', rebalancing_df['Ticker'].map(TICKER_NAMES).fillna(rebalancing_df['Ticker']))

            st.subheader("리밸런싱 액션 테이블")
            st.dataframe(rebalancing_df, width="stretch")

            st.subheader("거래 요약")
            buy_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] > 0]
            sell_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'] < 0]

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**매수 종목**: {len(buy_actions)}개")
                if len(buy_actions) > 0:
                    st.dataframe(buy_actions[['Ticker', '종목명', 'Shares to Buy/Sell', 'Current Price']], width="stretch")
            with col2:
                st.write(f"**매도 종목**: {len(sell_actions)}개")
                if len(sell_actions) > 0:
                    st.dataframe(sell_actions[['Ticker', '종목명', 'Shares to Buy/Sell', 'Current Price']], width="stretch")
        except Exception as e:
            show_error(e)


def render(ctx):
    st.header("리밸런싱 가이드")
    st.markdown("현재 보유 수량을 입력하고 목표 비중을 설정하면 리밸런싱 가이드를 제공합니다.")

    state.ensure(state.RB_TABLE, lambda: _default_table(ctx.user_store))
    state.ensure(state.RB_VERSION, lambda: 0)

    st.subheader("현재 수량 · 목표 비중")
    st.caption("표에서 현재 수량(주)과 목표 비중(%)을 직접 수정하세요. 현재 수량은 '내 보유 수량 저장'으로 저장하면 나만 볼 수 있고 다음 접속 때 자동으로 불러옵니다.")
    edited = ticker_table_editor(
        state.RB_TABLE, state.RB_VERSION,
        {
            "현재 수량": st.column_config.NumberColumn("현재 수량(주)", min_value=0, step=1, format="%d"),
            "목표 비중(%)": st.column_config.NumberColumn("목표 비중(%)", min_value=0.0, max_value=100.0, step=0.5, format="%.1f"),
        },
        "rb",
    )

    current_holdings = {row["티커"]: int(row["현재 수량"]) for _, row in edited.iterrows()}
    target_weights = {row["티커"]: float(row["목표 비중(%)"]) / 100 for _, row in edited.iterrows()}
    total_pct = edited["목표 비중(%)"].sum()
    if total_pct == 0:
        st.error("목표 비중 합계가 0%입니다. 목표 비중을 입력하세요.")
    elif abs(total_pct - 100) > 0.05:
        st.warning(f"목표 비중 합계가 {total_pct:.1f}%입니다. 리밸런싱 가이드는 합계가 100%가 되도록 비율에 맞춰 계산합니다.")
    else:
        st.caption(f"목표 비중 합계: {total_pct:.1f}%")

    row_controls(state.RB_TABLE, state.RB_VERSION, edited,
                 lambda t: {"티커": t, "종목명": ticker_name(t), "현재 수량": 0, "목표 비중(%)": 0.0}, "rb")

    if st.button("내 보유 수량 저장", key="save_holdings_button"):
        try:
            ps.save_holdings(ctx.user_store, current_holdings)
            st.success("보유 수량을 저장했습니다. 다음에 접속하면 자동으로 불러옵니다.")
        except ps.StoreError as e:
            st.error(f"저장 실패: {e}")

    if st.button("리밸런싱 가이드 생성", key="rebalancing_button"):
        _render_guide(current_holdings, target_weights)
    else:
        st.info("현재 보유 수량과 목표 비중을 입력하고 '리밸런싱 가이드 생성' 버튼을 눌러주세요.")
