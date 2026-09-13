"""
Streamlit UI表示コンポーネント群。

【スマホ対応】
・カード表示(ダッシュボード/設定値/診断/Buy&Hold内訳)は、st.columns による固定列数ではなく
  CSS Grid(auto-fit, minmax)を使ったカードで表示する。JSによる端末幅判定を行わなくても、
  画面幅が狭くなれば自動的に列数が1〜2列に折り返される（PCでは3〜6列程度で表示される）。
・ボタン・入力欄はグローバルCSS(inject_global_css)でタップしやすいサイズに調整する。
・テーブルは重要な列を先頭に配置し、Streamlit標準の横スクロールに委ねる。
・資産推移グラフは compact=True 指定で高さと凡例フォントを縮小できる（「かんたん表示」用）。

計算ロジックには一切関与しない、表示専用のモジュールです。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import INITIAL_CAPITAL, TARGET_CAPITAL


# ======================================================================
# グローバルCSS（スマホでのタップしやすさ・カードの自動折り返し対応）
# ======================================================================
def inject_global_css() -> None:
    """
    アプリ全体に適用するCSS。安全なCSSのみを使用し、Streamlitの内部実装に
    深く依存する壊れやすいセレクタは避けている（stButton等の比較的安定したクラスのみ使用）。
    ページ内で一度だけ呼び出せばよい（main.py の先頭で呼び出す）。
    """
    st.markdown(
        """
        <style>
        /* ---- ボタン・入力欄をスマホでタップ/入力しやすいサイズに ---- */
        div.stButton > button, div.stDownloadButton > button {
            width: 100%;
            min-height: 3em;
            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 10px;
        }
        /* 「バックテスト実行」等のプライマリボタンをさらに目立たせる */
        div.stButton > button[kind="primary"] {
            font-size: 1.2rem;
            min-height: 3.5em;
            box-shadow: 0 2px 10px rgba(37, 99, 235, 0.35);
        }
        .stTextInput input, .stNumberInput input {
            font-size: 1rem;
            min-height: 2.6em;
        }
        /* 削除ボタン等の小さいボタンでも最低限のタップ領域を確保 */
        div.stButton > button {
            padding-top: 0.5em;
            padding-bottom: 0.5em;
        }

        /* ---- カードグリッド: 画面幅に応じて列数が自動的に変わる ---- */
        /* auto-fit + minmax により、PCでは横に並び、スマホでは自動的に1〜2列に折り返す。
           JavaScriptによる端末判定を使わずCSSのみで実現している。 */
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.6rem;
            margin: 0.4rem 0 1.1rem 0;
        }
        .metric-card {
            background: rgba(120, 120, 120, 0.08);
            border-radius: 10px;
            padding: 0.7rem 0.9rem;
            border: 1px solid rgba(120, 120, 120, 0.18);
        }
        .metric-card .metric-label {
            font-size: 0.78rem;
            opacity: 0.75;
            margin-bottom: 0.2rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .metric-card .metric-value {
            font-size: 1.15rem;
            font-weight: 700;
            line-height: 1.25;
            word-break: break-word;
        }

        /* ---- テーブルの横スクロールを保証（列がはみ出しても崩れない） ---- */
        div[data-testid="stDataFrame"] {
            overflow-x: auto;
        }

        /* ---- 見出しの余白をスマホでは少し詰める ---- */
        h1, h2, h3 {
            margin-top: 0.4em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_grid(items: list) -> None:
    """
    items: [(label, value_str), ...]
    CSSグリッドでカードを並べる。画面幅に応じて自動的に折り返される。
    """
    if not items:
        return
    cards_html = "".join(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'</div>'
        for label, value in items
    )
    st.markdown(f'<div class="metric-grid">{cards_html}</div>', unsafe_allow_html=True)


# ======================================================================
# ヘッダー・安全表示
# ======================================================================
def render_header() -> None:
    st.title("日本株 自動売買シミュレーター")
    st.caption("📝 ペーパートレード専用（仮想売買）。実際の発注は一切行いません。")


# ======================================================================
# ダッシュボードカード（総資産・現金・株式評価額・利益率・最大DD・勝率）
# ======================================================================
def render_dashboard_cards(metrics: dict) -> None:
    items = [
        ("総資産", f"¥{metrics.get('最終資産', 0):,.0f}"),
        ("現金", f"¥{metrics.get('現金', 0):,.0f}"),
        ("株式評価額", f"¥{metrics.get('株式評価額', 0):,.0f}"),
        ("利益率", f"{metrics.get('利益率', 0) * 100:.2f}%"),
        ("最大ドローダウン", f"{metrics.get('最大ドローダウン', 0) * 100:.2f}%"),
        ("勝率", f"{metrics.get('勝率', 0) * 100:.1f}%"),
    ]
    render_metric_grid(items)


def render_quick_summary(metrics: dict) -> None:
    """
    【スマホホーム画面対応】アプリを開いてすぐ分かる最重要2指標（総資産・利益率）だけを表示する。
    かんたん表示モードや、結果画面の一番上に使う想定。
    """
    items = [
        ("総資産", f"¥{metrics.get('最終資産', 0):,.0f}"),
        ("利益率", f"{metrics.get('利益率', 0) * 100:.2f}%"),
        ("最大ドローダウン", f"{metrics.get('最大ドローダウン', 0) * 100:.2f}%"),
    ]
    render_metric_grid(items)


# ======================================================================
# 資産推移グラフ
# ======================================================================
def render_equity_chart(equity_df: pd.DataFrame, bh_df: pd.DataFrame = None, compact: bool = False) -> None:
    """
    compact=True のとき（かんたん表示・スマホ想定）は高さと凡例フォントを抑える。
    width="stretch" は常に維持し、ピンチズーム・横スクロールを妨げない設定
    (config引数)で描画する。
    """
    fig = go.Figure()
    if equity_df is not None and not equity_df.empty:
        fig.add_trace(go.Scatter(
            x=equity_df.index, y=equity_df["equity"],
            mode="lines", name="戦略（トレンドフォロー）",
            line=dict(color="#2563eb", width=2),
        ))
    if bh_df is not None and not bh_df.empty:
        fig.add_trace(go.Scatter(
            x=bh_df.index, y=bh_df["equity"],
            mode="lines", name="Buy & Hold",
            line=dict(color="#9ca3af", width=2, dash="dot"),
        ))
    if equity_df is not None and not equity_df.empty:
        x_range = [equity_df.index.min(), equity_df.index.max()]
        fig.add_trace(go.Scatter(
            x=x_range, y=[INITIAL_CAPITAL, INITIAL_CAPITAL],
            mode="lines", name=f"初期資金 ({INITIAL_CAPITAL:,.0f}円)",
            line=dict(color="#94a3b8", width=1, dash="dash"),
        ))
        fig.add_trace(go.Scatter(
            x=x_range, y=[TARGET_CAPITAL, TARGET_CAPITAL],
            mode="lines", name=f"目標資産 ({TARGET_CAPITAL:,.0f}円)",
            line=dict(color="#ef4444", width=1, dash="dash"),
        ))

    height = 300 if compact else 450
    legend_font_size = 10 if compact else 12

    fig.update_layout(
        title="資産推移",
        xaxis_title="日付", yaxis_title="資産（円）",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=legend_font_size),
        ),
        height=height,
        margin=dict(l=10, r=10, t=70, b=10),
    )
    # scrollZoom: True でピンチズーム・スクロールを妨げない。displayModeBarはhoverでのみ表示し
    # スマホの限られた画面を圧迫しないようにする。
    st.plotly_chart(
        fig, width="stretch",
        config={"scrollZoom": True, "displayModeBar": "hover", "responsive": True},
    )


