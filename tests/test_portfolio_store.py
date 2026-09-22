import json
import os

import pytest
import requests

import auth
import storage as ps
from storage import schema
from fakes import FakeGitHub

ALICE, BOB = auth.user_key("alice@example.com"), auth.user_key("bob@example.com")


@pytest.fixture
def local(tmp_path):
    return ps.LocalBackend(str(tmp_path / "portfolios.json"))


def github(fake=None, **kwargs):
    backend = ps.GitHubBackend("token", "owner/repo", **kwargs)
    backend.session = fake or FakeGitHub()
    return backend


# ---------- 로컬 백엔드 / 포트폴리오 ----------

def test_missing_local_file_reads_as_empty(local):
    assert ps.load(local) == schema.empty_portfolios_document()


def test_saved_portfolio_round_trips_with_korean_text(local):
    ps.upsert_portfolio(local, ps.make_portfolio("내 포트", {"A": 0.6, "B": 0.4}, ALICE, "앨리스"))
    saved = ps.load(local)["portfolios"]
    assert saved[0]["name"] == "내 포트" and saved[0]["weights"] == {"A": 0.6, "B": 0.4}
    assert saved[0]["owner_name"] == "앨리스" and saved[0]["tickers"] == ["A", "B"]
    assert "내 포트" in open(local.path, encoding="utf-8").read()  # ensure_ascii=False


def test_same_name_by_same_owner_overwrites_and_keeps_id(local):
    ps.upsert_portfolio(local, ps.make_portfolio("안", {"A": 1.0}, ALICE, "앨리스"))
    first_id = ps.load(local)["portfolios"][0]["id"]
    ps.upsert_portfolio(local, ps.make_portfolio("안", {"A": 0.5, "B": 0.5}, ALICE, "앨리스"))
    portfolios = ps.load(local)["portfolios"]
    assert len(portfolios) == 1 and portfolios[0]["id"] == first_id and portfolios[0]["weights"]["B"] == 0.5


def test_other_users_portfolio_name_cannot_be_overwritten(local):
    ps.upsert_portfolio(local, ps.make_portfolio("공용안", {"A": 1.0}, ALICE, "앨리스"))
    with pytest.raises(ps.StoreError, match="앨리스"):
        ps.upsert_portfolio(local, ps.make_portfolio("공용안", {"B": 1.0}, BOB, "밥"))
    assert ps.load(local)["portfolios"][0]["weights"] == {"A": 1.0}


def test_delete_only_removes_own_portfolios(local):
    ps.upsert_portfolio(local, ps.make_portfolio("앨리스안", {"A": 1.0}, ALICE, "앨리스"))
    ps.upsert_portfolio(local, ps.make_portfolio("밥안", {"B": 1.0}, BOB, "밥"))
    ids = [p["id"] for p in ps.load(local)["portfolios"]]
    remaining = ps.delete_portfolios(local, ids, BOB)["portfolios"]
    assert [p["name"] for p in remaining] == ["앨리스안"]


def test_legacy_portfolios_without_owner_can_be_modified_by_anyone(local):
    legacy = {"id": "old00001", "name": "구버전", "tickers": ["A"], "weights": {"A": 1.0}}
    with open(local.path, "w", encoding="utf-8") as f:
        json.dump({"portfolios": [legacy]}, f)
    assert ps.can_modify(legacy, BOB)
    assert ps.delete_portfolios(local, ["old00001"], BOB)["portfolios"] == []


def test_import_skips_other_users_items_and_assigns_owner_to_ownerless_ones(local):
    ps.upsert_portfolio(local, ps.make_portfolio("앨리스안", {"A": 1.0}, ALICE, "앨리스"))
    alice_id = ps.load(local)["portfolios"][0]["id"]
    incoming = [
        {"id": alice_id, "name": "앨리스안", "tickers": ["A"], "weights": {"A": 0.1}},
        {"id": "newid001", "name": "외부안", "tickers": ["B"], "weights": {"B": 1.0}},
    ]
    data, skipped = ps.import_portfolios(local, incoming, BOB, "밥")
    by_name = {p["name"]: p for p in data["portfolios"]}
    assert skipped == 1
    assert by_name["앨리스안"]["weights"] == {"A": 1.0}
    assert by_name["외부안"]["owner_key"] == BOB


@pytest.mark.parametrize("bad", [[], {"portfolios": "x"}, {"portfolios": [{"id": 1}]},
                                 {"portfolios": [{"id": "x", "name": "n", "tickers": ["A"], "weights": {"B": 1}}]}])
