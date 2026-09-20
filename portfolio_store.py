import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "portfolios.json")
DATA_PATH = "data/portfolios.json"
KST = timezone(timedelta(hours=9))


class StoreError(Exception):
    pass


class ConflictError(StoreError):
    pass


def _empty():
    return {"portfolios": []}


class LocalBackend:
    """로컬 파일 저장소. Streamlit Cloud에서는 재부팅/재배포 시 초기화되므로 개발용이다."""
    persistent = False
    label = "로컬 파일 (Cloud에서는 재시작 시 사라짐)"

    def __init__(self, path=LOCAL_PATH):
        self.path = path

    def read(self):
        if not os.path.exists(self.path):
            return _empty(), None
        with open(self.path, encoding="utf-8") as f:
            return json.load(f), None

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
            if created.status_code not in (200, 201):
                raise StoreError(f"데이터 브랜치 생성 실패({created.status_code}): {created.text[:200]}")
        elif r.status_code != 200:
            raise StoreError(f"브랜치 조회 실패({r.status_code}): 토큰 권한과 저장소 이름을 확인하세요.")
        self._branch_ready = True

    def read(self):
        r = self._request("GET", f"/repos/{self.repo}/contents/{self.path}", params={"ref": self.branch})
        if r.status_code == 404:
            return _empty(), None
        if r.status_code != 200:
            raise StoreError(f"읽기 실패({r.status_code}): {r.text[:200]}")
        body = r.json()
        content = base64.b64decode(body["content"]).decode("utf-8")
        return json.loads(content), body["sha"]

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


def get_backend(secrets):
    """secrets에 GITHUB_TOKEN/GITHUB_REPO가 있으면 GitHub, 없으면 로컬 파일을 사용한다."""
    try:
        token = secrets["GITHUB_TOKEN"]
        repo = secrets["GITHUB_REPO"]
    except (KeyError, FileNotFoundError):
        return LocalBackend()
    branch = secrets["GITHUB_DATA_BRANCH"] if "GITHUB_DATA_BRANCH" in secrets else "data"
    return GitHubBackend(token, repo, branch)


def load(backend):
    return backend.read()[0]


def update(backend, mutate, message, retries=3):
    """
    읽기 → mutate(data) → 쓰기. 다른 저장과 충돌하면(409/422) 최신 데이터를 다시 읽어 재시도한다.
    변경이 반영된 최신 데이터를 반환한다.
    """
    for _ in range(retries):
        data, sha = backend.read()
        mutate(data)
        try:
            backend.write(data, sha, message)
            return data
        except ConflictError:
            continue
    raise ConflictError("여러 번 재시도했지만 충돌이 계속됩니다. 잠시 후 다시 시도하세요.")


def make_portfolio(name, weights):
    """weights: {ticker: 0~1 비중}. 티커 순서는 입력 순서를 유지한다."""
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name.strip(),
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "tickers": list(weights),
        "weights": {t: round(float(w), 6) for t, w in weights.items()},
    }


def upsert_portfolio(backend, portfolio):
    """같은 이름의 포트폴리오가 있으면 덮어쓴다(id는 기존 것을 유지)."""
    def mutate(data):
        for i, p in enumerate(data["portfolios"]):
            if p["name"] == portfolio["name"]:
                data["portfolios"][i] = {**portfolio, "id": p["id"]}
                return
        data["portfolios"].append(portfolio)
    return update(backend, mutate, f"Save portfolio: {portfolio['name']}")


def delete_portfolios(backend, ids):
    ids = set(ids)
    def mutate(data):
        data["portfolios"] = [p for p in data["portfolios"] if p["id"] not in ids]
    return update(backend, mutate, f"Delete {len(ids)} portfolio(s)")


def import_portfolios(backend, incoming):
    """백업 JSON의 포트폴리오를 병합한다. id가 같으면 교체, 없으면 추가."""
    def mutate(data):
        by_id = {p["id"]: i for i, p in enumerate(data["portfolios"])}
        for p in incoming:
            if p["id"] in by_id:
                data["portfolios"][by_id[p["id"]]] = p
            else:
                data["portfolios"].append(p)
    return update(backend, mutate, f"Import {len(incoming)} portfolio(s)")


def validate_import(obj):
    """업로드된 JSON이 저장 포맷인지 검사하고 포트폴리오 리스트를 반환한다."""
    if not isinstance(obj, dict) or not isinstance(obj.get("portfolios"), list):
        raise StoreError("'portfolios' 목록이 있는 JSON이 아닙니다.")
    for p in obj["portfolios"]:
        if not isinstance(p, dict) or not {"id", "name", "tickers", "weights"} <= p.keys():
            raise StoreError("포트폴리오 항목에 id/name/tickers/weights가 필요합니다.")
        if set(p["tickers"]) != set(p["weights"]):
            raise StoreError(f"'{p['name']}': tickers와 weights의 종목이 일치하지 않습니다.")
    return obj["portfolios"]
