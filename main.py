"""
日本株 自動売買シミュレーター（ペーパートレード版） - メインアプリ

起動方法:
    streamlit run main.py

※ 本アプリは仮想売買（ペーパートレード）専用です。実口座への発注は一切行いません。

【スマホ/クラウド公開対応】
・PAPER_MODE の判定は assert ではなく if文 + st.stop() による確実な停止に変更。
・設定(期間・リスクパラメータ)は「サイドバー」と「メイン画面上部のexpander」の
  両方から操作できるが、st.session_state のコールバックで相互同期しており、
  二重管理にはならない（_linked_slider を参照）。
・「かんたん表示 / 詳細表示」を切り替えられるようにし、情報量を調整できる。
・バックテスト計算ロジック（backtester.py 等）には一切手を加えていない。
"""
import streamlit as st

from config import DEFAULT_UNIVERSE, DEFAULT_BACKTEST_YEARS, INITIAL_CAPITAL, PAPER_MODE, SCREENING_UNIVERSE
from data_provider import YFinanceDataProvider, DataProviderError
from backtester import Backtester
from indicators import add_all_indicators
from strategy import evaluate_row, judgement_label
from trade_logger import trades_to_csv_bytes
from risk_manager import (
    RiskSettings, max_shares_by_risk, max_shares_by_position_limit,
    calc_stop_loss_price, can_afford_min_lot, min_purchase_amount,
)
import screening
import dashboard as dash

st.set_page_config(
    page_title="日本株 自動売買シミュレーター",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",  # スマホでは自動的にサイドバーは折りたたまれる
)

# ----------------------------------------------------------------
# 安全装置: PAPER_MODEがFalseの場合はアプリを起動させない。
# assert はPythonの最適化オプション(-O)で無効化される可能性があるため、
# if文 + st.stop() による確実な停止に変更している。
# ----------------------------------------------------------------
if not PAPER_MODE:
    st.error(
        "⛔ 安全装置エラー: PAPER_MODE が False になっているため、このアプリは起動できません。\n"
        "本アプリは仮想売買（ペーパートレード）専用として設計されており、実売買機能は含まれていません。"
    )
    st.stop()

dash.inject_global_css()


# ==================================================================
# セッション状態の初期化
# ==================================================================
if "universe" not in st.session_state:
    st.session_state.universe = {item["code"]: item["name"] for item in DEFAULT_UNIVERSE}
if "backtest_result" not in st.session_state:
    st.session_state.backtest_result = None
if "raw_price_data" not in st.session_state:
    st.session_state.raw_price_data = None
if "display_mode" not in st.session_state:
    st.session_state.display_mode = "かんたん表示"
if "screening_result" not in st.session_state:
    st.session_state.screening_result = None
if "screening_errors" not in st.session_state:
    st.session_state.screening_errors = []

_SETTINGS_DEFAULTS = {
    "years": DEFAULT_BACKTEST_YEARS,
    "max_loss_pct": 1.0,
    "max_position_pct": 25,
    "max_positions_n": 4,
    "stop_loss_pct": 5.0,
}


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_price_data(codes: tuple, years: int):
    provider = YFinanceDataProvider()
    data, errors = {}, []
    for code in codes:
        try:
            data[code] = provider.get_history(code, years)
        except DataProviderError as e:
            errors.append(str(e))
    return data, errors


@st.cache_data(show_spinner=False, ttl=3600 * 4)
def fetch_screening_results(universe_items: tuple):
    """
    広域スクリーニングの実行結果をキャッシュする（4時間）。
    「毎日」使う想定のため、日中に何度もタップしても再取得しないようにしている。
    キャッシュを無視して最新化したい場合は、ブラウザをリロードするか
    しばらく時間を置いてから再実行してください。
    """
    universe = dict(universe_items)
    rows, errors = screening.run_screening(universe, years=screening.SCREENING_HISTORY_YEARS)
    return rows, errors


