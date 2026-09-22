"""성과/배분/상관관계 차트. 예전에는 app.py, 탭1, 탭2에 같은 코드가 3벌 있었다."""
import pandas as pd
import plotly.express as px
import streamlit as st

from alignment import daily_returns


def performance_charts(history, metrics):
    """포트폴리오 가치 추이, 낙폭, 일간 수익률 분포. history에 표시용 열을 추가한다."""
    history['일간 수익률'] = history['Portfolio Value'].pct_change()

    st.subheader("포트폴리오 가치 추이")
    fig_line = px.line(history, y="Portfolio Value",
                        title=f"포트폴리오 가치 추이 (연환산 수익률: {metrics['Annualized Return']:.2%})")
    st.plotly_chart(fig_line, width="stretch")

    st.subheader("낙폭(Drawdown) 시각화")
    history['누적 최고'] = history['Portfolio Value'].cummax()
    history['낙폭'] = (history['Portfolio Value'] - history['누적 최고']) / history['누적 최고']
    fig_dd = px.area(history, y="낙폭", title=f"낙폭 추이 (최대 낙폭: {metrics['Max Drawdown']:.2%})",
                      color_discrete_sequence=["red"])
    fig_dd.update_yaxes(tickformat=".2%")
    st.plotly_chart(fig_dd, width="stretch")

    st.subheader("일간 수익률 분포")
    fig_hist = px.histogram(history, x="일간 수익률", nbins=50, title="일간 수익률 분포")
    st.plotly_chart(fig_hist, width="stretch")


def allocation_chart(weights, ticker_name, title="자산 배분"):
    """{티커: 비중} → 종목명이 붙은 파이차트 + 표. 완성된 표를 돌려준다(호출부가 추가로 쓸 수 있게)."""
    df = pd.DataFrame(list(weights.items()), columns=["티커", "비중"])
    df.insert(1, "종목명", df["티커"].map(ticker_name))
    st.subheader(title)
    fig_pie = px.pie(df, values="비중", names="종목명", title=title)
    st.plotly_chart(fig_pie, width="stretch")
    st.table(df.style.format({"비중": "{:.2%}"}))
    return df


def price_data_section(data):
    """종가 표와 상관관계 히트맵. data는 이미 공통 관측 구간으로 정렬된 가격이어야 한다."""
    st.subheader("주가 데이터 (종가)")
    st.dataframe(data)

    st.subheader("자산 간 상관관계")
    corr = daily_returns(data).corr()
    fig_corr = px.imshow(corr, text_auto=True, title="자산 간 상관관계")
    st.plotly_chart(fig_corr, width="stretch")
