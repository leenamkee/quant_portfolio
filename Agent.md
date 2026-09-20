# Agent.md

이 저장소에서 작업하는 AI 에이전트(및 개발자)를 위한 프로젝트 가이드.

## 프로젝트 개요

Streamlit 기반 퀀트 포트폴리오 매니저. `yfinance`로 시세를 받아 포트폴리오 최적화, 리밸런싱 백테스트, 보유 수량 기반 리밸런싱 가이드를 제공한다. Streamlit Community Cloud에 배포해 개인용(1인)으로 사용한다. UI 문구, 주석, docstring은 모두 한국어다.

현재 기본 포트폴리오는 **DC형 퇴직연금 계좌**용 국내 상장 ETF 6종목이다 (위험자산 70% 한도 준수, 아래 "도메인 규칙" 참고).

## 실행

```bash
pip install -r requirements.txt
streamlit run app_advanced.py   # 메인 앱 (3개 탭)
streamlit run app.py            # 초기 단일 페이지 버전
```

- devcontainer(`.devcontainer/devcontainer.json`)는 `app_advanced.py`를 8501 포트로 자동 실행한다.
- 테스트 스위트, 린터 설정은 없다. 변경 후에는 `python -m py_compile <파일>`로 문법을 확인하고, 가능하면 앱을 직접 띄워 확인한다.
- `requirements.txt`는 UTF-16(BOM) 인코딩이다. 수정 시 인코딩을 유지하거나, 변경하면 pip 설치가 되는지 확인한다.

## 파일 구조와 역할

| 파일 | 역할 |
| --- | --- |
| `app_advanced.py` | 메인 Streamlit 앱. 탭1 자동 최적화 / 탭2 사용자 정의 백테스트 / 탭3 리밸런싱 가이드 |
| `app.py` | 초기 버전 단일 페이지 앱 (탭1과 유사, 이후 기능 미반영 부분 있음) |
| `portfolio_engine.py` | 시세 조회(`get_stock_data`), 최적화(`optimize_portfolio`: max_sharpe / min_volatility / equal_weight / target_weight), 목표 비중(`DEFAULT_TARGET_WEIGHTS`), 이산 매수 수량(`get_discrete_allocation`) |
| `rebalance_engine.py` | 리밸런싱 백테스트(`backtest_rebalancing`)와 성과 지표(`calculate_metrics`) |
| `custom_backtest.py` | 사용자 정의 비중 백테스트. 누락 티커 제거·정규화 후 `rebalance_engine.backtest_rebalancing`에 위임 |
| `rebalancing_guide.py` | 현재가 조회, 보유 수량 대비 매수/매도 수량 계산, 거래 비용 계산 |
| `docs/` | 리서치/설계 문서 (예: `portfolio-storage-research.md`) |
| `worklog.md` | 작업 기록 (아래 "작업 규칙" 참고) |
| `*.md` (루트, 한글 파일명) | 초기 사용 가이드 문서 |

## 데이터 흐름

```
티커 입력 → portfolio_engine.get_stock_data (yfinance 'Close')
        → optimize_portfolio → weights {ticker: weight}
        → rebalance_engine.backtest_rebalancing → history(DataFrame)
        → calculate_metrics → 총수익률/CAGR/변동성/샤프/MDD
```

탭2는 `custom_backtest`, 탭3은 `rebalancing_guide`를 사용한다.

## 기본 종목 (KRX, yfinance 접미사 `.KS`)

| 티커 | 종목명 | 분류 | 목표 비중 |
| --- | --- | --- | --- |
| 273130.KS | KODEX 종합채권(AA-이상)액티브 | 안전자산 | 30% |
| 360750.KS | TIGER 미국S&P500 | 위험자산 | 25% |
| 284430.KS | KODEX 200미국채혼합50 | 위험자산 | 13% |
| 441640.KS | KODEX 미국배당커버드콜액티브 | 위험자산 | 13% |
| 458730.KS | TIGER 미국배당다우존스 | 위험자산 | 12% |
| 411060.KS | ACE KRX 금현물 | 위험자산 | 7% |

## 도메인 규칙 (중요)