def render_screening_section():
    """
    【広域スクリーニング】バックテスト対象の10銘柄とは別に、大型株ユニバース
    （config.SCREENING_UNIVERSE、約100銘柄）に対して現在の買いシグナルを一覧表示する。
    バックテストの実行有無にかかわらず、いつでも単独で使える。
    """
    with st.expander("🔍 広域スクリーニング（大型株ユニバース）", expanded=False):
        st.caption(
            f"バックテスト対象銘柄とは別に、大型株ユニバース（約{len(SCREENING_UNIVERSE)}銘柄）"
            "全体に対して、現在の買いシグナルを機械的に判定します。"
            "銘柄リストは独自にまとめた概算であり、JPX公式のTOPIX100構成銘柄とは"
            "完全には一致しない場合があります（config.pyのSCREENING_UNIVERSEで編集可能）。"
        )
        judgement_filter = st.selectbox(
            "表示する判定", ["すべて", "買い候補+様子見", "買い候補のみ"],
            key="screening_filter",
        )
        run_clicked = st.button(
            "🔍 スクリーニング実行", type="primary", width="stretch", key="run_screening",
        )

        if run_clicked:
            universe = {item["code"]: item["name"] for item in SCREENING_UNIVERSE}
            with st.spinner(f"{len(universe)}銘柄のデータを取得・判定中...(1〜2分程度かかる場合があります)"):
                rows, errors = fetch_screening_results(tuple(universe.items()))
            st.session_state.screening_result = rows
            st.session_state.screening_errors = errors

        if st.session_state.screening_errors:
            st.warning(
                f"{len(st.session_state.screening_errors)}銘柄のデータ取得に失敗しました"
                "（取得できた銘柄のみ結果に表示しています）。"
            )

        if st.session_state.screening_result:
            dash.render_screening_results(st.session_state.screening_result, judgement_filter)
        else:
            st.info("「スクリーニング実行」を押すと、大型株ユニバース全体の売買シグナルを判定します。")


# ==================================================================
# 設定値の相互同期ヘルパー
#
# サイドバー(PC向け)とメイン画面上部のexpander(スマホ向け)の両方に
# 同じ設定ウィジェットを配置するため、Streamlitの制約上まったく同じkeyは使えない。
# そこで「自分のkey」と「相方のkey」を持たせ、on_changeで相方のsession_stateへ
# 値を書き込むことで、どちらを操作しても常に同期された状態を保つ。
# ==================================================================
def _linked_slider(container, label: str, key_self: str, key_other: str, default,
                    min_value, max_value, step=None, format=None, help=None):
    if key_self not in st.session_state:
        st.session_state[key_self] = st.session_state.get(key_other, default)

    def _on_change():
        st.session_state[key_other] = st.session_state[key_self]

    kwargs = dict(min_value=min_value, max_value=max_value, key=key_self, on_change=_on_change, help=help)
    if step is not None:
        kwargs["step"] = step
    if format is not None:
        kwargs["format"] = format
    return container.slider(label, **kwargs)


def _render_universe_editor(container, location_suffix: str):
    """対象銘柄の一覧・削除・追加UI。universe自体は共有dictなので、ウィジェットのkeyだけ
    location_suffixで一意にすれば、サイドバーとexpanderのどちらから操作しても同じデータを編集できる。
    """
    for code, name in list(st.session_state.universe.items()):
        c1, c2 = container.columns([4, 1])
        c1.write(f"{code} {name}")
        if c2.button("削除", key=f"del_{location_suffix}_{code}"):
            del st.session_state.universe[code]
            st.rerun()

    with container.form(f"add_stock_form_{location_suffix}", clear_on_submit=True):
        st.write("銘柄を追加")
        new_code = st.text_input("証券コード（例: 7203）", key=f"new_code_{location_suffix}")
        new_name = st.text_input("銘柄名（例: トヨタ自動車）", key=f"new_name_{location_suffix}")
        submitted = st.form_submit_button("追加")
        if submitted and new_code.strip():
            st.session_state.universe[new_code.strip()] = new_name.strip() or new_code.strip()
            st.rerun()


