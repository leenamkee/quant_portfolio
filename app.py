import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import portfolio_engine as pe
import rebalance_engine as re

st.set_page_config(page_title="Quant Portfolio Manager", layout="wide")

st.title("📈 퀀트 포트폴리오 구성 및 리밸런싱")
st.markdown("""
이 앱은 주식 포트폴리오를 최적화하고 리밸런싱 전략에 따른 성과를 시뮬레이션합니다.
""")

# 사이드바 설정
st.sidebar.header("설정")
tickers_input = st.sidebar.text_input("티커 입력 (쉼표로 구분)", "AAPL, MSFT, GOOGL, AMZN, TSLA")
tickers = [t.strip() for t in tickers_input.split(",")]

start_date = st.sidebar.date_input("시작일", datetime.now() - timedelta(days=365*2))
end_date = st.sidebar.date_input("종료일", datetime.now())

initial_capital = st.sidebar.number_input("초기 자본 ($)", value=10000, step=1000)
rebalance_freq = st.sidebar.selectbox("리밸런싱 주기", ["None", "M", "Q", "Y"], index=1)
if rebalance_freq == "None": rebalance_freq = None

opt_method = st.sidebar.selectbox("최적화 방법", ["max_sharpe", "min_volatility", "equal_weight"])

if st.sidebar.button("분석 실행"):
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
                tab1, tab2, tab3 = st.tabs(["성과 분석", "자산 배분", "데이터"])
                
                with tab1:
                    st.subheader("포트폴리오 가치 추이 (CAGR 반영)")
                    # CAGR 계산을 위한 보조 데이터
                    history['Daily Return'] = history['Portfolio Value'].pct_change()
                    
                    # 포트폴리오 가치 차트
                    fig_line = px.line(history, y="Portfolio Value", title=f"Portfolio Value Over Time (CAGR: {metrics['Annualized Return']:.2%})")
                    st.plotly_chart(fig_line, use_container_width=True)
                    
                    # MDD 차트 추가
                    st.subheader("낙폭 (Drawdown) 시각화")
                    history['Cumulative Max'] = history['Portfolio Value'].cummax()
                    history['Drawdown'] = (history['Portfolio Value'] - history['Cumulative Max']) / history['Cumulative Max']
                    
                    fig_dd = px.area(history, y="Drawdown", title=f"Portfolio Drawdown (MDD: {metrics['Max Drawdown']:.2%})", color_discrete_sequence=['red'])
                    fig_dd.update_yaxes(tickformat=".2%")
                    st.plotly_chart(fig_dd, use_container_width=True)

                    st.subheader("일간 수익률 분포")
                    fig_hist = px.histogram(history, x="Daily Return", nbins=50, title="Daily Return Distribution")
                    st.plotly_chart(fig_hist, use_container_width=True)
                
                with tab2:
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

                with tab3:
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