- **DC/IRP 위험자산 70% 룰**: 위험자산 합계 ≤ 70%, 안전자산 ≥ 30%. 주식 비중 40% 초과 펀드/ETF, 금 현물 ETF는 위험자산이다. `284430`(혼합50, 주식 약 50%)도 위험자산이므로 안전자산 슬롯은 순수 채권 ETF(`273130`)가 담당한다. 비중을 바꿀 때는 이 제약을 깨지 않는지 반드시 확인한다.
- 국내 ETF는 KOSPI 상장이므로 yfinance 티커에 `.KS`를 붙인다.
- 통화는 원화(KRW)다. 초기 자본 입력은 원 단위 기본값 10,000,000.

## 수정 시 주의사항 (알려진 함정)

- **종목명·목표 비중·기본 티커의 단일 출처는 `portfolio_engine.py`**(`TICKER_NAMES`, `DEFAULT_TARGET_WEIGHTS`)다. 앱의 기본 티커 입력, 탭2 비중 기본값, 탭3 목표 비중 기본 텍스트는 모두 여기서 만들어지므로 종목/비중을 바꿀 때는 이 두 딕셔너리만 수정한다(비중은 소수, 합 1.0).
- 탭3의 `holdings_input` 기본값은 **사용자의 실제 보유 수량**이다. 임의로 바꾸지 않는다. 목표 비중에만 있고 보유가 없는 티커는 0주로 계산되어 매수 안내가 나온다.
- `target_weight` 방법은 입력 티커가 전부 `DEFAULT_TARGET_WEIGHTS`에 있어야 그 비중을 쓰고, 아니면 균등 가중으로 대체된다.
- 화폐 단위는 원(KRW)이다. 금액을 표시할 때 `$`를 쓰지 말고 `{값:,.0f}원` 형식을 따른다.
- 리밸런싱 날짜는 `rebalance_engine.get_rebalance_dates`가 각 기간의 마지막 **실제 거래일**로 만든다(`resample().last().index`는 달력 말일이라 휴장일과 어긋나 리밸런싱이 누락되므로 쓰지 않는다). `backtest_rebalancing`은 비중 합이 1이 아니어도 정규화해서 쓴다.
- 탭3 매수/매도 분류는 `Shares to Buy/Sell`의 숫자 부호(>0, <0)로 판단한다. 문자열 비교를 쓰지 않는다.
- `rebalancing_guide.get_current_prices`는 최신일이 아니라 직전 거래일(`iloc[-2]`) 종가를 사용한다.
- `pypfopt`의 max_sharpe는 과거 평균 수익률에 민감해 특정 종목에 쏠린 비중을 낸다. 결과를 그대로 신뢰하지 말고 참고용으로 다룬다.

## 배포 (Streamlit Community Cloud)

- 로컬 디스크는 휘발성이다. 재부팅/재배포 시 앱이 쓴 파일은 사라지므로 **파일에 저장하는 방식의 영속화는 동작하지 않는다.** 포트폴리오 저장 기능은 `docs/portfolio-storage-research.md`의 설계(GitHub API로 JSON 커밋 + 다운로드/업로드 백업)를 따른다.
- 비밀 값(토큰 등)은 `st.secrets`(Cloud의 App settings → Secrets)로만 다루고 저장소에 커밋하지 않는다.

## 작업 규칙

- **모든 작업 내용을 `worklog.md`에 기록한다.** 작업을 마칠 때마다(커밋 전에) 날짜 섹션 아래에 무엇을·왜 바꿨는지, 확인한 방법, 남은 이슈를 추가하고 같은 커밋에 포함한다. 날짜는 최신이 위로 오도록 쓴다. 코드 변경이 없는 조사/문서 작업도 기록한다.
- 코드 주석/문구는 기존 스타일대로 한국어를 사용한다. 주석은 꼭 필요한 이유(WHY)만 짧게 쓴다.
- 커밋 메시지는 영어로, 변경의 이유를 중심으로 쓴다. 푸시는 사용자가 요청할 때만 한다.
- 요청 범위를 넘는 리팩터링은 하지 않는다 (예: 중복 모듈 통합은 별도 요청이 있을 때).