def _render_settings_widgets(container, location_suffix: str):
    """期間・リスクパラメータのスライダー群。サイドバー/expanderの両方から呼び出す共通部品。"""
    years = _linked_slider(
        container, "過去何年分のデータを使用するか",
        key_self=f"years_{location_suffix}", key_other=f"years_{'expander' if location_suffix == 'sidebar' else 'sidebar'}",
        default=_SETTINGS_DEFAULTS["years"], min_value=1, max_value=10,
    )
    max_loss_pct = _linked_slider(
        container, "1取引最大リスク（総資産に対する割合）",
        key_self=f"max_loss_pct_{location_suffix}",
        key_other=f"max_loss_pct_{'expander' if location_suffix == 'sidebar' else 'sidebar'}",
        default=_SETTINGS_DEFAULTS["max_loss_pct"], min_value=0.5, max_value=3.0, step=0.1, format="%.1f%%",
        help="1回の取引で許容する最大損失。この値からポジションサイズが逆算されます。",
    )
    max_position_pct = _linked_slider(
        container, "1銘柄最大投資比率",
        key_self=f"max_position_pct_{location_suffix}",
        key_other=f"max_position_pct_{'expander' if location_suffix == 'sidebar' else 'sidebar'}",
        default=_SETTINGS_DEFAULTS["max_position_pct"], min_value=10, max_value=50, step=1, format="%d%%",
        help="1銘柄に投入できる金額の総資産に対する上限。",
    )
    max_positions_n = _linked_slider(
        container, "最大同時保有数",
        key_self=f"max_positions_n_{location_suffix}",
        key_other=f"max_positions_n_{'expander' if location_suffix == 'sidebar' else 'sidebar'}",
        default=_SETTINGS_DEFAULTS["max_positions_n"], min_value=1, max_value=5, step=1,
        help="同時に保有できる銘柄数の上限。",
    )
    stop_loss_pct = _linked_slider(
        container, "損切りライン（購入価格からの下落率）",
        key_self=f"stop_loss_pct_{location_suffix}",
        key_other=f"stop_loss_pct_{'expander' if location_suffix == 'sidebar' else 'sidebar'}",
        default=_SETTINGS_DEFAULTS["stop_loss_pct"], min_value=2.0, max_value=10.0, step=0.5, format="-%.1f%%",
        help="購入価格からこの比率だけ下落したら損切りします。",
    )
    return years, max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct


def _build_risk_settings(max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct) -> RiskSettings:
    return RiskSettings(
        max_loss_per_trade_ratio=max_loss_pct / 100.0,
        max_position_ratio=max_position_pct / 100.0,
        max_positions=int(max_positions_n),
        stop_loss_ratio=-abs(stop_loss_pct) / 100.0,
    )


# ==================================================================
# サイドバー（PC向け・従来どおり維持）
# ==================================================================
def render_sidebar():
    st.sidebar.header("設定")
    mode_label = "📝 ペーパートレード（仮想売買）" if PAPER_MODE else "⚠️ 実売買"
    st.sidebar.markdown(f"**モード:** {mode_label}")
    st.sidebar.markdown("---")

    st.sidebar.subheader("バックテスト期間・リスクパラメータ")
    years, max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct = _render_settings_widgets(
        st.sidebar, "sidebar"
    )

    st.sidebar.subheader("対象銘柄")
    _render_universe_editor(st.sidebar, "sidebar")

    st.sidebar.markdown("---")
    run = st.sidebar.button("バックテスト実行", type="primary", width="stretch", key="run_sidebar")
    return years, max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct, run