# ======================================================================
# 成績サマリー表
# ======================================================================
_METRIC_ORDER = [
    "初期資金", "最終資産", "総利益", "利益率", "年間リターン", "最大ドローダウン",
    "勝率", "総取引回数", "平均利益", "平均損失", "Profit Factor", "Sharpe Ratio", "平均保有日数",
]

_METRIC_FMT = {
    "初期資金": lambda v: f"¥{v:,.0f}",
    "最終資産": lambda v: f"¥{v:,.0f}",
    "総利益": lambda v: f"¥{v:,.0f}",
    "利益率": lambda v: f"{v * 100:.2f}%",
    "年間リターン": lambda v: f"{v * 100:.2f}%",
    "最大ドローダウン": lambda v: f"{v * 100:.2f}%",
    "勝率": lambda v: f"{v * 100:.1f}%",
    "総取引回数": lambda v: f"{v:.0f}",
    "平均利益": lambda v: f"¥{v:,.0f}",
    "平均損失": lambda v: f"¥{v:,.0f}",
    "Profit Factor": lambda v: (f"{v:.2f}" if v == v else "N/A"),
    "Sharpe Ratio": lambda v: f"{v:.2f}",
    "平均保有日数": lambda v: f"{v:.1f}日",
}


def render_metrics_table(metrics: dict, bh_metrics: dict = None) -> None:
    rows = []
    for key in _METRIC_ORDER:
        if key in metrics:
            fmt = _METRIC_FMT.get(key, str)
            row = {"指標": key, "戦略": fmt(metrics[key])}
            if bh_metrics and key in bh_metrics:
                row["Buy & Hold"] = fmt(bh_metrics[key])
            rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ======================================================================
