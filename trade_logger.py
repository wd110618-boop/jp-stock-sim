"""取引履歴のCSV保存モジュール

記録内容: 日時, 銘柄コード, 銘柄名, 売買, 株数, 価格, 取引金額, 手数料, 損益, 売買理由
"""
import pandas as pd

COLUMNS = ["datetime", "code", "name", "side", "shares", "price", "amount", "commission", "pnl", "reason"]
COLUMN_LABELS_JA = {
    "datetime": "日時", "code": "銘柄コード", "name": "銘柄名", "side": "売買",
    "shares": "株数", "price": "価格", "amount": "取引金額", "commission": "手数料",
    "pnl": "損益", "reason": "売買理由",
}


def _prepare(trades_df: pd.DataFrame) -> pd.DataFrame:
    df = trades_df.copy() if trades_df is not None else pd.DataFrame()
    if df.empty:
        df = pd.DataFrame(columns=COLUMNS)
    df = df.reindex(columns=COLUMNS)
    return df.rename(columns=COLUMN_LABELS_JA)


def save_trades_csv(trades_df: pd.DataFrame, path: str = "trade_history.csv") -> str:
    """取引履歴をCSVファイルとして保存し、保存先パスを返す"""
    df = _prepare(trades_df)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def trades_to_csv_bytes(trades_df: pd.DataFrame) -> bytes:
    """Streamlitのdownload_button用にCSVをbytesで返す"""
    df = _prepare(trades_df)
    return df.to_csv(index=False).encode("utf-8-sig")