# ==================================================================
# メイン画面上部の設定expander（スマホ向け・PCでも利用可）
# ==================================================================
def render_settings_expander(expanded: bool):
    with st.expander("⚙️ バックテスト設定（期間・リスク・対象銘柄）", expanded=expanded):
        st.caption("スマートフォンではここから設定・実行できます（サイドバーと内容は連動しています）。")
        years, max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct = _render_settings_widgets(
            st, "expander"
        )

        st.markdown("**対象銘柄**")
        _render_universe_editor(st, "expander")

        run = st.button(
            "🚀 バックテスト実行", type="primary", width="stretch", key="run_expander"
        )
    return years, max_loss_pct, max_position_pct, max_positions_n, stop_loss_pct, run


def render_display_mode_toggle():
    st.radio(
        "表示モード", options=["かんたん表示", "詳細表示"],
        key="display_mode", horizontal=True,
        help="かんたん表示では主要な情報のみ、詳細表示ではすべての指標・タブを表示します。",
    )


# ==================================================================
# メイン処理
# ==================================================================
def main():
    dash.render_header()
    render_display_mode_toggle()
    is_simple_mode = st.session_state.display_mode == "かんたん表示"

    # バックテストの実行有無にかかわらず、いつでも使える広域スクリーニング
    render_screening_section()

    has_result_before = st.session_state.backtest_result is not None

    # --- 設定UI: サイドバー(PC) + メイン画面上部expander(スマホ) の両方を描画 ---
    (years_sb, max_loss_sb, max_pos_ratio_sb, max_positions_sb, stop_loss_sb, run_sb) = render_sidebar()
    (years_ex, max_loss_ex, max_pos_ratio_ex, max_positions_ex, stop_loss_ex, run_ex) = render_settings_expander(
        expanded=not has_result_before
    )

    # サイドバーとexpanderは on_change で常に同期されているため、どちらの戻り値を使っても同じ値になる。
    years = years_sb
    risk_settings = _build_risk_settings(max_loss_sb, max_pos_ratio_sb, max_positions_sb, stop_loss_sb)
    run = run_sb or run_ex

    if run:
        codes = tuple(st.session_state.universe.keys())
        if not codes:
            st.error("対象銘柄が登録されていません。銘柄を追加してください。")
            return

        with st.spinner("株価データを取得中..."):
            price_data, errors = fetch_price_data(codes, years)

        if errors:
            st.warning("一部銘柄のデータ取得に失敗しました:\n" + "\n".join(f"- {e}" for e in errors))
        if not price_data:
            st.error("データを取得できませんでした。銘柄コードやネットワーク接続を確認してください。")
            return

        st.session_state.raw_price_data = price_data
        names = {c: st.session_state.universe.get(c, c) for c in price_data.keys()}

        with st.spinner("バックテストを実行中..."):
            bt = Backtester(price_data, names, initial_capital=INITIAL_CAPITAL, settings=risk_settings)
            result = bt.run()

        st.session_state.backtest_result = result
        st.success("バックテストが完了しました。")

    result = st.session_state.backtest_result

    if result is None:
        st.info("👆 上の「バックテスト設定」またはサイドバーから設定を選択し、バックテストを実行してください。")
        return

    pf = result.portfolio

    # 最新終値の取得（保有銘柄評価用・シグナル画面用）
    latest_close = {}
    if not result.equity_df.empty and st.session_state.raw_price_data:
        last_date = result.equity_df.index[-1]
        for code, df in st.session_state.raw_price_data.items():
            if last_date in df.index:
                latest_close[code] = float(df.loc[last_date, "Close"])
            elif not df.empty:
                latest_close[code] = float(df["Close"].iloc[-1])

    dash_metrics = dict(result.metrics)
    dash_metrics["現金"] = pf.cash
    dash_metrics["株式評価額"] = pf.stock_value(latest_close)

    # ---- ホーム画面の推奨順序: 総資産・利益率 → 資産推移グラフ → 成績サマリー → 診断 → 詳細タブ ----
    if is_simple_mode:
        dash.render_quick_summary(dash_metrics)
    else:
        dash.render_dashboard_cards(dash_metrics)

    st.markdown("### 資産推移グラフ")
    dash.render_equity_chart(result.equity_df, result.buy_hold_equity_df, compact=is_simple_mode)

    if is_simple_mode:
        # ---- かんたん表示: 現在の買いシグナルを資産推移の直後に表示 ----
        st.markdown("### 現在の買いシグナル")
        _render_buy_signal_section(result, latest_close, dash_metrics, pf)
        st.info("その他の詳細な指標・履歴・診断は「詳細表示」に切り替えるとご覧いただけます。")
        return

    # ---- 詳細表示 ----
    dash.render_settings_used(result.settings)

    st.markdown("### 成績サマリー（戦略 vs Buy & Hold）")
    dash.render_metrics_table(result.metrics, result.buy_hold_metrics)

    dash.render_buy_hold_summary(result.buy_hold_metrics)
    dash.render_diagnostics(result.diagnostics)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["保有銘柄", "売買履歴", "銘柄ごとの成績", "現在の買いシグナル", "資金不足ログ"]
    )

    with tab1:
        dash.render_positions_table(pf.positions, latest_close)

    with tab2:
        dash.render_trades_table(result.trades_df)
        if result.trades_df is not None and not result.trades_df.empty:
            csv_bytes = trades_to_csv_bytes(result.trades_df)
            st.download_button(
                "取引履歴をCSVでダウンロード", data=csv_bytes,
                file_name="trade_history.csv", mime="text/csv",
            )

    with tab3:
        dash.render_per_stock_performance(result.trades_df, st.session_state.universe)

    with tab4:
        st.caption("直近営業日の終値データに基づく現在の売買シグナル判定です。")
        _render_buy_signal_section(result, latest_close, dash_metrics, pf)

    with tab5:
        st.caption(
            "シグナルが出ていたにもかかわらず、資金管理ルール（現金不足・1銘柄最大投資比率・"
            "1取引最大リスク・最大保有銘柄数・新規停止条件など）により購入できなかった記録です。"
        )
        dash.render_skip_log(result.skip_log_df)


