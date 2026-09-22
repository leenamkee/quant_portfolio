"""포트폴리오·보유 수량에 대한 저장 로직: 소유권, 병합, 검증. 실제 읽기/쓰기는 backends.py에 맡긴다."""
import uuid
from datetime import datetime, timedelta, timezone

from .schema import (
    ConflictError,
    REQUIRED_PORTFOLIO_KEYS,
    StoreError,
    load_holdings_document,
    load_portfolios_document,
)

KST = timezone(timedelta(hours=9))


def load(backend):
    raw, _ = backend.read()
    return load_portfolios_document(raw)


def update(backend, mutate, message, document_loader=load_portfolios_document, retries=3):
    """
    읽기 → 형식 검증(document_loader) → mutate(data) → 쓰기.
    다른 저장과 충돌하면(409/422) 최신 데이터를 다시 읽어 재시도한다. 변경이 반영된 최신 데이터를 반환한다.
    """
    for _ in range(retries):
        raw, sha = backend.read()
        data = document_loader(raw)
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
    raw, _ = backend.read()
    return load_holdings_document(raw).get("holdings", {})


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
    return update(backend, mutate, "Update holdings", document_loader=load_holdings_document)


def validate_import(obj):
    """업로드된 JSON이 저장 포맷인지 검사하고 포트폴리오 리스트를 반환한다."""
    if not isinstance(obj, dict) or not isinstance(obj.get("portfolios"), list):
        raise StoreError("'portfolios' 목록이 있는 JSON이 아닙니다.")
    for p in obj["portfolios"]:
        if not isinstance(p, dict) or not REQUIRED_PORTFOLIO_KEYS <= p.keys():
            raise StoreError("포트폴리오 항목에 id/name/tickers/weights가 필요합니다.")
        if set(p["tickers"]) != set(p["weights"]):
            raise StoreError(f"'{p['name']}': tickers와 weights의 종목이 일치하지 않습니다.")
    return obj["portfolios"]
