# 퀀트 포트폴리오 매니저

Streamlit 기반의 포트폴리오 최적화 · 리밸런싱 백테스트 · 리밸런싱 가이드 도구입니다. `yfinance`로 시세를 가져오며, 기본 설정은 **DC형 퇴직연금 계좌**(위험자산 70% 한도)에 맞춘 국내 상장 ETF 포트폴리오입니다.

## 주요 기능

`app_advanced.py`는 4개 탭으로 구성됩니다.

1. **자동 최적화** — 티커를 입력하면 최적 비중을 계산하고 리밸런싱 주기(월/분기/연)별로 백테스트합니다.
   - `max_sharpe`: 샤프 지수 최대화
   - `min_volatility`: 변동성 최소화
   - `equal_weight`: 동일 가중
   - `target_weight`: 미리 정한 목표 비중(연금계좌 규정 준수)
2. **사용자 정의 백테스트** — 종목별 비중을 직접 입력해 백테스트하고, 성과 차트와 자산 배분을 확인합니다.
3. **리밸런싱 가이드** — 현재 보유 수량과 목표 비중을 넣으면 종목별 매수/매도 수량, 필요 현금, 예상 거래 비용을 계산합니다.
4. **포트폴리오 비교** — 탭2에서 저장한 여러 포트폴리오를 같은 기간·초기 자본·리밸런싱 주기로 백테스트해 성과 지표와 가치 추이를 나란히 비교합니다. JSON 백업/복원과 삭제도 여기서 합니다.

성과 지표: 총 수익률, 연환산 수익률(CAGR), 연환산 변동성, 샤프 지수, 최대 낙폭(MDD).

`app.py`는 탭1과 유사한 초기 단일 페이지 버전입니다.

## 기본 포트폴리오

| 티커 | 종목명 | 분류 | 목표 비중 |
| --- | --- | --- | --- |
| 273130.KS | KODEX 종합채권(AA-이상)액티브 | 안전자산 | 30% |
| 360750.KS | TIGER 미국S&P500 | 위험자산 | 25% |
| 284430.KS | KODEX 200미국채혼합50 | 위험자산 | 13% |
| 441640.KS | KODEX 미국배당커버드콜액티브 | 위험자산 | 13% |
| 458730.KS | TIGER 미국배당다우존스 | 위험자산 | 12% |
| 411060.KS | ACE KRX 금현물 | 위험자산 | 7% |

DC/IRP 퇴직연금은 위험자산을 적립금의 70%까지만 담을 수 있어(안전자산 최소 30%), 안전자산 슬롯으로 순수 채권형 ETF를 넣고 나머지를 70% 안에 배분했습니다. 국내 상장 종목은 yfinance에서 `.KS` 접미사가 필요합니다.

## 실행 방법

Python 3.11 이상을 권장합니다.

```bash
pip install -r requirements.txt
streamlit run app_advanced.py
```

브라우저에서 http://localhost:8501 로 접속합니다. GitHub Codespaces / VS Code Dev Container에서는 `.devcontainer` 설정에 따라 앱이 자동으로 실행됩니다.

## 프로젝트 구조

```
.
├── app_advanced.py       # 메인 앱 (자동 최적화 / 사용자 정의 백테스트 / 리밸런싱 가이드 / 포트폴리오 비교)
├── app.py                # 초기 단일 페이지 버전
├── portfolio_engine.py   # 시세 조회, 포트폴리오 최적화, 목표 비중, 이산 매수 수량
├── rebalance_engine.py   # 리밸런싱 백테스트, 성과 지표
├── custom_backtest.py    # 사용자 정의 비중 백테스트
├── rebalancing_guide.py  # 보유 수량 기반 매수/매도 가이드, 거래 비용
├── portfolio_store.py    # 포트폴리오·보유 수량 영속화 (GitHub JSON / 로컬 파일)
├── auth.py               # Google 로그인 판정, 허용 이메일
├── docs/                 # 리서치/설계 문서
├── Agent.md              # 개발자/AI 에이전트용 프로젝트 가이드
├── worklog.md            # 작업 기록
└── requirements.txt
```

## 사용 팁

- 목표 비중을 바꿀 때는 위험자산 합계가 70%를 넘지 않는지 확인하세요. 종목명과 목표 비중 기본값은 `portfolio_engine.py`의 `TICKER_NAMES`, `DEFAULT_TARGET_WEIGHTS` 한 곳에서 관리하며, 앱의 기본 입력값은 여기서 자동으로 만들어집니다.
- 리밸런싱 가이드의 "현재 보유 수량"은 본인의 실제 보유 수량을 입력하고 "내 보유 수량 저장"을 눌러두면 다음 접속 때 자동으로 불러옵니다.
- `max_sharpe` 결과는 과거 데이터 기간에 민감해 특정 종목에 비중이 쏠릴 수 있으니 참고용으로 보세요.

## 배포

Streamlit Community Cloud에 배포해 사용합니다. Cloud의 로컬 디스크는 재부팅/재배포 시 초기화되므로, 포트폴리오를 영구 저장하려면 외부 저장소가 필요합니다. 검토 결과와 설계안은 [docs/portfolio-storage-research.md](docs/portfolio-storage-research.md)를 참고하세요.

### 저장소·로그인 설정 (Cloud Secrets)

저장한 포트폴리오를 재시작 후에도 유지하려면 App settings → Secrets에 GitHub 저장소 정보를 넣습니다. 코드 저장소가 공개이므로 **데이터는 별도의 비공개 저장소**를 권장합니다(첫 커밋이 1개 이상 있어야 함).

```toml
GITHUB_TOKEN = "github_pat_..."                    # 데이터 저장소 하나에만 Contents 읽기/쓰기 권한
GITHUB_REPO = "leenamkee/quant_portfolio_data"
GITHUB_DATA_BRANCH = "data"                        # 생략 가능
```

설정하지 않으면 로컬 파일에 저장하며, Cloud에서는 앱이 재시작될 때 사라집니다.

여러 명이 함께 쓸 때는 Google 로그인을 켜고 허용할 이메일을 지정합니다. 모두가 서로의 포트폴리오를 볼 수 있고(수정·삭제는 작성자만), 보유 수량은 사용자별로 저장되어 본인만 봅니다.

```toml
ALLOWED_EMAILS = ["a@gmail.com", "b@gmail.com"]     # 최상위 키는 [auth]보다 앞에

[auth]
redirect_uri = "https://<앱 주소>.streamlit.app/oauth2callback"
cookie_secret = "<랜덤 문자열>"
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Google OAuth 클라이언트 생성부터 순서대로 따라 할 수 있는 절차는 [docs/google-login-setup.md](docs/google-login-setup.md), 설계 배경은 [docs/multi-user-plan.md](docs/multi-user-plan.md)를 참고하세요. GitHub 저장소만 설정하고 로그인을 설정하지 않으면 데이터 보호를 위해 앱이 열리지 않습니다.

## 주의

이 프로젝트의 결과는 과거 데이터 기반의 시뮬레이션이며 투자 권유가 아닙니다. 연금계좌의 위험자산 분류 기준은 금융기관·상품별로 다를 수 있으니 실제 투자 전에 소속 금융기관의 분류를 확인하세요.
