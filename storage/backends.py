"""실제 읽기/쓰기 백엔드. 문서 형태는 모르고 원문 dict만 다룬다(형태 검사는 schema.py, 저장 로직은 repository.py)."""
import base64
import json
import os

import requests

from .schema import StoreError, ConflictError

LOCAL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "portfolios.json")
DATA_PATH = "data/portfolios.json"


def user_path(user_key):
    return f"users/{user_key}.json"


class LocalBackend:
    """로컬 파일 저장소. Streamlit Cloud에서는 재부팅/재배포 시 초기화되므로 개발용이다."""
    persistent = False
    label = "로컬 파일 (Cloud에서는 재시작 시 사라짐)"

    def __init__(self, path=LOCAL_PATH):
        self.path = path

    @classmethod
    def for_repo_path(cls, repo_path):
        """저장소 상대 경로(예: users/abc.json)를 로컬 data/ 폴더 아래 파일로 대응시킨다."""
        base = os.path.dirname(LOCAL_PATH)
        rel = repo_path[len("data/"):] if repo_path.startswith("data/") else repo_path
        return cls(os.path.join(base, *rel.split("/")))

    def read(self):
        """(원문 dict, None) 튜플. 파일이 없으면 빈 dict({}). 로컬 백엔드는 충돌 개념이 없어 두 번째 값은 항상 None이다."""
        if not os.path.exists(self.path):
            return {}, None
        with open(self.path, encoding="utf-8") as f:
            try:
                return json.load(f), None
            except json.JSONDecodeError as e:
                raise StoreError(f"저장된 파일이 손상되었습니다(JSON 형식이 아님): {e}") from e

    def write(self, data, sha, message):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


class GitHubBackend:
    """
    GitHub Contents API로 별도 데이터 브랜치의 JSON 파일을 읽고 쓴다.
    Cloud 앱이 추적하는 브랜치(main)에 커밋하면 저장할 때마다 앱이 재배포되므로 다른 브랜치를 쓴다.
    """
    persistent = True
    API = "https://api.github.com"

    def __init__(self, token, repo, branch="data", path=DATA_PATH):
        self.repo = repo
        self.branch = branch
        self.path = path
        self.label = f"GitHub {repo}@{branch}"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self._branch_ready = False

    def _request(self, method, url, **kwargs):
        try:
            return self.session.request(method, f"{self.API}{url}", timeout=15, **kwargs)
        except requests.RequestException as e:
            raise StoreError(f"GitHub 연결 실패: {e}") from e

    def _ensure_branch(self):
        if self._branch_ready:
            return
        r = self._request("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
        if r.status_code == 404:
            repo_info = self._request("GET", f"/repos/{self.repo}")
            if repo_info.status_code != 200:
                raise StoreError(f"저장소 조회 실패({repo_info.status_code}): 토큰 권한과 저장소 이름을 확인하세요.")
            base = repo_info.json()["default_branch"]
            base_ref = self._request("GET", f"/repos/{self.repo}/git/ref/heads/{base}")
            if base_ref.status_code != 200:
                raise StoreError(f"기본 브랜치 조회 실패({base_ref.status_code})")
            created = self._request("POST", f"/repos/{self.repo}/git/refs", json={
                "ref": f"refs/heads/{self.branch}",
                "sha": base_ref.json()["object"]["sha"],
            })
            if created.status_code == 422:
                # 다른 요청이 동시에 먼저 브랜치를 만들었을 수 있다(최초 저장 경쟁). 이미 있으면 성공으로 본다.
                recheck = self._request("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
                if recheck.status_code != 200:
                    raise StoreError(f"데이터 브랜치 생성 실패({created.status_code}): {created.text[:200]}")
            elif created.status_code not in (200, 201):
                raise StoreError(f"데이터 브랜치 생성 실패({created.status_code}): {created.text[:200]}")
        elif r.status_code != 200:
            raise StoreError(f"브랜치 조회 실패({r.status_code}): 토큰 권한과 저장소 이름을 확인하세요.")
        self._branch_ready = True

    def read(self):
        """(원문 dict, sha) 튜플. 파일이 없으면 (빈 dict, None)."""
        r = self._request("GET", f"/repos/{self.repo}/contents/{self.path}", params={"ref": self.branch})
        if r.status_code == 404:
            return {}, None
        if r.status_code != 200:
            raise StoreError(f"읽기 실패({r.status_code}): {r.text[:200]}")
        body = r.json()
        content = base64.b64decode(body["content"]).decode("utf-8")
        try:
            return json.loads(content), body["sha"]
        except json.JSONDecodeError as e:
            raise StoreError(f"저장된 데이터가 손상되었습니다(JSON 형식이 아님): {e}") from e

    def write(self, data, sha, message):
        self._ensure_branch()
        payload = {
            "message": message,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        r = self._request("PUT", f"/repos/{self.repo}/contents/{self.path}", json=payload)
        if r.status_code in (200, 201):
            return
        if r.status_code in (409, 422):
            raise ConflictError("다른 곳에서 먼저 저장되어 충돌했습니다.")
        raise StoreError(f"저장 실패({r.status_code}): {r.text[:200]}")


def get_backend(secrets, path=DATA_PATH):
    """secrets에 GITHUB_TOKEN/GITHUB_REPO가 있으면 GitHub, 없으면 로컬 파일을 사용한다."""
    try:
        token = secrets["GITHUB_TOKEN"]
        repo = secrets["GITHUB_REPO"]
    except (KeyError, FileNotFoundError):
        return LocalBackend.for_repo_path(path)
    branch = secrets["GITHUB_DATA_BRANCH"] if "GITHUB_DATA_BRANCH" in secrets else "data"
    return GitHubBackend(token, repo, branch, path)