# 使用したリスク設定値／Buy&Hold内訳／診断（すべてカードグリッド化）
# ======================================================================
def render_settings_used(settings) -> None:
    """【重要1対応】バックテストに使用したリスク設定値を必ず結果画面に表示する"""
    st.markdown("##### 使用したリスク設定値")
    display_dict = settings.as_display_dict()
    render_metric_grid(list(display_dict.items()))


def render_buy_hold_summary(bh_metrics: dict) -> None:
    """【重要4対応】Buy & Holdで実際に投資された金額・未使用現金・購入銘柄数を表示する"""
    if not bh_metrics:
        return
    st.markdown("##### Buy & Hold の内訳")
    items = [
        ("投資済み金額", f"¥{bh_metrics.get('投資済み金額', 0):,.0f}"),
        ("未使用現金", f"¥{bh_metrics.get('未使用現金', 0):,.0f}"),
        ("実購入銘柄数", f"{bh_metrics.get('実購入銘柄数', 0)} / {bh_metrics.get('対象銘柄数', 0)}銘柄"),
        ("未使用現金比率", f"{bh_metrics.get('未使用現金比率', 0) * 100:.1f}%"),
    ]
    render_metric_grid(items)
    if bh_metrics.get("unused_cash_warning"):
        st.warning(
            "⚠️ Buy & Holdは100株単位の制約で購入できなかった銘柄が多く、"
            "資産の大部分が未使用現金のまま残っています。"
            "Buy & Holdとの比較結果はこの「大量の未使用現金」による影響を強く受けている可能性があるため、"
            "参考程度に見てください。"
        )


def render_diagnostics(diagnostics: dict) -> None:
    """
    【診断】「戦略が悪いのか」「そもそも50万円では対象株を買えないのか」を切り分けるための指標を表示する。
    """
    if not diagnostics:
        st.info("診断情報がありません。")
        return
    st.markdown("##### 診断サマリー")
    items = [
        ("購入できた銘柄数", f"{diagnostics.get('購入できた銘柄数', 0)}銘柄"),
        ("資金不足でスキップした回数", f"{diagnostics.get('資金不足でスキップした回数', 0)}回"),
        ("シグナル発生回数", f"{diagnostics.get('シグナル発生回数', 0)}回"),
        ("実際のエントリー回数", f"{diagnostics.get('実際のエントリー回数', 0)}回"),
        ("平均資金使用率", f"{diagnostics.get('平均資金使用率', 0) * 100:.1f}%"),
        ("最大資金使用率", f"{diagnostics.get('最大資金使用率', 0) * 100:.1f}%"),
        ("現金比率(平均)", f"{diagnostics.get('現金比率(平均)', 0) * 100:.1f}%"),
        ("年間取引回数", f"{diagnostics.get('年間取引回数', 0):.1f}回/年"),
    ]
    render_metric_grid(items)

    signal_count = diagnostics.get("シグナル発生回数", 0)
    entry_count = diagnostics.get("実際のエントリー回数", 0)
    skip_count = diagnostics.get("資金不足でスキップした回数", 0)
    if signal_count > 0 and skip_count > 0 and skip_count >= entry_count:
        st.warning(
            "⚠️ シグナルは発生しているものの、資金不足によるスキップが実際のエントリー回数と同等以上あります。"
            "戦略自体よりも「初期資金50万円では対象銘柄の多くを購入できない」ことが"
            "成績を左右している可能性があります。1銘柄最大投資比率を上げる、"
            "あるいは株価水準の低い銘柄を対象に追加するなどの見直しを検討してください。"
        )


def render_skip_log(skip_log_df: pd.DataFrame) -> None:
    """【重要1対応】シグナルはあったが資金管理ルールで購入できなかった記録を一覧表示する"""
    if skip_log_df is None or skip_log_df.empty:
        st.info("資金不足等でスキップした取引はありません。")
        return
    df = skip_log_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"date": "日時", "code": "銘柄コード", "reason": "理由"})
    # 重要列(日時・銘柄コード・理由)を先頭にしたうえで横スクロールに委ねる
    df = df[["日時", "銘柄コード", "理由"]]
    st.dataframe(df.sort_values("日時", ascending=False), width="stretch", hide_index=True)


