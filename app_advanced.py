import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import portfolio_engine as pe
import rebalance_engine as re
import custom_backtest as cb
import rebalancing_guide as rg

st.set_page_config(page_title="Quant Portfolio Manager", layout="wide")

st.title("📈 퀀트 포트폴리오 구성 및 리밸런싱")
st.markdown("""
이 앱은 주식 포트폴리오를 최적화하고 리밸런싱 전략에 따른 성과를 시뮬레이션합니다.
또한 사용자 정의 포트폴리오의 백테스트와 현재 보유 수량 기반 리밸런싱 가이드를 제공합니다.
""")

# 탭 구성
tab1, tab2, tab3 = st.tabs(["자동 최적화", "사용자 정의 백테스트", "리밸런싱 가이드"])

# ============ TAB 1: 자동 최적화 ============
with tab1:
    st.header("자동 포트폴리오 최적화")
    
    # 사이드바 설정
    st.sidebar.header("⚙️ 자동 최적화 설정")
    tickers_input = st.sidebar.text_input("티커 입력 (쉼표로 구분)", "AAPL, MSFT, GOOGL, AMZN, TSLA", key="tab1_tickers")
    tickers = [t.strip() for t in tickers_input.split(",")]
    
    start_date = st.sidebar.date_input("시작일", datetime.now() - timedelta(days=365*2), key="tab1_start")
    end_date = st.sidebar.date_input("종료일", datetime.now(), key="tab1_end")
    
    initial_capital = st.sidebar.number_input("초기 자본 ($)", value=10000, step=1000, key="tab1_capital")
    rebalance_freq = st.sidebar.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=1, key="tab1_rebalance")
    if rebalance_freq == "None": rebalance_freq = None
    
    opt_method = st.sidebar.selectbox("최적화 방법", ["max_sharpe", "min_volatility", "equal_weight"], key="tab1_method")
    
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
                        st.write(f"남은 현금: ${leftover:.2f}")
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
    st.markdown("원하는 종목과 비중을 입력하여 백테스트를 수행합니다.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("포트폴리오 구성")
        tickers_custom = st.text_input("티커 입력 (쉼표로 구분)", "AAPL, MSFT, GOOGL", key="custom_tickers")
        tickers_list = [t.strip() for t in tickers_custom.split(",")]
        
        weights_custom = {}
        st.write("각 종목의 비중을 입력하세요 (합계 100% 필요):")
        
        cols = st.columns(len(tickers_list))
        for idx, ticker in enumerate(tickers_list):
            with cols[idx]:
                weights_custom[ticker] = st.number_input(
                    f"{ticker} 비중 (%)",
                    value=100/len(tickers_list),
                    step=1.0,
                    key=f"weight_{ticker}"
                ) / 100
    
    with col2:
        st.subheader("백테스트 설정")
        custom_start_date = st.date_input("시작일", datetime.now() - timedelta(days=365*2), key="custom_start")
        custom_end_date = st.date_input("종료일", datetime.now(), key="custom_end")
        custom_initial_capital = st.number_input("초기 자본 ($)", value=10000, step=1000, key="custom_capital")
        custom_rebalance_freq = st.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=1, key="custom_rebalance")
        if custom_rebalance_freq == "None": custom_rebalance_freq = None
    
    if st.button("백테스트 실행", key="custom_button"):
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
                        fig_pie = px.pie(weight_df, values='Weight', names='Ticker', title="Portfolio Weights")
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
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("현재 보유 수량")
        holdings_input = st.text_area(
            "현재 보유 수량 (형식: TICKER:SHARES, 한 줄에 하나씩)",
            "AAPL:10\nMSFT:5\nGOOGL:3",
            key="holdings_input"
        )
        
        current_holdings = {}
        try:
            for line in holdings_input.strip().split('\n'):
                if line.strip():
                    ticker, shares = line.split(':')
                    current_holdings[ticker.strip()] = int(shares.strip())
        except:
            st.error("입력 형식이 올바르지 않습니다. (예: AAPL:10)")
    
    with col2:
        st.subheader("목표 비중")
        weights_input = st.text_area(
            "목표 비중 (형식: TICKER:WEIGHT%, 한 줄에 하나씩)",
            "AAPL:50\nMSFT:30\nGOOGL:20",
            key="weights_input"
        )
        
        target_weights = {}
        try:
            for line in weights_input.strip().split('\n'):
                if line.strip():
                    ticker, weight = line.split(':')
                    target_weights[ticker.strip()] = float(weight.strip().rstrip('%')) / 100
        except:
            st.error("입력 형식이 올바르지 않습니다. (예: AAPL:50)")
    
    if st.button("리밸런싱 가이드 생성", key="rebalancing_button"):
        with st.spinner("리밸런싱 가이드를 생성 중입니다..."):
            try:
                # 현재 주가 가져오기
                tickers_for_prices = list(set(list(current_holdings.keys()) + list(target_weights.keys())))
                current_prices = rg.get_current_prices(tickers_for_prices)
                
                if not current_prices:
                    st.error("현재 주가를 가져오지 못했습니다.")
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
                    col1.metric("포트폴리오 총 가치", f"${total_value:.2f}")
                    col2.metric("필요한 현금", f"${max(0, cash_needed):.2f}")
                    col3.metric("예상 거래 비용", f"${transaction_cost:.2f}")
                    col4.metric("순 현금 필요", f"${max(0, cash_needed) + transaction_cost:.2f}")
                    
                    st.subheader("리밸런싱 액션 테이블")
                    st.dataframe(rebalancing_df, use_container_width=True)
                    
                    # 매수/매도 분류
                    st.subheader("거래 요약")
                    buy_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'].astype(str).str.contains('-') == False]
                    buy_actions = buy_actions[buy_actions['Shares to Buy/Sell'] != '0']
                    
                    sell_actions = rebalancing_df[rebalancing_df['Shares to Buy/Sell'].astype(str).str.contains('-')]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**매수 종목**: {len(buy_actions)}개")
                        if len(buy_actions) > 0:
                            st.dataframe(buy_actions[['Ticker', 'Shares to Buy/Sell', 'Current Price']], use_container_width=True)
                    
                    with col2:
                        st.write(f"**매도 종목**: {len(sell_actions)}개")
                        if len(sell_actions) > 0:
                            st.dataframe(sell_actions[['Ticker', 'Shares to Buy/Sell', 'Current Price']], use_container_width=True)
                    
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
    else:
        st.info("현재 보유 수량과 목표 비중을 입력하고 '리밸런싱 가이드 생성' 버튼을 눌러주세요.")
