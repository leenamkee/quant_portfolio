"""저장 문서(포트폴리오/보유 수량 JSON)의 형태 검사와 버전 관리.

스키마 버전이 없는 기존 파일(버전을 도입하기 전에 저장된 데이터)도 그대로 읽을 수 있고, 다음에 그 파일에
쓸 때 버전이 채워진다(마이그레이션은 강제로 다시 쓰지 않고, 읽을 때 채우고 쓸 때 반영하는 식으로 자연스럽게 일어난다).
"""

SCHEMA_VERSION = 1
REQUIRED_PORTFOLIO_KEYS = {"id", "name", "tickers", "weights"}


class StoreError(Exception):
    pass


class ConflictError(StoreError):
    pass


def empty_portfolios_document():
    return {"schema_version": SCHEMA_VERSION, "portfolios": []}


def empty_holdings_document():
    return {"schema_version": SCHEMA_VERSION, "holdings": {}}


def load_portfolios_document(raw):
    """
    백엔드가 돌려준 원문 dict를 검사해 돌려준다.
    raw가 빈 dict({})면 파일이 아직 없다는 뜻이라 새 문서를 만든다. 그 외에는 형태를 검사하고,
    스키마 버전이 없으면 채워 넣는다.
    """
    if raw == {}:
        return empty_portfolios_document()
    if not isinstance(raw, dict) or not isinstance(raw.get("portfolios"), list):
        raise StoreError("저장된 데이터 형식이 올바르지 않습니다('portfolios' 목록이 없음).")
    for p in raw["portfolios"]:
        if not isinstance(p, dict) or not REQUIRED_PORTFOLIO_KEYS <= p.keys():
            raise StoreError("저장된 포트폴리오 항목 형식이 올바르지 않습니다(id/name/tickers/weights 필요).")
    raw.setdefault("schema_version", SCHEMA_VERSION)
    return raw


def load_holdings_document(raw):
    """load_portfolios_document과 같은 방식으로 보유 수량 문서를 검사한다."""
    if raw == {}:
        return empty_holdings_document()
    if not isinstance(raw, dict) or not isinstance(raw.get("holdings", {}), dict):
        raise StoreError("저장된 보유 수량 데이터 형식이 올바르지 않습니다.")
    raw.setdefault("schema_version", SCHEMA_VERSION)
    return raw