# ======================================================================
# テーブル（保有銘柄・売買履歴・銘柄ごとの成績）
# 重要列を先頭に配置し、st.dataframe 標準の横スクロールに委ねることで
# スマホでも表が崩れないようにしている。
# ======================================================================
def render_positions_table(positions: dict, price_lookup: dict) -> None:
    if not positions:
        st.info("現在保有中の銘柄はありません。")
        return
    rows = []
    for code, pos in positions.items():
        current_price = price_lookup.get(code, pos.entry_price)
        entry_date = pos.entry_date
        entry_date_str = entry_date.strftime("%Y-%m-%d") if hasattr(entry_date, "strftime") else str(entry_date)
        rows.append({
            "銘柄コード": code,
            "評価損益率": f"{pos.unrealized_pnl_ratio(current_price) * 100:.2f}%",
            "評価損益": f"¥{pos.unrealized_pnl(current_price):,.0f}",
            "銘柄名": pos.name,
            "株数": pos.shares,
            "取得単価": f"¥{pos.entry_price:,.1f}",
            "現在値": f"¥{current_price:,.1f}",
            "評価額": f"¥{pos.market_value(current_price):,.0f}",
            "取得日": entry_date_str,
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_trades_table(trades_df: pd.DataFrame) -> None:
    if trades_df is None or trades_df.empty:
        st.info("取引履歴がありません。")
        return
    df = trades_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={
        "datetime": "日時", "code": "銘柄コード", "name": "銘柄名", "side": "売買",
        "shares": "株数", "price": "価格", "amount": "取引金額", "commission": "手数料",
        "pnl": "損益", "reason": "理由",
    })
    # 重要列(日時・銘柄コード・売買・損益)を先頭に並べ替え
    ordered_cols = ["日時", "銘柄コード", "売買", "損益", "銘柄名", "株数", "価格", "取引金額", "手数料", "理由"]
    df = df[[c for c in ordered_cols if c in df.columns]]
    st.dataframe(df.sort_values("日時", ascending=False), width="stretch", hide_index=True)


def render_per_stock_performance(trades_df: pd.DataFrame, universe: dict) -> None:
    if trades_df is None or trades_df.empty:
        st.info("取引がまだありません。")
        return
    closed = trades_df[trades_df["pnl"].notna()].copy()
    if closed.empty:
        st.info("決済済みの取引がまだありません。")
        return
    grouped = closed.groupby("code").agg(
        銘柄名=("name", "first"),
        取引回数=("pnl", "count"),
        勝率=("pnl", lambda s: (s > 0).mean()),
        合計損益=("pnl", "sum"),
        平均損益=("pnl", "mean"),
    ).reset_index().rename(columns={"code": "銘柄コード"})
    grouped["勝率"] = (grouped["勝率"] * 100).round(1).astype(str) + "%"
    grouped["合計損益"] = grouped["合計損益"].round(0)
    grouped["平均損益"] = grouped["平均損益"].round(0)
    # 重要列(銘柄コード・銘柄名・合計損益)を先頭に
    grouped = grouped[["銘柄コード", "銘柄名", "合計損益", "取引回数", "勝率", "平均損益"]]
    st.dataframe(grouped, width="stretch", hide_index=True)


# ======================================================================
# 現在の買いシグナル（カードUI・スマホで最優先に見るべき情報を上部に配置）
# ======================================================================
def render_buy_signal_table(signal_rows: list) -> None:
    """
    signal_rows: [{
        "code", "name", "judgement", "sma", "rsi", "macd", "volume",
        "affordable"(bool), "purchasable_shares"(int), "min_purchase_amount"(float),
    }, ...]

    【スマホ対応】銘柄・総合判定・購入可能株数・必要最低購入金額・資金不足かどうか、
    という優先度の高い情報をカード上部にまとめ、SMA/RSI/MACD/出来高の内訳は
    st.expander に格納して画面を圧迫しないようにしている。
    """
    if not signal_rows:
        st.info("シグナルデータがありません。")
        return
    badge_map = {"買い候補": "🟢", "様子見": "🟡", "売り": "🔴"}
    for row in signal_rows:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            c1.markdown(f"**{row['name']}（{row['code']}）**")
            badge = badge_map.get(row["judgement"], "⚪")
            c2.markdown(f"{badge} **{row['judgement']}**")

            # --- 優先表示: 購入可能株数・必要最低購入金額・資金不足かどうか ---
            fund_items = [
                ("購入可能株数", f"{row.get('purchasable_shares', 0):,}株" if row.get("affordable") else "0株"),
                ("必要最低購入金額(100株)", f"¥{row.get('min_purchase_amount', 0):,.0f}"),
                ("資金状況", "🟢 購入可能" if row.get("affordable", False) else "🔴 資金不足"),
            ]
            render_metric_grid(fund_items)

            with st.expander("条件詳細（SMA・RSI・MACD・出来高）"):
                cond_cols = st.columns(2)
                cond_cols[0].markdown(f"SMAトレンド {'○' if row['sma'] else '×'}")
                cond_cols[1].markdown(f"RSI {'○' if row['rsi'] else '×'}")
                cond_cols2 = st.columns(2)
                cond_cols2[0].markdown(f"MACD {'○' if row['macd'] else '×'}")
                cond_cols2[1].markdown(f"出来高 {'○' if row['volume'] else '×'}")


# ======================================================================
# 広域スクリーニング結果（大型株ユニバース向け・テーブル表示）
# 銘柄数が多いためカード形式ではなく表形式にし、重要列（総合判定）を先頭に置く。
# ======================================================================
def render_screening_results(rows: list, judgement_filter: str = "すべて") -> None:
    """
    rows: screening.run_screening() が返すリスト。
    judgement_filter: "すべて" / "買い候補+様子見" / "買い候補のみ"
    """
    if not rows:
        st.info("スクリーニング結果がありません。「スクリーニング実行」を押してください。")
        return

    filtered = rows
    if judgement_filter == "買い候補のみ":
        filtered = [r for r in rows if r["judgement"] == "買い候補"]
    elif judgement_filter == "買い候補+様子見":
        filtered = [r for r in rows if r["judgement"] in ("買い候補", "様子見")]

    if not filtered:
        st.info("この条件に該当する銘柄はありませんでした。")
        return

    badge_map = {"買い候補": "🟢 買い候補", "様子見": "🟡 様子見", "売り": "🔴 売り"}
    df = pd.DataFrame([
        {
            "総合判定": badge_map.get(r["judgement"], r["judgement"]),
            "銘柄コード": r["code"],
            "銘柄名": r["name"],
            "現在値": f"¥{r['price']:,.0f}",
            "SMA": "○" if r["sma"] else "×",
            "RSI": "○" if r["rsi"] else "×",
            "MACD": "○" if r["macd"] else "×",
            "出来高": "○" if r["volume"] else "×",
        }
        for r in filtered
    ])
    st.caption(f"該当 {len(filtered)}銘柄 / 全 {len(rows)}銘柄中")
    st.dataframe(df, width="stretch", hide_index=True)

            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 10px;
        }
        /* 「バックテスト実行」等のプライマリボタンをさらに目立たせる */
        div.stButton > button[kind="primary"] {
            font-size: 1.2rem;
            min-height: 3.5em;
            box-shadow: 0 2px 10px rgba(37, 99, 235, 0.35);
        }
        .stTextInput input, .stNumberInput input {
            font-size: 1rem;
            min-height: 2.6em;
        }
        /* 削除ボタン等の小さいボタンでも最低限のタップ領域を確保 */
        div.stButton > button {
            padding-top: 0.5em;
            padding-bottom: 0.5em;
        }

        /* ---- カードグリッド: 画面幅に応じて列数が自動的に変わる ---- */
        /* auto-fit + minmax により、PCでは横に並び、スマホでは自動的に1〜2列に折り返す。
           JavaScriptによる端末判定を使わずCSSのみで実現している。 */
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.6rem;
            margin: 0.4rem 0 1.1rem 0;
        }
        .metric-card {
            background: rgba(120, 120, 120, 0.08);
            border-radius: 10px;
            padding: 0.7rem 0.9rem;
            border: 1px solid rgba(120, 120, 120, 0.18);
        }
        .metric-card .metric-label {
            font-size: 0.78rem;
            opacity: 0.75;
            margin-bottom: 0.2rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .metric-card .metric-value {
            font-size: 1.15rem;
            font-weight: 700;
            line-height: 1.25;
            word-break: break-word;
        }

        /* ---- テーブルの横スクロールを保証（列がはみ出しても崩れない） ---- */
        div[data-testid="stDataFrame"] {
            overflow-x: auto;
        }

        /* ---- 見出しの余白をスマホでは少し詰める ---- */
        h1, h2, h3 {
            margin-top: 0.4em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_grid(items: list) -> None:
    """
    items: [(label, value_str), ...]
    CSSグリッドでカードを並べる。画面幅に応じて自動的に折り返される。
    """
    if not items:
        return
    cards_html = "".join(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'</div>'
        for label, value in items
    )
    st.markdown(f'<div class="metric-grid">{cards_html}</div>', unsafe_allow_html=True)


# ======================================================================
# ヘッダー・安全表示
# ======================================================================
def render_header() -> None:
    st.title("日本株 自動売買シミュレーター")
    st.caption("📝 ペーパートレード専用（仮想売買）。実際の発注は一切行いません。")


# ======================================================================
# ダッシュボードカード（総資産・現金・株式評価額・利益率・最大DD・勝率）
# ======================================================================
def render_dashboard_cards(metrics: dict) -> None:
    items = [
        ("総資産", f"¥{metrics.get('最終資産', 0):,.0f}"),
        ("現金", f"¥{metrics.get('現金', 0):,.0f}"),
        ("株式評価額", f"¥{metrics.get('株式評価額', 0):,.0f}"),
        ("利益率", f"{metrics.get('利益率', 0) * 100:.2f}%"),
        ("最大ドローダウン", f"{metrics.get('最大ドローダウン', 0) * 100:.2f}%"),
        ("勝率", f"{metrics.get('勝率', 0) * 100:.1f}%"),
    ]
    render_metric_grid(items)


def render_quick_summary(metrics: dict) -> None:
    """
    【スマホホーム画面対応】アプリを開いてすぐ分かる最重要2指標（総資産・利益率）だけを表示する。
    かんたん表示モードや、結果画面の一番上に使う想定。
    """
    items = [
        ("総資産", f"¥{metrics.get('最終資産', 0):,.0f}"),
        ("利益率", f"{metrics.get('利益率', 0) * 100:.2f}%"),
        ("最大ドローダウン", f"{metrics.get('最大ドローダウン', 0) * 100:.2f}%"),
    ]
    render_metric_grid(items)


# ======================================================================
# 資産推移グラフ
# ======================================================================
def render_equity_chart(equity_df: pd.DataFrame, bh_df: pd.DataFrame = None, compact: bool = False) -> None:
    """
    compact=True のとき（かんたん表示・スマホ想定）は高さと凡例フォントを抑える。
    width="stretch" は常に維持し、ピンチズーム・横スクロールを妨げない設定
    (config引数)で描画する。
    """
    fig = go.Figure()
    if equity_df is not None and not equity_df.empty:
        fig.add_trace(go.Scatter(
            x=equity_df.index, y=equity_df["equity"],
            mode="lines", name="戦略（トレンドフォロー）",
            line=dict(color="#2563eb", width=2),
        ))
    if bh_df is not None and not bh_df.empty:
        fig.add_trace(go.Scatter(
            x=bh_df.index, y=bh_df["equity"],
            mode="lines", name="Buy & Hold",
            line=dict(color="#9ca3af", width=2, dash="dot"),
        ))
    if equity_df is not None and not equity_df.empty:
        x_range = [equity_df.index.min(), equity_df.index.max()]
        fig.add_trace(go.Scatter(
            x=x_range, y=[INITIAL_CAPITAL, INITIAL_CAPITAL],
            mode="lines", name=f"初期資金 ({INITIAL_CAPITAL:,.0f}円)",
            line=dict(color="#94a3b8", width=1, dash="dash"),
        ))
        fig.add_trace(go.Scatter(
            x=x_range, y=[TARGET_CAPITAL, TARGET_CAPITAL],
            mode="lines", name=f"目標資産 ({TARGET_CAPITAL:,.0f}円)",
            line=dict(color="#ef4444", width=1, dash="dash"),
        ))

    height = 300 if compact else 450
    legend_font_size = 10 if compact else 12

    fig.update_layout(
        title="資産推移",
        xaxis_title="日付", yaxis_title="資産（円）",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=legend_font_size),
        ),
        height=height,
        margin=dict(l=10, r=10, t=70, b=10),
    )
    # scrollZoom: True でピンチズーム・スクロールを妨げない。displayModeBarはhoverでのみ表示し
    # スマホの限られた画面を圧迫しないようにする。
    st.plotly_chart(
        fig, width="stretch",
        config={"scrollZoom": True, "displayModeBar": "hover", "responsive": True},
    )


