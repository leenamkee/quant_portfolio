# Google 로그인 + 데이터 저장소 설정 가이드

작성일: 2026-09-21

앱은 Google 로그인(`st.login`)과 허용 이메일 목록으로 접근을 통제하고, 로그인한 사용자별로 보유 수량을 저장한다. 아래 순서대로 한 번만 설정하면 된다. 설정 전에는 로컬 개발 모드(로그인 없음, 단일 사용자)로 동작한다.

## 동작 요약

| 상황 | 앱 동작 |
| --- | --- |
| 로그인 설정(`[auth]`) 없음, GitHub 저장소 설정 없음 | 로컬 개발 모드. 로그인 없이 열리고 데이터는 로컬 파일에 저장 |
| GitHub 저장소만 설정, 로그인 설정 없음 | **앱을 열지 않고 오류 표시** (데이터 보호) |
| 로그인 설정됨 | Google 로그인 필요. `ALLOWED_EMAILS`에 없는 계정은 거부. 허용 목록이 비어 있으면 모두 거부 |

> 배포 전 확인: `requirements.txt`에 `streamlit[auth]==1.52.2`가 들어 있어야 로그인이 동작한다(Authlib 필요). 이미 반영되어 있다.

## 1. 비공개 데이터 저장소 만들기

코드 저장소(`quant_portfolio`)는 공개라서 데이터를 같은 저장소에 두면 누구나 읽을 수 있다. 별도의 **비공개** 저장소를 만든다.

1. GitHub에서 새 저장소 `quant_portfolio_data` 생성 → Visibility: **Private**, "Add a README file" 체크(첫 커밋이 있어야 한다).
2. Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
   - Repository access: **Only select repositories** → `quant_portfolio_data` 하나만
   - Permissions → Repository permissions → **Contents: Read and write**
   - 만료일을 정하고 기록해둔다(만료되면 저장이 실패한다).
3. 발급된 `github_pat_...` 값을 복사해둔다(다시 볼 수 없다).

앱이 이 저장소에 `data` 브랜치를 자동으로 만들고 아래 파일을 관리한다.

```
data/portfolios.json          # 모두가 볼 수 있는 포트폴리오 (작성자 표시)
users/<이메일 해시>.json      # 사용자별 보유 수량 (본인만 조회)
```

## 2. Google OAuth 클라이언트 만들기

콘솔 메뉴 이름은 Google의 개편에 따라 조금씩 다를 수 있다.

1. [Google Cloud Console](https://console.cloud.google.com/)에서 새 프로젝트를 만든다.
2. **OAuth 동의 화면**(Google Auth Platform)을 설정한다.
   - 사용자 유형: **외부(External)**
   - 앱 이름, 사용자 지원 이메일, 개발자 연락처 이메일 입력
   - 게시 상태는 **테스트(Testing)**로 두고, **테스트 사용자**에 4명의 Google 이메일을 모두 추가한다.
   - 테스트 상태는 최대 100명까지 로그인할 수 있고, 로그인 시 "확인되지 않은 앱" 안내 화면이 보인다. 4명 규모에서는 이대로 써도 된다. 기본 범위(openid, email, profile)만 쓰므로 별도 검증 절차는 필요 없다. ([관련 설명](https://support.google.com/cloud/answer/15549945?hl=en))
3. **사용자 인증 정보 → OAuth 클라이언트 ID 만들기**
   - 애플리케이션 유형: **웹 애플리케이션**
   - **승인된 리디렉션 URI**를 두 개 추가한다.
     - `https://<내 앱 주소>.streamlit.app/oauth2callback`
     - `http://localhost:8501/oauth2callback` (로컬에서 테스트할 때)
4. 생성된 **클라이언트 ID**와 **클라이언트 보안 비밀번호**를 복사해둔다.

## 3. Streamlit Cloud Secrets 입력

앱 → Manage app → Settings → **Secrets**에 아래를 붙여넣고 값을 채운다. TOML에서는 최상위 키(`GITHUB_*`, `ALLOWED_EMAILS`)가 `[auth]` 테이블보다 **앞에** 와야 한다.

```toml
GITHUB_TOKEN = "github_pat_..."
GITHUB_REPO = "leenamkee/quant_portfolio_data"
ALLOWED_EMAILS = ["a@gmail.com", "b@gmail.com", "c@gmail.com", "d@gmail.com"]

[auth]
redirect_uri = "https://<내 앱 주소>.streamlit.app/oauth2callback"
cookie_secret = "<아래 명령으로 만든 랜덤 문자열>"
client_id = "<클라이언트 ID>"
client_secret = "<클라이언트 보안 비밀번호>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

`cookie_secret`은 다음 명령으로 만든다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

저장하면 앱이 재시작된다. 접속하면 "Google로 로그인" 화면이 나오고, `ALLOWED_EMAILS`에 있는 계정만 들어갈 수 있다.

## 4. 로컬에서 로그인까지 테스트하기 (선택)

`.streamlit/secrets.toml`(저장소에 커밋하지 않는다)에 위와 같은 내용을 넣되 `redirect_uri`는 `http://localhost:8501/oauth2callback`로 한다. GitHub 항목은 빼면 데이터는 로컬 `data/` 폴더에 저장된다. 그 뒤 `streamlit run app_advanced.py`를 실행한다. GitHub Codespaces 같은 호스팅 개발 환경에서는 로그인 리디렉션이 제한될 수 있다([Streamlit 문서](https://docs.streamlit.io/develop/concepts/connections/authentication)).

## 사용 방식

- **포트폴리오**: 탭2에서 저장하면 모두에게 보이고(작성자 표시), 탭4에서 함께 비교할 수 있다. 수정·삭제는 **작성자 본인만** 가능하고, 다른 사람이 만든 이름으로는 저장되지 않는다.
- **보유 수량**: 탭3에서 "내 보유 수량 저장"을 누르면 본인 파일에만 저장되고 다른 사용자에게는 보이지 않는다. 다음 접속 때 자동으로 불러온다.
- 파일명은 이메일의 SHA-256 앞 12자리라 저장소에 이메일이 드러나지 않는다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| "GitHub 저장소는 설정되어 있지만 Google 로그인([auth]) 설정이 없습니다" | Secrets에 `[auth]` 항목이 빠졌다 |
| "ALLOWED_EMAILS가 설정되지 않아…" | `ALLOWED_EMAILS`가 없거나 비었다. `[auth]`보다 위에 있어야 한다 |
| "…계정은 이 앱의 사용 권한이 없습니다" | 그 이메일이 `ALLOWED_EMAILS`에 없다(대소문자는 무시한다) |
| Google 화면에서 `redirect_uri_mismatch` | OAuth 클라이언트의 승인된 리디렉션 URI가 Secrets의 `redirect_uri`와 정확히 같아야 한다 |
| Google 화면에서 "액세스 차단됨" | OAuth 동의 화면의 테스트 사용자에 그 계정을 추가했는지 확인 |
| 저장 실패(401/403/404) | 토큰 만료 또는 권한 부족, 저장소 이름 오타. 토큰을 저장소 하나에 Contents 읽기/쓰기로 다시 발급 |
| 저장소가 비어 있다는 오류 | 데이터 저장소에 첫 커밋(README)이 필요하다 |