def test_import_validation_rejects_malformed_backups(bad):
    with pytest.raises(ps.StoreError):
        ps.validate_import(bad)


# ---------- 보유 수량 ----------

def test_holdings_round_trip_and_do_not_store_portfolios_key(local):
    ps.save_holdings(local, {"360750.KS": 3221, "411060.KS": 0})
    assert ps.load_holdings(local) == {"360750.KS": 3221, "411060.KS": 0}
    assert "portfolios" not in json.load(open(local.path, encoding="utf-8"))


@pytest.mark.parametrize("bad", [{"X": -1}, {"X": 1.5}, {"X": "3"}, {"X": True and 2.0}])
def test_holdings_must_be_non_negative_integers(local, bad):
    with pytest.raises(ps.StoreError):
        ps.save_holdings(local, bad)


def test_local_repo_paths_map_under_data_folder():
    assert ps.LocalBackend.for_repo_path("data/portfolios.json").path == ps.LOCAL_PATH
    users = ps.LocalBackend.for_repo_path(ps.user_path("abc123")).path.replace("\\", "/")
    assert users.endswith("/data/users/abc123.json")


# ---------- get_backend 선택 ----------

def test_backend_is_local_without_github_secrets():
    assert isinstance(ps.get_backend({}), ps.LocalBackend)


def test_backend_is_github_with_secrets_and_default_branch():
    backend = ps.get_backend({"GITHUB_TOKEN": "t", "GITHUB_REPO": "o/r"})
    assert isinstance(backend, ps.GitHubBackend) and backend.branch == "data" and backend.persistent


def test_backend_uses_custom_branch_and_path():
    backend = ps.get_backend({"GITHUB_TOKEN": "t", "GITHUB_REPO": "o/r", "GITHUB_DATA_BRANCH": "x"}, ps.user_path("k"))
    assert backend.branch == "x" and backend.path == "users/k.json"


# ---------- GitHub 백엔드 (가짜 서버) ----------

def test_github_missing_file_reads_as_empty():
    # 백엔드 자체는 문서 종류(포트폴리오/보유 수량)를 모르므로 빈 dict만 돌려준다. 기본 문서 모양을
    # 채우는 것은 schema.load_portfolios_document/load_holdings_document의 몫이다.
    assert github().read() == ({}, None)


def test_first_save_creates_data_branch_then_writes_file():
    fake = FakeGitHub(branch_exists=False)
    backend = github(fake)
    ps.upsert_portfolio(backend, ps.make_portfolio("g1", {"A": 1.0}, ALICE, "앨리스"))
    order = [c[0] for c in fake.calls]
    assert ("POST", "/repos/owner/repo/git/refs") in fake.calls
    assert order.index("POST") < order.index("PUT")
    assert json.loads(fake.file)["portfolios"][0]["name"] == "g1"


def test_existing_branch_is_not_recreated():
    fake = FakeGitHub(branch_exists=True)
    ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))
    assert not any(c[0] == "POST" for c in fake.calls)


def test_conflict_is_retried_with_fresh_data():
    fake = FakeGitHub(branch_exists=True)
    backend = github(fake)
    ps.upsert_portfolio(backend, ps.make_portfolio("g1", {"A": 1.0}))
    fake.conflicts_left = 1
    ps.upsert_portfolio(backend, ps.make_portfolio("g2", {"B": 1.0}))
    assert [p["name"] for p in json.loads(fake.file)["portfolios"]] == ["g1", "g2"]
    assert len(fake.puts()) == 3  # g1, g2(409), g2(재시도)


def test_persistent_conflict_raises_after_three_attempts():
    fake = FakeGitHub(branch_exists=True)
    fake.conflicts_left = 99
    with pytest.raises(ps.ConflictError):
        ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))
    assert len(fake.puts()) == 3


@pytest.mark.parametrize("method,needle,status", [("GET", "/contents/", 401), ("GET", "/contents/", 403), ("GET", "/contents/", 500)])
def test_read_errors_surface_as_store_error_with_status(method, needle, status):
    fake = FakeGitHub()
    fake.forced[(method, needle)] = (status, {"message": "nope"})
    with pytest.raises(ps.StoreError, match=str(status)):
        github(fake).read()


