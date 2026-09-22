from dataclasses import dataclass, field

import pandas as pd

from errors import ValidationError
from validation import validate_prices_frame


@dataclass
class Aligned:
    """
    종목들의 가격을 하나의 분석 구간으로 맞춘 결과.

    정책(§9-3 확정): **공통 관측 구간**만 쓴다. 모든 종목에 가격이 있는 구간(가장 늦게 시작한 종목의 첫 유효일 ~
    가장 일찍 끝난 종목의 마지막 유효일)으로 자르고, 그 안에서 일부 종목의 가격이 없는 날은 **제외**한다.
    앞 값으로 채우지 않는다(상장 전이나 거래 정지 구간의 수익률을 왜곡할 수 있음).
    """
    prices: pd.DataFrame
    start: pd.Timestamp
    end: pd.Timestamp
    first_valid: dict = field(default_factory=dict)  # {ticker: 첫 유효일}
    limiting_ticker: str = None                      # 분석 시작일을 늦춘(가장 늦게 시작한) 종목, 없으면 None
    dropped_days: int = 0                            # 공통 구간 안에서 가격 누락으로 제외한 거래일 수

    @property
    def days(self):
        return len(self.prices)


def align_prices(data):
    """가격 표를 공통 관측 구간으로 맞춘다. 종목 기간이 겹치지 않거나 거래일이 2일 미만이면 ValidationError."""
    validate_prices_frame(data)
    first = {ticker: data[ticker].first_valid_index() for ticker in data.columns}
    last = {ticker: data[ticker].last_valid_index() for ticker in data.columns}
    start, end = max(first.values()), min(last.values())
    if start > end:
        raise ValidationError(
            f"종목들의 가격 기간이 겹치지 않아 분석할 수 없습니다 (가장 늦게 시작: {start:%Y-%m-%d}, 가장 일찍 끝남: {end:%Y-%m-%d})."
        )
    window = data.loc[start:end]
    clean = window.dropna(how="any")
    if len(clean) < 2:
        raise ValidationError("모든 종목에 가격이 있는 공통 거래일이 부족합니다. 수익률 계산에는 최소 2거래일이 필요합니다.")
    earliest = min(first.values())
    limiting = next((t for t in data.columns if first[t] == start), None) if start > earliest else None
    return Aligned(prices=clean, start=clean.index[0], end=clean.index[-1], first_valid=first,
                   limiting_ticker=limiting, dropped_days=len(window) - len(clean))


def daily_returns(prices):
    """일간 수익률. 결측을 채우지 않는 수식이라 pandas 버전에 따라 결과가 달라지지 않는다."""
    return (prices / prices.shift(1) - 1).iloc[1:]
