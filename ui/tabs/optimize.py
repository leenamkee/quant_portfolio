"""탭1: 자동 최적화. 티커를 입력하면 통계적으로 비중을 계산해 백테스트한다."""
import streamlit as st

import market_data as md
import portfolio_engine as pe
import rebalance_engine as backtest_engine
from alignment import align_prices
from config import DEFAULT_TARGET_WEIGHTS, SHARPE_LABEL, format_sharpe
from ui.charts import allocation_chart, performance_charts, price_data_section
from ui.components import backtest_settings, show_analysis_window, show_error, ticker_name

DEFAULT_TICKERS = ", ".join(sorted(DEFAULT_TARGET_WEIGHTS))
OPTIMIZATION_METHODS = ["max_sharpe", "min_volatility", "equal_weight", "target_weight"]


def render(ctx):
    st.header("자동 포트폴리오 최적화")

    tickers_input = st.text_input("티커 입력 (쉼표로 구분)", DEFAULT_TICKERS, key="tab1_tickers")
    tickers = [t.strip() for t in tickers_input.split(",")]

    start_date, end_date, initial_capital, rebalance_freq = backtest_settings("tab1")
    opt_method = st.selectbox("최적화 방법", OPTIMIZATION_METHODS, key="tab1_method")

    if not st.button("분석 실행", key="tab1_button"):
        st.info("설정을 완료하고 '분석 실행' 버튼을 눌러주세요.")
        return

    with st.spinner("데이터를 가져오고 분석 중입니다..."):
        try:
            data = md.get_prices(tickers, start_date, end_date)
            aligned = align_prices(data)
            data = aligned.prices
            show_analysis_window(aligned, start_date)

            weights = pe.optimize_portfolio(data, method=opt_method)
            history = backtest_engine.backtest_rebalancing(data, weights, rebalance_freq, initial_capital)
            metrics = backtest_engine.calculate_metrics(history)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("총 수익률", f"{metrics['Total Return']:.2%}")
            col2.metric("연환산 수익률", f"{metrics['Annualized Return']:.2%}")
            col3.metric(SHARPE_LABEL, format_sharpe(metrics['Sharpe Ratio']))
            col4.metric("최대 낙폭 (MDD)", f"{metrics['Max Drawdown']:.2%}")

            tab_perf, tab_alloc, tab_data = st.tabs(["성과 분석", "자산 배분", "데이터"])

            with tab_perf:
                performance_charts(history, metrics)

            with tab_alloc:
                allocation_chart(weights, ticker_name, f"최적화된 자산 배분 ({opt_method})")

                latest_prices = data.iloc[-1]
                allocation, leftover = pe.get_discrete_allocation(weights, latest_prices, initial_capital)
                st.subheader("추천 매수 수량 (현재가 기준)")
                st.write(f"남은 현금: {leftover:,.0f}원")
                st.table([{"티커": t, "종목명": ticker_name(t), "수량": n} for t, n in allocation.items()])

            with tab_data:
                price_data_section(data)
        except Exception as e:
            show_error(e)
