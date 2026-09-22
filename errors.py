class ValidationError(ValueError):
    """사용자 입력이나 데이터가 계산에 쓸 수 없는 값일 때. 메시지는 화면에 그대로 보여줄 수 있다."""


class MarketDataError(RuntimeError):
    """시세 조회에 실패했거나 결과를 쓸 수 없을 때."""