# ======================================================================
# 成績サマリー表
# ======================================================================
_METRIC_ORDER = [
    "初期資金", "最終資産", "総利益", "利益率", "年間リターン", "最大ドローダウン",
    "勝率", "総取引回数", "平均利益", "平均損失", "Profit Factor", "Sharpe Ratio", "平均保有日数",
]

_METRIC_FMT = {
    "初期資金": lambda v: f"¥{v:,.0f}",
    "最終資産": lambda v: f"¥{v:,.0f}",
    "総利益": lambda v: f"¥{v:,.0f}",
    "利益率": lambda v: f"{v * 100:.2f}%",
    "年間リターン": lambda v: f"{v * 100:.2f}%",
    "最大ドローダウン": lambda v: f"{v * 100:.2f}%",
    "勝率": lambda v: f"{v * 100:.1f}%",
    "総取引回数": lambda v: f"{v:.0f}",
    "平均利益": lambda v: f"¥{v:,.0f}",
    "平均損失": lambda v: f"¥{v:,.0f}",
    "Profit Factor": lambda v: (f"{v:.2f}" if v == v else "N/A"),
    "Sharpe Ratio": lambda v: f"{v:.2f}",
    "平均保有日数": lambda v: f"{v:.1f}日",
}


def render_metrics_table(metrics: dict, bh_metrics: dict = None) -> None:
    rows = []
    for key in _METRIC_ORDER:
        if key in metrics:
            fmt = _METRIC_FMT.get(key, str)
            row = {"指標": key, "戦略": fmt(metrics[key])}
            if bh_metrics and key in bh_metrics:
                row["Buy & Hold"] = fmt(bh_metrics[key])
            rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ======================================================================
