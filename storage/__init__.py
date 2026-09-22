"""
포트폴리오·보유 수량 저장소.

내부적으로 세 파일로 나뉜다:
- schema.py: 저장 문서의 형태 검사와 스키마 버전
- backends.py: 실제 읽기/쓰기(로컬 파일, GitHub Contents API)
- repository.py: 포트폴리오/보유 수량에 대한 저장 로직(소유권, 병합, 검증)

바깥에서는 이 패키지를 하나의 모듈처럼 쓴다: `import storage as ps`.
"""
from .backends import DATA_PATH, GitHubBackend, LocalBackend, LOCAL_PATH, get_backend, user_path
from .schema import ConflictError, StoreError
from .repository import (
    can_modify,
    delete_portfolios,
    import_portfolios,
    load,
    load_holdings,
    make_portfolio,
    save_holdings,
    update,
    upsert_portfolio,
    validate_import,
)

__all__ = [
    "DATA_PATH", "GitHubBackend", "LocalBackend", "LOCAL_PATH", "get_backend", "user_path",
    "ConflictError", "StoreError",
    "can_modify", "delete_portfolios", "import_portfolios", "load", "load_holdings",
    "make_portfolio", "save_holdings", "update", "upsert_portfolio", "validate_import",
]
