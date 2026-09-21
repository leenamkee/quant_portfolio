# Agent.md

이 저장소에서 작업하는 AI 에이전트(및 개발자)를 위한 프로젝트 가이드.

## 프로젝트 개요

Streamlit 기반 퀀트 포트폴리오 매니저. `yfinance`로 시세를 받아 포트폴리오 최적화, 리밸런싱 백테스트, 보유 수량 기반 리밸런싱 가이드를 제공한다. Streamlit Community Cloud에 배포해 개인용(1인)으로 사용한다. 3~4명이 함께 쓰는 확장 방안은 `docs/multi-user-plan.md`. UI 문구, 주석, docstring은 모두 한국어다.

현재 기본 포트폴리오는 **DC형 퇴직연금 계좌**용 국내 상장 ETF 6종목이다 (위험자산 70% 한도 준수, 아래 "도메인 규칙" 참고).

## 실행

```bash
pip install -r requirements.txt
streamlit run app_advanced.py   # 메인 앱 (4개 탭, 로그인 미설정 시 로컬 개발 모드)
streamlit run app.py            # 초기 단일 페이지 버전
```

- devcontainer(`.devcontainer/devcontainer.json`)는 `app_advanced.py`를 8501 포트로 자동 실행한다.
- 테스트 스위트, 린터 설정은 없다. 변경 후에는 `python -m py_compile <파일>`로 문법을 확인하고, 가능하면 앱을 직접 띄워 확인한다.
- `requirements.txt`는 UTF-16(BOM) 인코딩이다. 수정 시 인코딩을 유지하거나, 변경하면 pip 설치가 되는지 확인한다.
- UI 변경은 Streamlit `AppTest`(`streamlit.testing.v1`)로 저장소를 오염시키지 않도록 **임시 복사본**에서 실행해 확인할 수 있다.

## 파일 구조와 역할