# 使用したリスク設定値／Buy&Hold内訳／診断（すべてカードグリッド化）
# ======================================================================
def render_settings_used(settings) -> None:
    """【重要1対応】バックテストに使用したリスク設定値を必ず結果画面に表示する"""
    st.markdown("##### 使用したリスク設定値")
    display_dict = settings.as_display_dict()
    render_metric_grid(list(display_dict.items()))


def render_buy_hold_summary(bh_metrics: dict) -> None:
    """【重要4対応】Buy & Holdで実際に投資された金額・未使用現金・購入銘柄数を表示する"""
    if not bh_metrics:
        return
    st.markdown("##### Buy & Hold の内訳")
    items = [
        ("投資済み金額", f"¥{bh_metrics.get('投資済み金額', 0):,.0f}"),
        ("未使用現金", f"¥{bh_metrics.get('未使用現金', 0):,.0f}"),
        ("実購入銘柄数", f"{bh_metrics.get('実購入銘柄数', 0)} / {bh_metrics.get('対象銘柄数', 0)}銘柄"),
        ("未使用現金比率", f"{bh_metrics.get('未使用現金比率', 0) * 100:.1f}%"),
    ]
    render_metric_grid(items)
    if bh_metrics.get("unused_cash_warning"):
        st.warning(
            "⚠️ Buy & Holdは100株単位の制約で購入できなかった銘柄が多く、"
            "資産の大部分が未使用現金のまま残っています。"
            "Buy & Holdとの比較結果はこの「大量の未使用現金」による影響を強く受けている可能性があるため、"
            "参考程度に見てください。"
        )


