"""
広域スクリーニングモジュール。

バックテスト用の対象銘柄（config.DEFAULT_UNIVERSE）とは別に、より広い銘柄群
（config.SCREENING_UNIVERSE）に対して、strategy.py の買い条件を機械的に適用し、
「買い候補」「様子見」「売り」の一覧を作る。

【設計方針】
このモジュールは、データ取得・指標計算・シグナル判定のいずれについても
既存モジュール（data_provider.py / indicators.py / strategy.py）をそのまま
呼び出すだけで、それらのロジック自体には一切手を加えていない。
バックテストの資金管理・売買執行（backtester.py / risk_manager.py /
portfolio.py）にも関与しない、純粋な「現在時点のシグナル一覧表示」機能。
"""
from __future__ import annotations
from typing import Dict, List, Tuple

from data_provider import YFinanceDataProvider, DataProviderError
from indicators import add_all_indicators
from strategy import evaluate_row, judgement_label

# シグナル判定に必要な指標（SMA60・出来高20日平均等）が計算できる最低限の期間。
# 過去1年分あれば全指標のウォームアップ期間として十分。
SCREENING_HISTORY_YEARS = 1

_JUDGEMENT_ORDER = {"買い候補": 0, "様子見": 1, "売り": 2}


def run_screening(universe: Dict[str, str], years: int = SCREENING_HISTORY_YEARS) -> Tuple[List[Dict], List[str]]:
    """
    universe: {証券コード: 銘柄名}
    各銘柄について直近の売買シグナルを判定した結果のリストと、
    データ取得に失敗した銘柄のエラーメッセージ一覧を返す。

    戻り値の各要素:
        {"code", "name", "price", "judgement", "score", "sma", "rsi", "macd", "volume"}
    "買い候補" → "様子見" → "売り" の順、同じ判定の中では条件を多く満たす順に並べる。
    """
    provider = YFinanceDataProvider()
    rows: List[Dict] = []
    errors: List[str] = []

    for code, name in universe.items():
        try:
            df = provider.get_history(code, years)
        except DataProviderError as e:
            errors.append(str(e))
            continue

        if df is None or df.empty:
            continue

        df_ind = add_all_indicators(df)
        last_row = df_ind.iloc[-1]
        check = evaluate_row(last_row)
        price = float(last_row["Close"])

        rows.append({
            "code": code,
            "name": name,
            "price": price,
            "judgement": judgement_label(check),
            "score": check.score,
            "sma": check.sma_trend,
            "rsi": check.rsi_ok,
            "macd": check.macd_ok,
            "volume": check.volume_ok,
        })

    rows.sort(key=lambda r: (_JUDGEMENT_ORDER.get(r["judgement"], 3), -r["score"]))
    return rows, errors