| 파일 | 역할 |
| --- | --- |
| `app_advanced.py` | 메인 Streamlit 앱. 탭1 자동 최적화 / 탭2 사용자 정의 백테스트(+포트폴리오 저장) / 탭3 리밸런싱 가이드 / 탭4 포트폴리오 비교 |
| `app.py` | 초기 버전 단일 페이지 앱 (탭1과 유사, 이후 기능 미반영 부분 있음) |
| `portfolio_engine.py` | 시세 조회(`get_stock_data`), 최적화(`optimize_portfolio`: max_sharpe / min_volatility / equal_weight / target_weight), 목표 비중(`DEFAULT_TARGET_WEIGHTS`), 이산 매수 수량(`get_discrete_allocation`) |
| `rebalance_engine.py` | 리밸런싱 백테스트(`backtest_rebalancing`)와 성과 지표(`calculate_metrics`) |
| `custom_backtest.py` | 사용자 정의 비중 백테스트. 누락 티커 제거·정규화 후 `rebalance_engine.backtest_rebalancing`에 위임 |
| `rebalancing_guide.py` | 현재가 조회, 보유 수량 대비 매수/매도 수량 계산, 거래 비용 계산 |
| `portfolio_store.py` | 영속화. `GitHubBackend`(GitHub Contents API, 별도 `data` 브랜치) / `LocalBackend`(로컬 파일, 개발용). 공용 포트폴리오(`data/portfolios.json`, 작성자 표시·작성자만 수정/삭제)와 사용자별 보유 수량(`users/<해시>.json`)을 다룬다 |
| `auth.py` | Google 로그인(`st.login`) 판정. 허용 이메일(`ALLOWED_EMAILS`) 검사, 사용자 키(이메일 SHA-256 앞 12자리) 생성. 로그인 설정이 없고 GitHub 저장소만 설정되면 앱을 열지 않는다(fail-closed) |
| `docs/` | `portfolio-storage-research.md`(저장 방식), `multi-user-plan.md`(3~4명 사용 방안), `google-login-setup.md`(로그인·저장소 설정 절차) |
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
- 탭2·탭3은 `st.data_editor` 표로 입력한다. 종목 추가/제거 UI는 공통 함수 `row_controls()`(와 `ticker_name()`, `normalize_ticker()`)를 함께 쓰며, 탭2는 세션 키 `bt_table`/`bt_version`(+`bt_loaded`, `bt_flash`), 탭3은 `rb_table`/`rb_version`을 쓴다. 탭2의 저장본 불러오기는 선택한 포트폴리오의 티커·비중으로 표를 다시 만들고 저장 이름을 채운다(남의 것이면 "(내 복사본)"). 비중 0인 종목은 백테스트와 저장에서 제외한다.
- 탭3은 표(티커·종목명·현재 수량·목표 비중%)로 입력한다. 표는 `st.session_state["rb_table"]`에 두고, 종목 추가/제거는 표를 갱신한 뒤 `rb_version`을 올려 에디터 키를 바꿔 초기화한다(입력 데이터가 바뀌면 에디터의 편집 상태가 리셋되기 때문). 종목명은 `TICKER_NAMES`에서 채우고 없으면 `(미등록)`이다. 현재 수량은 **사용자별로 저장**(`users/<해시>.json`)되고 접속 시 자동으로 불러오며, 목표 비중은 저장하지 않고 `DEFAULT_TARGET_WEIGHTS`에서 채운다. 저장된 수량이 없으면 기본 티커를 0주로 채운다. **코드에 실제 보유 수량을 넣지 않는다**(저장소가 공개다). 목표 비중에만 있고 보유가 없는 티커는 0주로 계산되어 매수 안내가 나온다.
- `target_weight` 방법은 입력 티커가 전부 `DEFAULT_TARGET_WEIGHTS`에 있어야 그 비중을 쓰고, 아니면 균등 가중으로 대체된다.
- 화폐 단위는 원(KRW)이다. 금액을 표시할 때 `$`를 쓰지 말고 `{값:,.0f}원` 형식을 따른다.
- 리밸런싱 날짜는 `rebalance_engine.get_rebalance_dates`가 각 기간의 마지막 **실제 거래일**로 만든다(`resample().last().index`는 달력 말일이라 휴장일과 어긋나 리밸런싱이 누락되므로 쓰지 않는다). `backtest_rebalancing`은 비중 합이 1이 아니어도 정규화해서 쓴다.
- **위젯은 스크립트 순서대로 그려지므로, 뒤쪽 코드(저장/새로고침 처리)가 바꾼 목록은 다음 실행 전까지 앞쪽 위젯(예: 탭2 불러오기 선택 목록)에 반영되지 않는다.** 저장·새로고침 직후에는 `st.rerun()`으로 다시 그리고, 사라지는 성공 메시지는 `st.session_state`에 보관했다가 다시 그린 뒤 표시한다(`bt_flash`).
- `AppTest`의 `selectbox.select()`는 선택지가 바뀐 뒤 옛 포맷 함수를 참조해 실패할 수 있다. 위젯 키에 선택값을 직접 대입한 뒤 `run()`하는 방식으로 검증한다.
- `app_advanced.py`에서 `re`는 `rebalance_engine`의 별칭이다. 정규식 모듈을 `re`로 import하지 않는다(문자열 검사는 `str` 메서드를 쓴다).
- 탭3 매수/매도 분류는 `Shares to Buy/Sell`의 숫자 부호(>0, <0)로 판단한다. 문자열 비교를 쓰지 않는다.
- `rebalancing_guide.get_current_prices`는 최신일이 아니라 직전 거래일(`iloc[-2]`) 종가를 사용한다.
- `pypfopt`의 max_sharpe는 과거 평균 수익률에 민감해 특정 종목에 쏠린 비중을 낸다. 결과를 그대로 신뢰하지 말고 참고용으로 다룬다.