def render_diagnostics(diagnostics: dict) -> None:
    """
    【診断】「戦略が悪いのか」「そもそも50万円では対象株を買えないのか」を切り分けるための指標を表示する。
    """
    if not diagnostics:
        st.info("診断情報がありません。")
        return
    st.markdown("##### 診断サマリー")
    items = [
        ("購入できた銘柄数", f"{diagnostics.get('購入できた銘柄数', 0)}銘柄"),
        ("資金不足でスキップした回数", f"{diagnostics.get('資金不足でスキップした回数', 0)}回"),
        ("シグナル発生回数", f"{diagnostics.get('シグナル発生回数', 0)}回"),
        ("実際のエントリー回数", f"{diagnostics.get('実際のエントリー回数', 0)}回"),
        ("平均資金使用率", f"{diagnostics.get('平均資金使用率', 0) * 100:.1f}%"),
        ("最大資金使用率", f"{diagnostics.get('最大資金使用率', 0) * 100:.1f}%"),
        ("現金比率(平均)", f"{diagnostics.get('現金比率(平均)', 0) * 100:.1f}%"),
        ("年間取引回数", f"{diagnostics.get('年間取引回数', 0):.1f}回/年"),
    ]
    render_metric_grid(items)

    signal_count = diagnostics.get("シグナル発生回数", 0)
    entry_count = diagnostics.get("実際のエントリー回数", 0)
    skip_count = diagnostics.get("資金不足でスキップした回数", 0)
    if signal_count > 0 and skip_count > 0 and skip_count >= entry_count:
        st.warning(
            "⚠️ シグナルは発生しているものの、資金不足によるスキップが実際のエントリー回数と同等以上あります。"
            "戦略自体よりも「初期資金50万円では対象銘柄の多くを購入できない」ことが"
            "成績を左右している可能性があります。1銘柄最大投資比率を上げる、"
            "あるいは株価水準の低い銘柄を対象に追加するなどの見直しを検討してください。"
        )


def render_skip_log(skip_log_df: pd.DataFrame) -> None:
    """【重要1対応】シグナルはあったが資金管理ルールで購入できなかった記録を一覧表示する"""
    if skip_log_df is None or skip_log_df.empty:
        st.info("資金不足等でスキップした取引はありません。")
        return
    df = skip_log_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"date": "日時", "code": "銘柄コード", "reason": "理由"})
    # 重要列(日時・銘柄コード・理由)を先頭にしたうえで横スクロールに委ねる
    df = df[["日時", "銘柄コード", "理由"]]
    st.dataframe(df.sort_values("日時", ascending=False), width="stretch", hide_index=True)


