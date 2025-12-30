# 퀀트 포트폴리오 매니저 (Streamlit)

이 애플리케이션은 파이썬의 `Streamlit`, `yfinance`, `PyPortfolioOpt` 라이브러리를 사용하여 퀀트 투자 포트폴리오를 구성하고 리밸런싱 성과를 시뮬레이션합니다.

## 주요 기능
1. **데이터 수집**: Yahoo Finance API를 통해 실시간 주가 데이터를 가져옵니다.
2. **포트폴리오 최적화**:
   - **Max Sharpe**: 샤프 지수 최대화 (위험 대비 수익률 최적화)
   - **Min Volatility**: 변동성 최소화
   - **Equal Weight**: 동일 가중치 배분
3. **리밸런싱 시뮬레이션**: 월간(M), 분기(Q), 연간(Y) 주기에 따른 리밸런싱 백테스트를 수행합니다.
4. **성과 지표**: 총 수익률, 연환산 수익률, 샤프 지수, 최대 낙폭(MDD) 등을 계산합니다.
5. **시각화**: 포트폴리오 가치 추이, 자산 배분 비중, 상관관계 행렬 등을 차트로 제공합니다.

## 실행 방법
1. 필요한 패키지를 설치합니다:
   ```bash
   pip install streamlit yfinance pandas numpy plotly PyPortfolioOpt quantstats matplotlib
   ```
2. 앱을 실행합니다:
   ```bash
   streamlit run app.py
   ```

## 파일 구조
- `app.py`: 메인 Streamlit UI 및 통합 로직
- `portfolio_engine.py`: 데이터 수집 및 포트폴리오 최적화 엔진
- `rebalance_engine.py`: 리밸런싱 백테스트 및 성과 지표 계산 엔진
