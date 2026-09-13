"""テクニカル指標計算モジュール（SMA / RSI / MACD / ATR / 出来高平均）"""
import numpy as np
import pandas as pd

from config import (
    SMA_SHORT, SMA_MID, SMA_LONG, RSI_PERIOD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL, ATR_PERIOD, VOLUME_AVG_PERIOD,
)


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.fillna(50)  # データ不足・分母0のときは中立値50とする
    return rsi_val


def macd(series: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW, signal: int = MACD_SIGNAL):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def volume_avg(volume: pd.Series, window: int = VOLUME_AVG_PERIOD) -> pd.Series:
    return volume.rolling(window=window, min_periods=window).mean()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCVデータフレームに全テクニカル指標を追加して返す（元データは変更しない）"""
    out = df.copy()
    out["SMA5"] = sma(out["Close"], SMA_SHORT)
    out["SMA20"] = sma(out["Close"], SMA_MID)
    out["SMA60"] = sma(out["Close"], SMA_LONG)
    out["RSI14"] = rsi(out["Close"], RSI_PERIOD)
    macd_line, signal_line, hist = macd(out["Close"])
    out["MACD"] = macd_line
    out["MACD_SIGNAL"] = signal_line
    out["MACD_HIST"] = hist
    out["ATR14"] = atr(out, ATR_PERIOD)
    out["VOL_AVG20"] = volume_avg(out["Volume"], VOLUME_AVG_PERIOD)
    return out
