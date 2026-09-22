import os
import shutil
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILES = [
    "app_advanced.py", "auth.py", "portfolio_engine.py", "rebalance_engine.py",
    "custom_backtest.py", "rebalancing_guide.py", "portfolio_store.py",
]
APP_MODULES = [f[:-3] for f in APP_FILES]

sys.path.insert(0, os.path.join(ROOT, "tests"))
from fakes import make_download  # noqa: E402


def _random_walk(columns, periods=300, seed=42, start="2024-01-02"):
    idx = pd.bdate_range(start, periods=periods)
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.01, size=(periods, len(columns)))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=columns)


@pytest.fixture
def prices():
    """결정적 합성 시세(결측 없음)."""
    return _random_walk(["AAA.KS", "BBB.KS", "CCC.KS", "DDD.KS"])


@pytest.fixture
def gap_prices():
    """한 종목(B)에 상장 전 결측 2일 + 중간 결측 1일이 있는 시세."""
    idx = pd.bdate_range("2024-01-01", periods=6)
    return pd.DataFrame({
        "A": [100.0, 101, 102, 103, 104, 105],
        "B": [np.nan, np.nan, 50.0, np.nan, 52.0, 53.0],
    }, index=idx)


@pytest.fixture
def krx_prices():
    """앱 기본 티커 6개에 대한 합성 시세."""
    import portfolio_engine as pe
    return _random_walk(sorted(pe.DEFAULT_TARGET_WEIGHTS), seed=7)


@pytest.fixture
def fake_yahoo(monkeypatch, krx_prices):
    """앱과 엔진이 호출하는 yfinance.download를 합성 시세로 대체한다."""
    import yfinance
    monkeypatch.setattr(yfinance, "download", make_download(krx_prices))
    return krx_prices


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """
    앱 소스를 임시 폴더로 복사해 AppTest를 실행하기 위한 격리 환경.
    로컬 저장소(data/) 파일이 저장소 폴더에 생기지 않고, 테스트 사이에 캐시가 공유되지 않게 한다.
    """
    import streamlit as st
    for name in APP_FILES:
        shutil.copy(os.path.join(ROOT, name), tmp_path / name)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for m in APP_MODULES:
        sys.modules.pop(m, None)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield tmp_path
    for m in APP_MODULES:
        sys.modules.pop(m, None)
    st.cache_resource.clear()
    st.cache_data.clear()


@pytest.fixture
def run_app(app_env, fake_yahoo):
    """secrets를 지정해 앱을 한 번 실행하고 AppTest 객체를 돌려주는 함수."""
    from streamlit.testing.v1 import AppTest

    def _run(secrets=None):
        at = AppTest.from_file(str(app_env / "app_advanced.py"), default_timeout=120)
        for key, value in (secrets or {}).items():
            at.secrets[key] = value
        return at.run()
    _run.app_env = app_env
    return _run
