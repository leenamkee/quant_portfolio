# 포트폴리오 저장/비교 방법 리서치 (Streamlit Cloud)

작성일: 2026-09-19

## 배경 및 목표

Streamlit Community Cloud에 배포된 개인용 퀀트 포트폴리오 앱에서, 여러 포트폴리오(티커 조합 + 목표 비중)를 저장해두고 나중에 성과를 나란히 비교하고 싶다. 앱이 완전관리형 클라우드에서 돌아가므로 PostgreSQL 같은 별도 DB를 구축·운영하는 부담 없이, JSON 기반의 가벼운 저장 방법으로 해결하는 것이 목표다.

## Streamlit Community Cloud 파일시스템의 핵심 제약

로컬 디스크는 ephemeral(휘발성)이다. 앱이 재부팅되거나(자동 슬립 후 재시작, 리소스 회수 등) GitHub에 새 커밋이 푸시되어 재배포되면, 런타임 중 앱이 로컬에 쓴 파일은 모두 사라진다.

즉 `portfolios.json`을 앱 작업 디렉터리에 저장하는 방식은 세션 중에는 동작하지만, 컨테이너가 재시작되는 순간 데이터가 날아간다 — 실질적으로 "저장했다고 착각하기 쉬운 함정"이다. ([Streamlit 커뮤니티: Files lost after reboot](https://discuss.streamlit.io/t/files-lost-after-reboot-in-streamlit-cloud/33917))

`st.session_state`는 더 짧게 간다: 같은 브라우저 탭(세션) 동안만 유지되고, 새로고침·다른 브라우저·서버 재시작에는 살아남지 않는다. ([Streamlit 공식 문서: Session State](https://docs.streamlit.io/develop/concepts/architecture/session-state))

결론: 진짜 영속성을 원한다면 **앱 컨테이너 밖의 저장소**(Git 저장소 자체, 외부 API/스프레드시트, 외부 오브젝트 스토리지 등)를 써야 한다.

## 방법 비교

DB 없이 JSON을 진짜로 영속화하는 5가지 방법을 비교했다.

| 방법 | 영속성 | 구현 난이도 | 비용 | 장점 | 단점 |
| --- | --- | --- | --- | --- | --- |
| 브라우저 다운로드/업로드 (`st.download_button` / `st.file_uploader`) | 사용자가 파일을 직접 보관하는 동안만 | 매우 낮음 | 무료 | 외부 계정/토큰 전혀 필요 없음, 코드 몇 줄이면 끝 | 자동 저장이 아니라 매번 수동 업로드해야 여러 세션에서 비교 가능 |
| GitHub API로 저장소에 JSON 커밋 ([예시](https://huggingface.co/spaces/Suvh/hicxai-condition-1/blob/main/src/github_saver.py)) | 영구적 (git 이력에 남음) | 중간 | 무료 | 이미 쓰는 GitHub 저장소를 그대로 재사용, 버전 이력이 자동으로 남음 | Personal Access Token을 `st.secrets`에 보관해야 함, 커밋이 잦으면 히스토리 오염, 동시 저장 시 충돌 가능 |
| GitHub Gist API ([참고](https://dev.to/rikurouvila/how-to-use-a-github-gist-as-a-free-database-20np)) | 영구적 | 낮음~중간 | 무료 | 저장소 코드와 분리된 별도 파일로 관리, 공개/비공개 선택 가능 | 역시 PAT 필요, Gist 하나당 리비전이 계속 쌓임 |
| Google Sheets (`st.connection("gsheets", type=GSheetsConnection)`) | 영구적 | 중간 | 무료 (Google 계정) | Streamlit 공식 지원([streamlit/gsheets-connection](https://github.com/streamlit/gsheets-connection)), 시트를 직접 열어 눈으로 확인/수정 가능 | 서비스 계정 생성 및 Sheets/Drive API 활성화 등 초기 설정이 상대적으로 복잡 |
| 호스팅 JSON 스토리지 (JSONBin.io 등) | 영구적 | 낮음 | 무료 티어 존재(요청 수 제한) | REST API 하나로 즉시 사용, 스키마 없이 JSON 그대로 저장 | 서드파티 서비스 의존, 무료 티어 한도/서비스 지속성 리스크 |

이 프로젝트는 1인이 사용하는 개인용 앱이라 동시 쓰기 충돌이나 대규모 트래픽은 고려하지 않았다.

## 추천안

**GitHub API로 저장소에 `data/portfolios.json`을 커밋하는 방식**을 1순위로 추천한다.

- 이미 quant_portfolio GitHub 저장소를 쓰고 있으므로 새 계정이나 서비스 등록이 필요 없다.
- 저장할 때마다 자동으로 git 커밋이 쌓여 변경 이력이 공짜로 생긴다(언제 어떤 포트폴리오를 추가·수정했는지 추적 가능).
- 개인용 앱이라 동시 쓰기 충돌이 없고, 저장 빈도도 낮아(포트폴리오를 만들 때만 저장) GitHub API 호출량이나 커밋 이력 오염 문제가 실질적으로 문제되지 않는다.
- 필요한 건 Contents 읽기/쓰기 권한만 가진 fine-grained Personal Access Token 하나를 만들어 Streamlit Cloud의 App settings → Secrets에 넣어두는 것뿐이다.

보조로 **브라우저 다운로드/업로드**를 함께 두는 것을 권장한다: GitHub API 호출이 실패하더라도(토큰 만료, 네트워크 장애 등) portfolios.json을 로컬에 백업받을 수 있어 데이터 유실 위험을 줄인다.

Google Sheets는 시트를 눈으로 바로 보고 싶거나 향후 여러 사람이 같이 관리해야 할 때 고려할 만한 대안이지만, 현재의 1인용 워크플로우에는 과한 설정이라고 판단했다.

## 구현 개요

### 데이터 스키마 (`data/portfolios.json`)

```json
{
  "portfolios": [
    {
      "id": "dc-70-30-2026-09",
      "name": "DC 연금계좌 - 위험자산 70%",
      "created_at": "2026-09-19T00:00:00+09:00",
      "tickers": ["273130.KS", "284430.KS", "360750.KS", "411060.KS", "441640.KS", "458730.KS"],
      "weights": {
        "273130.KS": 0.30,
        "284430.KS": 0.13,
        "360750.KS": 0.25,
        "411060.KS": 0.07,
        "441640.KS": 0.13,
        "458730.KS": 0.12
      },
      "backtest": {
        "start_date": "2024-09-19",
        "end_date": "2026-09-19",
        "initial_capital": 10000000,
        "rebalance_freq": "Q"
      }
    }
  ]
}
```

### 저장/로드 코드 스케치 (PyGithub)

```python
import json
from github import Github
import streamlit as st

REPO_NAME = "leenamkee/quant_portfolio"
FILE_PATH = "data/portfolios.json"

def _get_repo():
    gh = Github(st.secrets["GITHUB_TOKEN"])
    return gh.get_repo(REPO_NAME)

def load_portfolios():
    repo = _get_repo()
    try:
        content = repo.get_contents(FILE_PATH)
        return json.loads(content.decoded_content.decode())
    except Exception:
        return {"portfolios": []}

def save_portfolio(new_entry):
    repo = _get_repo()
    data = load_portfolios()
    data["portfolios"].append(new_entry)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        content = repo.get_contents(FILE_PATH)
        repo.update_file(FILE_PATH, f"Add portfolio: {new_entry['name']}", payload, content.sha)
    except Exception:
        repo.create_file(FILE_PATH, f"Add portfolio: {new_entry['name']}", payload)
```

### Secrets 설정 (Streamlit Cloud → App settings → Secrets)

```toml
GITHUB_TOKEN = "github_pat_..."
```

PAT는 이 저장소만 대상으로 하는 fine-grained 토큰을 만들고, 권한은 Contents: Read and write만 부여하면 충분하다.

### 성과 비교 화면

`portfolios.json`을 읽어 각 항목의 `tickers`/`weights`로 기존 `rebalance_engine.backtest_rebalancing`을 반복 실행하고, 결과를 하나의 표·차트로 나란히 보여준다(예: 포트폴리오별 누적수익률 곡선 겹치기, CAGR/샤프/MDD 비교표).

## 구현 결과 (2026-09-20)

추천안대로 구현했다. 코드는 [portfolio_store.py](../portfolio_store.py)와 `app_advanced.py`의 탭2(저장), 탭4 "포트폴리오 비교"에 있다. 원안과 달라진 점은 다음과 같다.

| 항목 | 원안 | 구현 | 이유 |
| --- | --- | --- | --- |
| 저장 위치 | 저장소(main)의 `data/portfolios.json` | **별도 `data` 브랜치**의 `data/portfolios.json` | Cloud는 추적 브랜치에 푸시가 있을 때마다 앱을 자동 갱신한다([Manage your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)). main에 커밋하면 저장할 때마다 앱이 재배포되어 작업 중이던 세션이 초기화된다. `data` 브랜치는 없으면 자동 생성된다. |
| GitHub 클라이언트 | PyGithub | `requests`로 Contents API 직접 호출 | 이미 `requirements.txt`에 있어 의존성을 추가하지 않는다. |
| 충돌 처리 | 없음 | 409/422(sha 불일치) 시 최신본을 다시 읽어 최대 3회 재시도 | 동시 저장 시 유실 방지 ([GitHub 409 사례](https://github.com/orgs/community/discussions/62198)) |
| 스키마 | 백테스트 설정(기간·자본·주기) 포함 | `id`, `name`, `created_at`, `tickers`, `weights`만 저장 | 비교할 때 기간·자본·주기를 동일하게 맞춰야 공정하므로 비교 화면에서 입력받는다. |
| 토큰 없을 때 | (미정) | 로컬 파일(`data/portfolios.json`)로 대체 + 경고 표시 | 로컬 개발용. Cloud에서는 재시작 시 사라진다. |

**주의 — 코드 저장소가 공개(public)면 저장한 포트폴리오도 공개된다.** 이 프로젝트의 저장소(`leenamkee/quant_portfolio`)는 공개 저장소라서, 같은 저장소의 `data` 브랜치에 저장하면 누구나 읽을 수 있다. 데이터는 **별도의 비공개 저장소**(예: `quant_portfolio_data`, 최소 1개 커밋이 있어야 함)에 저장하는 것을 권장한다. 이 경우 앱 코드 저장소를 건드리지 않으므로 재배포 문제도 없다. `GITHUB_REPO`만 바꾸면 된다.

Secrets 설정(Streamlit Cloud → App settings → Secrets):

```toml
GITHUB_TOKEN = "github_pat_..."          # 데이터 저장소 하나에만 Contents: Read and write 권한
GITHUB_REPO = "leenamkee/quant_portfolio_data"   # 권장: 비공개 데이터 저장소
GITHUB_DATA_BRANCH = "data"              # 생략 가능 (기본값 data, 없으면 자동 생성)
```

사용 흐름: 탭2에서 종목 비중 입력 → "현재 구성 저장" → 탭4에서 여러 포트폴리오를 선택해 기간·초기 자본·리밸런싱 주기를 맞춰 성과 지표와 가치 추이를 나란히 비교. 백업/복원(JSON 다운로드·업로드)과 삭제도 탭4에 있다.

여러 명이 함께 쓰는 경우의 확장 방안은 [multi-user-plan.md](multi-user-plan.md)를 참고.

## 참고 자료

- [Files lost after reboot in Streamlit Cloud – Streamlit 커뮤니티](https://discuss.streamlit.io/t/files-lost-after-reboot-in-streamlit-cloud/33917)
- [Status and limitations of Community Cloud – Streamlit 공식 문서](https://docs.streamlit.io/deploy/streamlit-community-cloud/status)
- [Session State – Streamlit 공식 문서](https://docs.streamlit.io/develop/concepts/architecture/session-state)
- [GitHub Saver 예시 (Hugging Face Spaces)](https://huggingface.co/spaces/Suvh/hicxai-condition-1/blob/main/src/github_saver.py)
- [streamlit/gsheets-connection – GitHub](https://github.com/streamlit/gsheets-connection)
- [Connect Streamlit to a private Google Sheet – Streamlit 공식 문서](https://docs.streamlit.io/develop/tutorials/databases/private-gsheet)
- [How to use a GitHub Gist as a free database – DEV Community](https://dev.to/rikurouvila/how-to-use-a-github-gist-as-a-free-database-20np)
- [JSONBin.io – JSON Storage & Hosting Service](https://jsonbin.io/)
- [Secrets management for your Community Cloud app – Streamlit 공식 문서](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
