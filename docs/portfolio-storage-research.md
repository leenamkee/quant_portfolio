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
