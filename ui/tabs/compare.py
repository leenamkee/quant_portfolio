"""탭4: 포트폴리오 비교. 저장된 포트폴리오 여러 개를 같은 기간·자본·주기로 백테스트해 나란히 비교한다."""
import json

import pandas as pd
import plotly.express as px
import streamlit as st

import market_data as md
import rebalance_engine as backtest_engine
import storage as ps
from alignment import align_prices
from config import COMPARE_DEFAULT_REBALANCE, TICKER_NAMES, format_sharpe
from errors import ValidationError
from ui import state
from ui.components import backtest_settings, show_error


def _render_compositions(saved):
    with st.expander(f"저장된 포트폴리오 구성 ({len(saved)}개)"):
        rows = []
        for p in saved:
            for t, w in p["weights"].items():
                rows.append({"포트폴리오": p["name"], "작성자": p.get("owner_name") or "-", "티커": t,
                             "종목명": TICKER_NAMES.get(t, t), "비중": f"{w:.1%}"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _run_comparison(chosen, cmp_start, cmp_end, cmp_capital, cmp_freq):
    with st.spinner("백테스트 중입니다..."):
        try:
            all_tickers = tuple(sorted({t for p in chosen for t in p["tickers"]}))
            prices = md.get_prices(list(all_tickers), cmp_start, cmp_end)
            curves, metric_rows = {}, []
            for p in chosen:
                missing = [t for t in p["tickers"] if t not in prices.columns]
                if missing:
                    st.warning(f"'{p['name']}': 데이터를 받지 못한 티커가 있어 제외했습니다 ({', '.join(missing)})")
                    continue
                try:
                    aligned = align_prices(prices[p["tickers"]])
                except ValidationError as e:
                    st.warning(f"'{p['name']}': {e} 제외했습니다.")
                    continue
                history = backtest_engine.backtest_rebalancing(aligned.prices, p["weights"], cmp_freq, cmp_capital)
                m = backtest_engine.calculate_metrics(history)
                curves[p["name"]] = history["Portfolio Value"]
                metric_rows.append({
                    "포트폴리오": p["name"],
                    "기간": f"{aligned.start:%Y-%m-%d} ~ {aligned.end:%Y-%m-%d}",
                    "총 수익률": f"{m['Total Return']:.2%}",
                    "연환산 수익률": f"{m['Annualized Return']:.2%}",
                    "연환산 변동성": f"{m['Annualized Volatility']:.2%}",
                    "샤프": format_sharpe(m['Sharpe Ratio']),
                    "MDD": f"{m['Max Drawdown']:.2%}",
                    "최종 가치(원)": f"{history['Portfolio Value'].iloc[-1]:,.0f}",
                })
            if not curves:
                st.error("비교할 수 있는 포트폴리오가 없습니다.")
                return
            st.subheader("성과 지표")
            st.dataframe(pd.DataFrame(metric_rows), width="stretch", hide_index=True)
            st.subheader("포트폴리오 가치 추이")
            fig = px.line(pd.DataFrame(curves), labels={"value": "포트폴리오 가치(원)", "variable": "포트폴리오"})
            st.plotly_chart(fig, width="stretch")
            st.caption("종목별 상장일이 달라 포트폴리오마다 실제 비교 기간이 다를 수 있습니다(위 '기간' 열 참고).")
        except Exception as e:
            show_error(e)


def _render_delete(ctx, saved):
    mine = {p["id"]: p["name"] for p in saved if ps.can_modify(p, ctx.identity.key)}
    with st.expander("삭제 (내가 만든 포트폴리오만)"):
        to_delete = st.multiselect("삭제할 포트폴리오", list(mine), format_func=mine.get, key="delete_selected")
        if st.button("선택 항목 삭제", key="delete_button") and to_delete:
            try:
                data = ps.delete_portfolios(ctx.store, to_delete, ctx.identity.key)
                st.session_state[state.SAVED_PORTFOLIOS] = data["portfolios"]
                st.success(f"{len(to_delete)}개 삭제했습니다.")
                st.rerun()
            except ps.StoreError as e:
                st.error(f"삭제 실패: {e}")


def _render_backup(ctx, saved):
    with st.expander("백업/복원 (JSON)"):
        st.download_button(
            "JSON 백업 다운로드",
            data=json.dumps({"portfolios": saved}, ensure_ascii=False, indent=2),
            file_name="portfolios.json",
            mime="application/json",
            key="backup_download",
        )
        uploaded = st.file_uploader("백업 JSON 불러오기 (id가 같으면 교체, 없으면 추가)", type="json", key="backup_upload")
        if uploaded is not None and st.button("가져오기", key="import_button"):
            try:
                incoming = ps.validate_import(json.load(uploaded))
                data, skipped = ps.import_portfolios(ctx.store, incoming, ctx.identity.key, ctx.identity.name)
                st.session_state[state.SAVED_PORTFOLIOS] = data["portfolios"]
                st.success(f"{len(incoming) - skipped}개를 가져왔습니다." + (f" (다른 사용자 소유 {skipped}개는 건너뜀)" if skipped else ""))
                st.rerun()
            except (ps.StoreError, json.JSONDecodeError) as e:
                st.error(f"가져오기 실패: {e}")


def render(ctx):
    st.header("저장된 포트폴리오 성과 비교")
    st.caption(f"저장소: {ctx.store.label}")
    if not ctx.store.persistent:
        st.warning("GitHub 저장소가 설정되지 않아 로컬 파일에 저장 중입니다. Streamlit Cloud에서는 앱이 재시작되면 사라지니, "
                   "Secrets에 GITHUB_TOKEN / GITHUB_REPO를 설정하거나 아래 '백업/복원'으로 JSON을 내려받아 보관하세요.")
    if st.session_state.get(state.STORE_ERROR):
        st.error(f"저장소 읽기 실패: {st.session_state[state.STORE_ERROR]}")

    if st.button("저장소에서 다시 불러오기", key="reload_portfolios"):
        ctx.refresh_saved_portfolios()
        st.rerun()

    saved = st.session_state[state.SAVED_PORTFOLIOS]

    if not saved:
        st.info("저장된 포트폴리오가 없습니다. '사용자 정의 백테스트' 탭에서 비중을 입력하고 '현재 구성 저장'을 눌러 추가하세요.")
    else:
        names = {p["id"]: p["name"] for p in saved}
        labels = {p["id"]: f"{p['name']} · {p.get('owner_name') or '작성자 없음'}" for p in saved}

        _render_compositions(saved)

        selected = st.multiselect("비교할 포트폴리오", list(names), default=list(names)[:4],
                                  format_func=labels.get, key=state.COMPARE_SELECTED)

        c1, c2, c3, c4 = st.columns(4)
        cmp_start, cmp_end, cmp_capital, cmp_freq = backtest_settings(
            "cmp", containers=(c1, c2, c3, c4), default_rebalance=COMPARE_DEFAULT_REBALANCE)

        if st.button("비교 실행", key="compare_button"):
            chosen = [p for p in saved if p["id"] in selected]
            if len(chosen) < 1:
                st.error("비교할 포트폴리오를 선택하세요.")
            else:
                _run_comparison(chosen, cmp_start, cmp_end, cmp_capital, cmp_freq)

        _render_delete(ctx, saved)

    _render_backup(ctx, saved)
