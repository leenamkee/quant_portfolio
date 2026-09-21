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

    @classmethod
    def for_repo_path(cls, repo_path):
        """저장소 상대 경로(예: users/abc.json)를 로컬 data/ 폴더 아래 파일로 대응시킨다."""
        base = os.path.dirname(LOCAL_PATH)
        rel = repo_path[len("data/"):] if repo_path.startswith("data/") else repo_path
        return cls(os.path.join(base, *rel.split("/")))

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


def get_backend(secrets, path=DATA_PATH):
    """secrets에 GITHUB_TOKEN/GITHUB_REPO가 있으면 GitHub, 없으면 로컬 파일을 사용한다."""
    try:
        token = secrets["GITHUB_TOKEN"]
        repo = secrets["GITHUB_REPO"]
    except (KeyError, FileNotFoundError):
        return LocalBackend.for_repo_path(path)
    branch = secrets["GITHUB_DATA_BRANCH"] if "GITHUB_DATA_BRANCH" in secrets else "data"
    return GitHubBackend(token, repo, branch, path)


def user_path(user_key):
    return f"users/{user_key}.json"


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


def make_portfolio(name, weights, owner_key=None, owner_name=None):
    """weights: {ticker: 0~1 비중}. 티커 순서는 입력 순서를 유지한다."""
    portfolio = {
        "id": uuid.uuid4().hex[:8],
        "name": name.strip(),
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "tickers": list(weights),
        "weights": {t: round(float(w), 6) for t, w in weights.items()},
    }
    if owner_key:
        portfolio["owner_key"] = owner_key
        portfolio["owner_name"] = owner_name or ""
    return portfolio


def can_modify(portfolio, owner_key):
    """작성자가 없는 항목(이전 데이터)이거나 작성자 본인이면 수정/삭제할 수 있다. owner_key가 None이면 제한하지 않는다."""
    if owner_key is None:
        return True
    return portfolio.get("owner_key") in (None, owner_key)


def upsert_portfolio(backend, portfolio):
    """같은 이름이 있으면 덮어쓴다(id 유지). 다른 사용자가 만든 이름이면 거부한다."""
    def mutate(data):
        for i, p in enumerate(data["portfolios"]):
            if p["name"] == portfolio["name"]:
                if not can_modify(p, portfolio.get("owner_key")):
                    raise StoreError(f"'{p['name']}'은(는) {p.get('owner_name') or '다른 사용자'}님이 만든 포트폴리오입니다. 다른 이름으로 저장하세요.")
                data["portfolios"][i] = {**portfolio, "id": p["id"]}
                return
        data["portfolios"].append(portfolio)
    return update(backend, mutate, f"Save portfolio: {portfolio['name']}")


def delete_portfolios(backend, ids, owner_key=None):
    """본인 것(또는 작성자 없는 항목)만 삭제한다."""
    ids = set(ids)
    def mutate(data):
        data["portfolios"] = [p for p in data["portfolios"] if not (p["id"] in ids and can_modify(p, owner_key))]
    return update(backend, mutate, f"Delete {len(ids)} portfolio(s)")


def import_portfolios(backend, incoming, owner_key=None, owner_name=None):
    """
    백업 JSON을 병합한다. id가 같으면 교체, 없으면 추가한다.
    다른 사용자 소유 항목은 덮어쓰지 않고 건너뛰며, 작성자가 없는 항목은 가져온 사용자 소유로 지정한다.
    (병합된 데이터, 건너뛴 개수)를 반환한다.
    """
    skipped = []
    def mutate(data):
        skipped.clear()  # 충돌 재시도 시 중복 집계 방지
        by_id = {p["id"]: i for i, p in enumerate(data["portfolios"])}
        names = {p["name"]: p for p in data["portfolios"]}
        for p in incoming:
            p = dict(p)
            if owner_key and not p.get("owner_key"):
                p["owner_key"], p["owner_name"] = owner_key, owner_name or ""
            existing = data["portfolios"][by_id[p["id"]]] if p["id"] in by_id else names.get(p["name"])
            if existing is not None and not can_modify(existing, owner_key):
                skipped.append(p["name"])
                continue
            if existing is not None:
                idx = data["portfolios"].index(existing)
                data["portfolios"][idx] = {**p, "id": existing["id"]}
            else:
                data["portfolios"].append(p)
    data = update(backend, mutate, f"Import {len(incoming)} portfolio(s)")
    return data, len(skipped)


def load_holdings(backend):
    """사용자별 파일에서 보유 수량({ticker: shares})을 읽는다."""
    return backend.read()[0].get("holdings", {})


def save_holdings(backend, holdings):
    clean = {}
    for ticker, shares in holdings.items():
        if not isinstance(shares, int) or shares < 0:
            raise StoreError(f"'{ticker}' 보유 수량은 0 이상의 정수여야 합니다.")
        clean[ticker] = shares

    def mutate(data):
        data["holdings"] = clean
        data["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
        data.pop("portfolios", None)
    return update(backend, mutate, "Update holdings")


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
