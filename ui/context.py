"""탭 모듈에 넘기는 공유 상태를 하나로 묶는다. 탭 함수 시그니처가 인자 5~6개로 늘어나는 것을 막는다."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class AppContext:
    identity: object          # auth.Identity
    store: object              # 공용 포트폴리오 저장소 백엔드
    user_store: object         # 이 사용자의 보유 수량 저장소 백엔드
    refresh_saved_portfolios: Callable[[], None]