## 배포 (Streamlit Community Cloud)

- 로컬 디스크는 휘발성이다. 재부팅/재배포 시 앱이 쓴 파일은 사라지므로 **로컬 파일 저장(`LocalBackend`)은 Cloud에서 영속화가 되지 않는다.** 저장한 포트폴리오는 `portfolio_store.GitHubBackend`가 GitHub의 JSON 파일(`data/portfolios.json`)에 커밋해 보관하고, 탭4의 JSON 다운로드/업로드가 백업 수단이다. 설계 배경은 `docs/portfolio-storage-research.md`.
- **Cloud는 추적 브랜치(main)에 푸시가 있을 때마다 앱을 재배포한다.** 그래서 저장 데이터는 main이 아닌 별도 브랜치(`data`)나 별도 저장소에 커밋한다. 데이터 커밋을 main에 하지 않는다.
- **코드 저장소(`leenamkee/quant_portfolio`)는 공개(public)다.** 데이터를 같은 저장소에 저장하면 누구나 읽을 수 있으므로, 운영 시 `GITHUB_REPO`는 별도의 비공개 저장소로 지정한다. 실제 보유 수량 같은 민감한 값을 코드나 커밋에 넣지 않는다(탭3 기본 보유 수량은 이미 이력에 남아 있음, `docs/multi-user-plan.md` 참고).
- 저장소 관련 secrets: `GITHUB_TOKEN`(데이터 저장소 한 곳에만 Contents 읽기/쓰기), `GITHUB_REPO`, 선택 `GITHUB_DATA_BRANCH`(기본 `data`). 없으면 로컬 파일로 대체되고 탭4에 경고가 뜬다.
- 로그인 secrets: `[auth]`(redirect_uri, cookie_secret, client_id, client_secret, server_metadata_url)와 최상위 `ALLOWED_EMAILS`. 최상위 키는 `[auth]` 테이블보다 앞에 둔다. 설정 절차는 `docs/google-login-setup.md`. `st.login`에는 Authlib가 필요해 `requirements.txt`가 `streamlit[auth]`를 쓴다.
- 로그인 판정 규칙(`auth.resolve_identity`)을 바꿀 때는 fail-closed(설정이 불완전하면 열지 않음)를 유지한다. `st.cache_resource`로 만든 저장소 객체는 프로세스 안에서 재사용되므로, 테스트에서 secrets를 바꿔가며 시나리오를 돌릴 때는 시나리오마다 새 프로세스로 실행한다.
- 다른 모듈에 새 상수/함수를 추가하고 앱에서 참조하는 변경을 푸시하면, 실행 중인 Cloud 프로세스가 옛 모듈을 캐시하고 있어 `AttributeError`가 날 수 있다. 이 경우 코드 문제가 아니므로 Manage app → Reboot app을 먼저 시도한다 (2026-09-20 `pe.TICKER_NAMES` 사례).
- 비밀 값(토큰 등)은 `st.secrets`(Cloud의 App settings → Secrets)로만 다루고 저장소에 커밋하지 않는다.

## 작업 규칙

- **모든 작업 내용을 `worklog.md`에 기록한다.** 작업을 마칠 때마다(커밋 전에) 날짜 섹션 아래에 무엇을·왜 바꿨는지, 확인한 방법, 남은 이슈를 추가하고 같은 커밋에 포함한다. 날짜는 최신이 위로 오도록 쓴다. 코드 변경이 없는 조사/문서 작업도 기록한다.
- 코드 주석/문구는 기존 스타일대로 한국어를 사용한다. 주석은 꼭 필요한 이유(WHY)만 짧게 쓴다.
- 커밋 메시지는 영어로, 변경의 이유를 중심으로 쓴다. 푸시는 사용자가 요청할 때만 한다.
- 요청 범위를 넘는 리팩터링은 하지 않는다 (예: 중복 모듈 통합은 별도 요청이 있을 때).