# ======================================================================
# テーブル（保有銘柄・売買履歴・銘柄ごとの成績）
# 重要列を先頭に配置し、st.dataframe 標準の横スクロールに委ねることで
# スマホでも表が崩れないようにしている。
# ======================================================================
def render_positions_table(positions: dict, price_lookup: dict) -> None:
    if not positions:
        st.info("現在保有中の銘柄はありません。")
        return
    rows = []
    for code, pos in positions.items():
        current_price = price_lookup.get(code, pos.entry_price)
        entry_date = pos.entry_date
        entry_date_str = entry_date.strftime("%Y-%m-%d") if hasattr(entry_date, "strftime") else str(entry_date)
        rows.append({
            "銘柄コード": code,
            "評価損益率": f"{pos.unrealized_pnl_ratio(current_price) * 100:.2f}%",
            "評価損益": f"¥{pos.unrealized_pnl(current_price):,.0f}",
            "銘柄名": pos.name,
            "株数": pos.shares,
            "取得単価": f"¥{pos.entry_price:,.1f}",
            "現在値": f"¥{current_price:,.1f}",
            "評価額": f"¥{pos.market_value(current_price):,.0f}",
            "取得日": entry_date_str,
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_trades_table(trades_df: pd.DataFrame) -> None:
    if trades_df is None or trades_df.empty:
        st.info("取引履歴がありません。")
        return
    df = trades_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={
        "datetime": "日時", "code": "銘柄コード", "name": "銘柄名", "side": "売買",
        "shares": "株数", "price": "価格", "amount": "取引金額", "commission": "手数料",
        "pnl": "損益", "reason": "理由",
    })
    # 重要列(日時・銘柄コード・売買・損益)を先頭に並べ替え
    ordered_cols = ["日時", "銘柄コード", "売買", "損益", "銘柄名", "株数", "価格", "取引金額", "手数料", "理由"]
    df = df[[c for c in ordered_cols if c in df.columns]]
    st.dataframe(df.sort_values("日時", ascending=False), width="stretch", hide_index=True)


def render_per_stock_performance(trades_df: pd.DataFrame, universe: dict) -> None:
    if trades_df is None or trades_df.empty:
        st.info("取引がまだありません。")
        return
    closed = trades_df[trades_df["pnl"].notna()].copy()
    if closed.empty:
        st.info("決済済みの取引がまだありません。")
        return
    grouped = closed.groupby("code").agg(
        銘柄名=("name", "first"),
        取引回数=("pnl", "count"),
        勝率=("pnl", lambda s: (s > 0).mean()),
        合計損益=("pnl", "sum"),
        平均損益=("pnl", "mean"),
    ).reset_index().rename(columns={"code": "銘柄コード"})
    grouped["勝率"] = (grouped["勝率"] * 100).round(1).astype(str) + "%"
    grouped["合計損益"] = grouped["合計損益"].round(0)
    grouped["平均損益"] = grouped["平均損益"].round(0)
    # 重要列(銘柄コード・銘柄名・合計損益)を先頭に
    grouped = grouped[["銘柄コード", "銘柄名", "合計損益", "取引回数", "勝率", "平均損益"]]
    st.dataframe(grouped, width="stretch", hide_index=True)


# ======================================================================
# 現在の買いシグナル（カードUI・スマホで最優先に見るべき情報を上部に配置）
# ======================================================================
def render_buy_signal_table(signal_rows: list) -> None:
    """
    signal_rows: [{
        "code", "name", "judgement", "sma", "rsi", "macd", "volume",
        "affordable"(bool), "purchasable_shares"(int), "min_purchase_amount"(float),
    }, ...]

    【スマホ対応】銘柄・総合判定・購入可能株数・必要最低購入金額・資金不足かどうか、
    という優先度の高い情報をカード上部にまとめ、SMA/RSI/MACD/出来高の内訳は
    st.expander に格納して画面を圧迫しないようにしている。
    """
    if not signal_rows:
        st.info("シグナルデータがありません。")
        return
    badge_map = {"買い候補": "🟢", "様子見": "🟡", "売り": "🔴"}
    for row in signal_rows:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            c1.markdown(f"**{row['name']}（{row['code']}）**")
            badge = badge_map.get(row["judgement"], "⚪")
            c2.markdown(f"{badge} **{row['judgement']}**")

            # --- 優先表示: 購入可能株数・必要最低購入金額・資金不足かどうか ---
            fund_items = [
                ("購入可能株数", f"{row.get('purchasable_shares', 0):,}株" if row.get("affordable") else "0株"),
                ("必要最低購入金額(100株)", f"¥{row.get('min_purchase_amount', 0):,.0f}"),
                ("資金状況", "🟢 購入可能" if row.get("affordable", False) else "🔴 資金不足"),
            ]
            render_metric_grid(fund_items)

            with st.expander("条件詳細（SMA・RSI・MACD・出来高）"):
                cond_cols = st.columns(2)
                cond_cols[0].markdown(f"SMAトレンド {'○' if row['sma'] else '×'}")
                cond_cols[1].markdown(f"RSI {'○' if row['rsi'] else '×'}")
                cond_cols2 = st.columns(2)
                cond_cols2[0].markdown(f"MACD {'○' if row['macd'] else '×'}")
                cond_cols2[1].markdown(f"出来高 {'○' if row['volume'] else '×'}")