def test_write_permission_error_surfaces_as_store_error():
    fake = FakeGitHub(branch_exists=True)
    fake.forced[("PUT", "/contents/")] = (403, {"message": "Resource not accessible"})
    with pytest.raises(ps.StoreError, match="403"):
        ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))


def test_network_failure_surfaces_as_store_error():
    fake = FakeGitHub()
    fake.raise_on_request = requests.ConnectionError("boom")
    with pytest.raises(ps.StoreError, match="연결 실패"):
        github(fake).read()


def test_branch_lookup_failure_is_reported():
    fake = FakeGitHub()
    fake.forced[("GET", "/git/ref/heads/data")] = (403, {})
    with pytest.raises(ps.StoreError, match="403"):
        ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))


# ---------- 저장소 안정화: 브랜치 생성 경쟁, 손상/형식 오류, 스키마 버전 (단계 4a) ----------

def test_branch_creation_race_is_tolerated():
    # 두 요청이 동시에 최초 저장을 시도하면 둘 다 브랜치가 없다고 보고 생성을 시도할 수 있다.
    # 나중 요청은 422(이미 존재)를 받는데, 실제로 브랜치가 있으면 오류로 보지 않고 계속 진행한다.
    fake = FakeGitHub(branch_exists=False)
    fake.race_on_branch_create = True
    ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))
    assert json.loads(fake.file)["portfolios"][0]["name"] == "g1"


def test_branch_creation_failure_that_is_not_a_race_still_raises():
    fake = FakeGitHub(branch_exists=False)
    fake.forced[("POST", "/git/refs")] = (422, {"message": "Validation Failed", "errors": ["something else"]})
    # 재조회해도 브랜치가 없다(경쟁이 아니라 진짜 실패) → 원래 오류를 보고한다
    with pytest.raises(ps.StoreError, match="422"):
        ps.upsert_portfolio(github(fake), ps.make_portfolio("g1", {"A": 1.0}))


def test_corrupted_json_is_reported_as_store_error():
    fake = FakeGitHub(branch_exists=True, file_bytes=b"not json at all")
    with pytest.raises(ps.StoreError, match="손상"):
        ps.load(github(fake))


def test_corrupted_local_file_is_reported_as_store_error(local):
    with open(local.path, "w", encoding="utf-8") as f:
        f.write("not json at all")
    with pytest.raises(ps.StoreError, match="손상"):
        ps.load(local)


def test_wrong_structure_is_rejected_on_read():
    fake = FakeGitHub(branch_exists=True, file_bytes=json.dumps({"portfolios": "oops"}).encode())
    with pytest.raises(ps.StoreError, match="portfolios"):
        ps.load(github(fake))


def test_malformed_portfolio_item_is_rejected_on_read():
    bad = json.dumps({"portfolios": [{"id": "x", "name": "누락됨"}]}).encode()
    fake = FakeGitHub(branch_exists=True, file_bytes=bad)
    with pytest.raises(ps.StoreError, match="tickers"):
        ps.load(github(fake))


def test_wrong_structure_is_rejected_when_reading_holdings(local):
    with open(local.path, "w", encoding="utf-8") as f:
        json.dump({"holdings": "oops"}, f)
    with pytest.raises(ps.StoreError):
        ps.load_holdings(local)


# ---------- 스키마 버전과 마이그레이션 ----------

def test_new_portfolios_document_is_stamped_with_the_current_schema_version(local):
    ps.upsert_portfolio(local, ps.make_portfolio("안", {"A": 1.0}))
    assert ps.load(local)["schema_version"] == schema.SCHEMA_VERSION


def test_new_holdings_document_is_stamped_with_the_current_schema_version(local):
    ps.save_holdings(local, {"A": 1})
    raw = json.load(open(local.path, encoding="utf-8"))
    assert raw["schema_version"] == schema.SCHEMA_VERSION


def test_legacy_file_without_schema_version_is_migrated_on_write(local):
    legacy = {"portfolios": [{"id": "old00001", "name": "구버전", "tickers": ["A"], "weights": {"A": 1.0}}]}
    with open(local.path, "w", encoding="utf-8") as f:
        json.dump(legacy, f)
    assert "schema_version" not in json.load(open(local.path, encoding="utf-8"))
    ps.upsert_portfolio(local, ps.make_portfolio("새안", {"B": 1.0}))
    raw = json.load(open(local.path, encoding="utf-8"))
    assert raw["schema_version"] == schema.SCHEMA_VERSION
    assert {p["name"] for p in raw["portfolios"]} == {"구버전", "새안"}
