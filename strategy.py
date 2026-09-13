"""
売買戦略モジュール（シンプルなトレンドフォロー戦略）

【買い条件】すべて満たした場合に買い候補
 1. SMA5 > SMA20
 2. SMA20 > SMA60
 3. 終値 > SMA20
 4. 50 <= RSI14 < 70
 5. MACD > MACDシグナル
 6. 出来高 >= 20日平均出来高

【売り条件】いずれかを満たした場合に売却
 - SMA5 が SMA20 を下回る         → sell_technical_signal()
 - MACD がシグナルを下回る        → sell_technical_signal()
 - 損切りライン到達               → risk_manager.check_exit_conditions()
 - 利確ライン到達                 → risk_manager.check_exit_conditions()
 - トレーリングストップ到達       → risk_manager.check_exit_conditions()
"""
from __future__ import annotations
from dataclasses import dataclass

import pandas as pd

from config import RSI_BUY_MIN, RSI_BUY_MAX


def _safe(v) -> bool:
    return v is not None and not pd.isna(v)


@dataclass
class SignalCheck:
    sma_trend: bool          # SMA5>SMA20>SMA60
    close_above_sma20: bool  # 終値がSMA20より上
    rsi_ok: bool              # 50<=RSI<70
    macd_ok: bool             # MACD>シグナル
    volume_ok: bool           # 出来高>=20日平均

    @property
    def is_buy(self) -> bool:
        return all([
            self.sma_trend, self.close_above_sma20, self.rsi_ok,
            self.macd_ok, self.volume_ok,
        ])

    @property
    def score(self) -> int:
        return sum([
            self.sma_trend, self.close_above_sma20, self.rsi_ok,
            self.macd_ok, self.volume_ok,
        ])


def evaluate_row(row: pd.Series) -> SignalCheck:
    """1銘柄・1日分の指標データ(Series)から買いシグナル判定を行う"""
    sma5, sma20, sma60 = row.get("SMA5"), row.get("SMA20"), row.get("SMA60")
    close = row.get("Close")
    rsi14 = row.get("RSI14")
    macd_v, macd_sig = row.get("MACD"), row.get("MACD_SIGNAL")
    vol, vol_avg = row.get("Volume"), row.get("VOL_AVG20")

    sma_trend = bool(_safe(sma5) and _safe(sma20) and _safe(sma60) and sma5 > sma20 > sma60)
    close_above_sma20 = bool(_safe(close) and _safe(sma20) and close > sma20)
    rsi_ok = bool(_safe(rsi14) and RSI_BUY_MIN <= rsi14 < RSI_BUY_MAX)
    macd_ok = bool(_safe(macd_v) and _safe(macd_sig) and macd_v > macd_sig)
    volume_ok = bool(_safe(vol) and _safe(vol_avg) and vol >= vol_avg)

    return SignalCheck(
        sma_trend=sma_trend,
        close_above_sma20=close_above_sma20,
        rsi_ok=rsi_ok,
        macd_ok=macd_ok,
        volume_ok=volume_ok,
    )


def sell_technical_signal(row: pd.Series) -> bool:
    """テクニカル的な売りシグナル（SMAデッドクロス or MACDデッドクロス）"""
    sma5, sma20 = row.get("SMA5"), row.get("SMA20")
    macd_v, macd_sig = row.get("MACD"), row.get("MACD_SIGNAL")

    sma_break = bool(_safe(sma5) and _safe(sma20) and sma5 < sma20)
    macd_break = bool(_safe(macd_v) and _safe(macd_sig) and macd_v < macd_sig)
    return sma_break or macd_break


def judgement_label(check: SignalCheck) -> str:
    """総合判定ラベル: 買い候補 / 様子見 / 売り"""
    if check.is_buy:
        return "買い候補"
    if check.score >= 3:
        return "様子見"
    return "売り"
