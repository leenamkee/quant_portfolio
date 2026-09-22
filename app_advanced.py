import streamlit as st

import auth
import storage as ps
from ui import state
from ui.context import AppContext
from ui.tabs import compare, custom_portfolio, optimize, rebalance_guide

st.set_page_config(page_title="Quant Portfolio Manager", layout="wide")


@st.cache_resource
def get_store():
    return ps.get_backend(st.secrets)


store = get_store()

identity = auth.resolve_identity(st.user, st.secrets, store.persistent)
if identity.status == "login":
    st.title("📈 퀀트 포트폴리오 매니저")
    st.info("허용된 Google 계정으로 로그인해야 사용할 수 있습니다.")
    st.button("Google로 로그인", on_click=st.login, type="primary")
    st.stop()
if identity.status in ("denied", "misconfigured"):
    st.error(identity.message)
    if identity.status == "denied":
        st.button("다른 계정으로 로그인", on_click=st.logout)
    st.stop()


@st.cache_resource
def get_user_store(key):
    return ps.get_backend(st.secrets, ps.user_path(key))


st.sidebar.markdown(f"👤 **{identity.name}**")
if identity.dev:
    st.sidebar.caption("로그인 미설정: 로컬 개발 모드")
else:
    st.sidebar.caption(identity.email)
    st.sidebar.button("로그아웃", on_click=st.logout, key="logout_button")


def refresh_saved_portfolios():
    try:
        st.session_state[state.SAVED_PORTFOLIOS] = ps.load(store)["portfolios"]
        st.session_state[state.STORE_ERROR] = None
    except ps.StoreError as e:
        st.session_state.setdefault(state.SAVED_PORTFOLIOS, [])
        st.session_state[state.STORE_ERROR] = str(e)


if state.SAVED_PORTFOLIOS not in st.session_state:
    refresh_saved_portfolios()

ctx = AppContext(
    identity=identity,
    store=store,
    user_store=get_user_store(identity.key),
    refresh_saved_portfolios=refresh_saved_portfolios,
)

st.title("📈 퀀트 포트폴리오 구성 및 리밸런싱")
st.markdown("""
이 앱은 주식 포트폴리오를 최적화하고 리밸런싱 전략에 따른 성과를 시뮬레이션합니다.
또한 사용자 정의 포트폴리오의 백테스트와 현재 보유 수량 기반 리밸런싱 가이드를 제공합니다.
""")

tab1, tab2, tab3, tab4 = st.tabs(["자동 최적화", "사용자 정의 백테스트", "리밸런싱 가이드", "포트폴리오 비교"])

with tab1:
    optimize.render(ctx)
with tab2:
    custom_portfolio.render(ctx)
with tab3:
    rebalance_guide.render(ctx)
with tab4:
    compare.render(ctx)