def _render_buy_signal_section(result, latest_close, dash_metrics, pf):
    """「現在の買いシグナル」の中身を組み立てる（かんたん表示・詳細表示の両方から呼び出す共通処理）"""
    current_equity = dash_metrics.get("最終資産", INITIAL_CAPITAL)
    current_cash = pf.cash

    signal_rows = []
    for code, df in (st.session_state.raw_price_data or {}).items():
        if df.empty:
            continue
        df_ind = add_all_indicators(df)
        last_row = df_ind.iloc[-1]
        check = evaluate_row(last_row)
        price = latest_close.get(code, float(last_row["Close"]))

        stop_price = calc_stop_loss_price(price, result.settings)
        shares_by_risk = max_shares_by_risk(current_equity, price, stop_price, result.settings)
        shares_by_pos = max_shares_by_position_limit(current_equity, price, result.settings)
        shares_by_cash = int(current_cash // (price * 100)) * 100 if price > 0 else 0
        purchasable_shares = max(min(shares_by_risk, shares_by_pos, shares_by_cash), 0)
        affordable = can_afford_min_lot(current_cash, current_equity, price, result.settings)

        signal_rows.append({
            "code": code,
            "name": st.session_state.universe.get(code, code),
            "judgement": judgement_label(check),
            "sma": check.sma_trend,
            "rsi": check.rsi_ok,
            "macd": check.macd_ok,
            "volume": check.volume_ok,
            "affordable": affordable,
            "purchasable_shares": purchasable_shares,
            "min_purchase_amount": min_purchase_amount(price),
        })
    dash.render_buy_signal_table(signal_rows)


if __name__ == "__main__":
    main()
