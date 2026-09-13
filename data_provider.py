"""
株価データ取得モジュール。

無料データソース(yfinance / Yahoo Finance)から日本株の日足OHLCVを取得する。
将来、証券会社APIに差し替えやすいよう、BaseDataProvider という抽象インターフェースを
定義し、具体的な取得処理は YFinanceDataProvider に閉じ込めている。

証券会社APIに移行する際は、BaseDataProvider を継承した
BrokerApiDataProvider のようなクラスを新規作成し、main.py 側で
差し替えるだけで良い構造になっている。
"""
from __future__ import annotations
import abc
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from config import to_ticker


class DataProviderError(Exception):
    """データ取得に失敗した場合の例外"""
    pass


class BaseDataProvider(abc.ABC):
    """株価データプロバイダの抽象基底クラス"""

    @abc.abstractmethod
    def get_history(self, code: str, period_years: int) -> pd.DataFrame:
        """
        指定銘柄の日足OHLCVデータを取得する。

        Returns:
            columns=["Open", "High", "Low", "Close", "Volume"] のDataFrame。
            index は日付(タイムゾーンなしのdatetime)。
        """
        raise NotImplementedError

    def get_history_multi(self, codes: List[str], period_years: int) -> Dict[str, pd.DataFrame]:
        """複数銘柄をまとめて取得する。取得失敗銘柄はスキップする。"""
        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            try:
                df = self.get_history(code, period_years)
                if df is not None and not df.empty:
                    result[code] = df
            except DataProviderError:
                continue
        return result


class YFinanceDataProvider(BaseDataProvider):
    """yfinance (Yahoo! Finance) を利用した無料データ取得の実装"""

    def get_history(self, code: str, period_years: int) -> pd.DataFrame:
        ticker_symbol = to_ticker(code)
        try:
            period_str = f"{max(period_years, 1)}y"
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period=period_str, interval="1d", auto_adjust=False)
        except Exception as e:  # noqa: BLE001
            raise DataProviderError(f"{code} のデータ取得に失敗しました: {e}") from e

        if df is None or df.empty:
            raise DataProviderError(f"{code} のデータが取得できませんでした（データなし）")

        missing_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c not in df.columns]
        if missing_cols:
            raise DataProviderError(f"{code} のデータに必要な列がありません: {missing_cols}")

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        try:
            df.index = df.index.tz_localize(None)
        except TypeError:
            pass  # 既にtz-naiveの場合
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        df.sort_index(inplace=True)
        return df

    def get_latest_price(self, code: str) -> Optional[float]:
        try:
            df = self.get_history(code, 1)
        except DataProviderError:
            return None
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
