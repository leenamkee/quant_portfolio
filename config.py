"""종목 정보와 앱 전체가 공유하는 상수. 기본 종목·비중을 바꿀 때는 이 파일만 수정한다."""

TICKER_NAMES = {
    "273130.KS": "KODEX 종합채권(AA-이상)액티브",
    "284430.KS": "KODEX 200미국채혼합50",
    "360750.KS": "TIGER 미국S&P500",
    "411060.KS": "ACE KRX 금현물",
    "441640.KS": "KODEX 미국배당커버드콜액티브",
    "458730.KS": "TIGER 미국배당다우존스",
}

# DC형 퇴직연금 위험자산 70% 한도 준수: 안전자산(채권형, 주식 0%) 30% + 위험자산 70%
# 앱의 기본 티커/비중 입력값도 이 딕셔너리에서 만들어진다.
DEFAULT_TARGET_WEIGHTS = {
    "273130.KS": 0.30,  # KODEX 종합채권(AA-이상)액티브 - 안전자산
    "411060.KS": 0.07,  # ACE KRX 금현물 - 위험자산
    "360750.KS": 0.25,  # TIGER 미국S&P500 - 위험자산
    "284430.KS": 0.13,  # KODEX 200미국채혼합50 - 위험자산
    "441640.KS": 0.13,  # KODEX 미국배당커버드콜액티브 - 위험자산
    "458730.KS": 0.12,  # TIGER 미국배당다우존스 - 위험자산
}

# 화면 기본값
REBALANCE_OPTIONS = ("None", "M", "Q", "Y")
DEFAULT_REBALANCE = "M"
COMPARE_DEFAULT_REBALANCE = "Q"
DEFAULT_LOOKBACK_DAYS = 365 * 2
DEFAULT_INITIAL_CAPITAL = 10_000_000
CAPITAL_STEP = 1_000_000

# 성과 지표
TRADING_DAYS_PER_YEAR = 252
# 변동성이 이 값보다 작으면 부동소수 오차로 취급해 샤프 지수를 정의하지 않는다(A3: 오차만 있어도 샤프가 폭주하는 문제 방지)
VOLATILITY_EPSILON = 1e-9
SHARPE_LABEL = "샤프 지수 (무위험수익률 0% 가정)"


def format_sharpe(value):
    """화면 표시용 샤프 지수 문자열. 정의되지 않으면(변동성이 0에 가까우면) 값 대신 안내 문구를 보여준다."""
    if value is None or not isinstance(value, (int, float)) or value != value:  # NaN 검사
        return "정의 안 됨(변동성 0)"
    return f"{value:.2f}"

# 시세 캐시(프로세스 안의 모든 사용자 세션이 공유). 요청 수를 줄이되 장중 가격이 너무 낡지 않게 한다.
PRICE_HISTORY_TTL_SECONDS = 1800
LATEST_PRICE_TTL_SECONDS = 300


def rebalance_index(option):
    """selectbox 기본 선택 위치."""
    return REBALANCE_OPTIONS.index(option)


def frequency_from_option(option):
    """selectbox 선택값을 엔진 인자로 바꾼다("None" → None)."""
    return None if option == "None" else option
