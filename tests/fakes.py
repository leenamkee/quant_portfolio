"""외부 서비스(Yahoo, GitHub)를 대신하는 가짜 객체. 테스트는 실제 네트워크를 호출하지 않는다."""
import base64
import json

import pandas as pd


def make_download(source, calls=None):
    """
    `yfinance.download`를 대신한다. source(DataFrame)에서 요청한 티커의 열을 'Close' 아래에 돌려준다.
    source에 없는 티커는 실제 yfinance처럼 전부 결측인 열이 된다. calls를 주면 요청 인자를 기록한다.
    """
    def fake_download(tickers, *args, **kwargs):
        cols = [tickers] if isinstance(tickers, str) else list(tickers)
        if calls is not None:
            calls.append({"tickers": cols, **kwargs})
        return pd.concat({"Close": source.reindex(columns=cols)}, axis=1)
    return fake_download


class Resp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeGitHub:
    """GitHub Contents/Git refs API의 최소 구현. `requests.Session`을 대신해 GitHubBackend.session에 넣는다."""

    def __init__(self, branch_exists=False, file_bytes=None):
        self.branch_exists = branch_exists
        self.file = file_bytes
        self.sha_n = 0
        self.calls = []
        self.conflicts_left = 0        # PUT이 이 횟수만큼 409를 돌려준다
        self.race_on_branch_create = False  # 브랜치 생성 시 다른 요청이 먼저 만든 상황(422)
        self.forced = {}               # (method, 경로에 포함된 문자열) -> (status, body)
        self.raise_on_request = None   # 요청 시 던질 예외
        self.headers = {}

    def _force(self, method, path):
        for (m, needle), value in self.forced.items():
            if m == method and needle in path:
                return Resp(*value)
        return None

    def request(self, method, url, **kwargs):
        if self.raise_on_request:
            raise self.raise_on_request
        path = url.replace("https://api.github.com", "")
        self.calls.append((method, path))
        forced = self._force(method, path)
        if forced:
            return forced
        if path.endswith("/git/ref/heads/data"):
            return Resp(200, {}) if self.branch_exists else Resp(404)
        if path.endswith("/git/ref/heads/main"):
            return Resp(200, {"object": {"sha": "abc123"}})
        if path.endswith("/git/refs") and method == "POST":
            if self.race_on_branch_create:
                self.branch_exists = True
                return Resp(422, {"message": "Reference already exists"})
            assert kwargs["json"] == {"ref": "refs/heads/data", "sha": "abc123"}
            self.branch_exists = True
            return Resp(201)
        if "/contents/" in path and method == "GET":
            if self.file is None:
                return Resp(404)
            return Resp(200, {"content": base64.b64encode(self.file).decode(), "sha": f"s{self.sha_n}"})
        if "/contents/" in path and method == "PUT":
            payload = kwargs["json"]
            assert payload["branch"] == "data"
            if self.conflicts_left > 0:
                self.conflicts_left -= 1
                return Resp(409)
            if self.file is not None and payload.get("sha") != f"s{self.sha_n}":
                return Resp(409)
            self.file = base64.b64decode(payload["content"])
            self.sha_n += 1
            return Resp(200)
        if path.count("/") == 3 and method == "GET":  # /repos/{owner}/{repo}
            return Resp(200, {"default_branch": "main"})
        raise AssertionError(f"예상하지 못한 요청: {method} {path}")

    def puts(self):
        return [c for c in self.calls if c[0] == "PUT"]
