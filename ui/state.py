"""
세션 상태 키. 여러 탭이 함께 읽고 쓰는 키를 한 곳에 모아, 오타로 새 키가 조용히 생기는 것을 막는다.

한 탭 안에서만 쓰는 위젯 키(예: 날짜·자본 입력)는 그 탭 모듈에 그대로 둔다. 여기 모으는 것은
탭 경계를 넘나드는 키(예: 탭2가 저장하면 탭4가 보여줄 목록)와, 표 편집기처럼 여러 탭이 같은
모양으로 반복하는 키뿐이다.
"""
import streamlit as st

SAVED_PORTFOLIOS = "saved_portfolios"
STORE_ERROR = "store_error"
COMPARE_SELECTED = "compare_selected"

BT_TABLE = "bt_table"
BT_VERSION = "bt_version"
BT_LOADED = "bt_loaded"
BT_FLASH = "bt_flash"
SAVE_NAME = "save_name"

RB_TABLE = "rb_table"
RB_VERSION = "rb_version"


def ensure(key, factory):
    """세션 상태에 key가 없으면 factory()로 만들어 넣는다. 있으면 손대지 않는다."""
    if key not in st.session_state:
        st.session_state[key] = factory()
    return st.session_state[key]
