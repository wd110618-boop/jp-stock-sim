"""
バックテストエンジン。

Look-ahead bias（未来のデータを使った判断）を避けるため、以下のルールで動作する。

  1. 買い/テクニカル売り のシグナルは「当日の終値」で確定させる。
  2. 確定したシグナルは「翌営業日の始値」で約定させる（当日中には約定させない）。
  3. 損切りは、保有銘柄の「当日の安値」がストップ価格を下回ったかどうかで判定する
     （逆指値注文がザラ場中に約定する、という一般的なバックテストの近似）。
  4. 利益確定は「当日の終値」が目標値以上になったかどうかで判定する。
  5. トレーリングストップは【重要3】で説明する特別なルールに従う。

手数料・スリッページ・単元株(100株)・購入可能資金・同時保有数の制約も反映する。

【重要3対応: トレーリングストップの日足OHLC問題】
日足データでは「当日のHighとLowのどちらが先に発生したか」が分からない。
そのため、
    「当日のHighでhigh_since_entryを更新 → 更新後のトレーリングストップ価格を
     同じ日のLowで約定させる」
という判定は、実際にはHigh到達前にLowでストップに引っかかっていた可能性を
無視した「未来参照に近い」不正確な判定になってしまう。

これを避けるため、本エンジンでは日々の処理順序を以下のように固定する。
    (a) 前営業日までに確定していた high_since_entry を使って、
        「当日のトレーリングストップ価格」を決定する。
    (b) その価格を「当日のLow」と比較してストップ判定を行う。
    (c) 判定が終わった後で、初めて「当日のHigh」を使って high_since_entry を更新する。
    (d) (c)で新しく引き上げられたトレーリングストップは、判定(b)には使われず、
        「翌営業日」から有効になる。
詳細は _apply_position_risk_management() 内のコメントを参照。

【重要1対応】
リスクパラメータ（1取引最大リスク・1銘柄最大投資比率・最大同時保有数・損切り幅など）は
risk_manager.RiskSettings として外部から注入できる。Streamlit画面のスライダーで
変更された値を Backtester(..., settings=...) に渡すことで反映される。
資金不足で購入できなかった銘柄は理由付きで skip_log に記録し、診断情報として画面表示する。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    INITIAL_CAPITAL, SHARE_UNIT, COMMISSION_RATE, MIN_COMMISSION, SLIPPAGE_RATE,
)
from indicators import add_all_indicators
from strategy import evaluate_row, sell_technical_signal
from risk_manager import (
    RiskSettings, max_shares_by_risk, max_shares_by_position_limit, calc_stop_loss_price,
    calc_take_profit_price, is_trailing_stop_active, calc_trailing_stop_price,
    can_open_new_position, daily_loss_limit_hit, drawdown_halt_hit,
    can_afford_min_lot, min_purchase_amount,
)
from portfolio import Portfolio


def calc_commission(amount: float) -> float:
    """手数料 = max(約定代金 × 手数料率, 最低手数料)"""
    if amount <= 0:
        return 0.0
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def apply_slippage(price: float, side: str) -> float:
    """買いは不利な方向(高く)、売りは不利な方向(安く)にスリッページを適用"""
    if side == "buy":
        return price * (1 + SLIPPAGE_RATE)
    return price * (1 - SLIPPAGE_RATE)


@dataclass
class BacktestResult:
    portfolio: Portfolio
    equity_df: pd.DataFrame
    trades_df: pd.DataFrame
    metrics: Dict
    settings: RiskSettings
    diagnostics: Dict = field(default_factory=dict)
    skip_log_df: Optional[pd.DataFrame] = None
    buy_hold_equity_df: Optional[pd.DataFrame] = None
    buy_hold_metrics: Optional[Dict] = None


class Backtester:
    def __init__(self, price_data: Dict[str, pd.DataFrame], names: Dict[str, str],
                 initial_capital: float = INITIAL_CAPITAL,
                 settings: Optional[RiskSettings] = None):
        """
        price_data: {証券コード: 生のOHLCV DataFrame}
        names: {証券コード: 銘柄名}
        settings: 画面で変更可能なリスクパラメータ。未指定時は config.py のデフォルト値を使用。
        """
        self.names = names
        self.initial_capital = initial_capital
        self.settings = settings if settings is not None else RiskSettings()
        self.data: Dict[str, pd.DataFrame] = {
            code: add_all_indicators(df) for code, df in price_data.items() if not df.empty
        }
        if self.data:
            all_dates = sorted(set().union(*[set(df.index) for df in self.data.values()]))
        else:
            all_dates = []
        self.calendar = pd.DatetimeIndex(all_dates)

    def _price_lookup(self, date, field_name: str) -> Dict[str, float]:
        lookup = {}
        for code, df in self.data.items():
            if date in df.index:
                lookup[code] = float(df.loc[date, field_name])
        return lookup

    # ------------------------------------------------------------------
    # メインループ
    # ------------------------------------------------------------------
    def run(self) -> BacktestResult:
        settings = self.settings
        pf = Portfolio(self.initial_capital)
        pending_entries: List[str] = []
        pending_exits: Dict[str, str] = {}

        skip_log: List[Dict] = []       # 【重要1】資金不足等でスキップした記録
        signal_count = 0                 # シグナル発生回数（診断用）
        utilization_history: List[float] = []  # 日次の資金使用率(株式評価額/総資産)

        for date in self.calendar:
            close_lookup = self._price_lookup(date, "Close")
            open_lookup = self._price_lookup(date, "Open")
            low_lookup = self._price_lookup(date, "Low")
            high_lookup = self._price_lookup(date, "High")

            sizing_price_lookup = open_lookup if open_lookup else close_lookup
            equity_start = pf.total_equity(sizing_price_lookup)

            # ---------- 1) 寄り付きで前日確定分の注文を約定 ----------
            # 1a) 手仕舞い(exit)を先に約定させ、現金を確保する
            for code, reason in list(pending_exits.items()):
                if code not in pf.positions or code not in open_lookup:
                    continue
                exec_price = apply_slippage(open_lookup[code], "sell")
                shares = pf.positions[code].shares
                commission = calc_commission(shares * exec_price)
                pf.close_position(date, code, exec_price, commission, reason)
            pending_exits.clear()

            # 1b) 新規エントリーを約定
            current_equity_for_sizing = pf.total_equity(sizing_price_lookup)
            for code in pending_entries:
                if code in pf.positions:
                    continue  # 既に保有中（ナンピン禁止・重複エントリー禁止）
                if not can_open_new_position(len(pf.positions), settings):
                    skip_log.append({"date": date, "code": code, "reason": "最大保有銘柄数到達"})
                    continue
                if code not in open_lookup:
                    continue

                raw_price = open_lookup[code]
                exec_price = apply_slippage(raw_price, "buy")
                stop_price = calc_stop_loss_price(exec_price, settings)

                shares_by_risk = max_shares_by_risk(current_equity_for_sizing, exec_price, stop_price, settings)
                shares_by_pos = max_shares_by_position_limit(current_equity_for_sizing, exec_price, settings)
                shares_by_cash = int(pf.cash // (exec_price * SHARE_UNIT)) * SHARE_UNIT
                shares = min(shares_by_risk, shares_by_pos, shares_by_cash)

                if shares < SHARE_UNIT:
                    # 【重要1】シグナルはあったがリスク管理・資金制約で購入できなかったケースを記録
                    reason_detail = []
                    if shares_by_cash < SHARE_UNIT:
                        reason_detail.append("現金不足")
                    if shares_by_pos < SHARE_UNIT:
                        reason_detail.append("1銘柄最大投資比率の制約")
                    if shares_by_risk < SHARE_UNIT:
                        reason_detail.append("1取引最大リスクの制約")
                    reason_text = "資金不足(" + "・".join(reason_detail) + ")" if reason_detail else "資金不足"
                    skip_log.append({"date": date, "code": code, "reason": reason_text})
                    continue

                commission = calc_commission(shares * exec_price)
                while shares >= SHARE_UNIT and (shares * exec_price + commission) > pf.cash:
                    shares -= SHARE_UNIT
                    commission = calc_commission(shares * exec_price)
                if shares < SHARE_UNIT:
                    skip_log.append({"date": date, "code": code, "reason": "資金不足(発注直前の現金不足)"})
                    continue

                pf.open_position(date, code, self.names.get(code, code), shares, exec_price, commission)
            pending_entries = []

            # ---------- 2) 保有ポジションのリスク管理判定（損切り／トレーリング／利確） ----------
            self._apply_position_risk_management(date, pf, low_lookup, close_lookup, high_lookup,
                                                    open_lookup, settings)

            # ---------- 3) 終値確定後、翌営業日向けのシグナルを生成 ----------
            equity_now = pf.total_equity(close_lookup)
            daily_pnl = equity_now - equity_start
            halt_new_entries = (
                daily_loss_limit_hit(daily_pnl, equity_start, settings)
                or drawdown_halt_hit(equity_now, max(pf.peak_equity, equity_now), settings)
            )
            halt_reason = None
            if daily_loss_limit_hit(daily_pnl, equity_start, settings):
                halt_reason = "1日の損失上限到達"
            elif drawdown_halt_hit(equity_now, max(pf.peak_equity, equity_now), settings):
                halt_reason = "最大ドローダウン到達"

            for code, df in self.data.items():
                if date not in df.index:
                    continue
                row = df.loc[date]

                if code in pf.positions:
                    if sell_technical_signal(row):
                        pending_exits[code] = "テクニカル売りシグナル(SMA/MACDデッドクロス)"
                else:
                    check = evaluate_row(row)
                    if not check.is_buy:
                        continue
                    signal_count += 1  # 【診断】シグナル発生回数をカウント

                    if halt_new_entries:
                        skip_log.append({"date": date, "code": code, "reason": f"新規停止中({halt_reason})"})
                        continue
                    if not can_open_new_position(len(pf.positions) + len(pending_entries), settings):
                        skip_log.append({"date": date, "code": code, "reason": "最大保有銘柄数到達"})
                        continue

                    # 【重要1】終値ベースで概算し、単元株(100株)すら購入できない銘柄は
                    # ここで「資金不足」としてスキップ・記録する
                    equity_est = pf.total_equity(close_lookup)
                    if not can_afford_min_lot(pf.cash, equity_est, close_lookup[code], settings):
                        skip_log.append({"date": date, "code": code, "reason": "資金不足(100株購入不可)"})
                        continue

                    if code not in pending_entries:
                        pending_entries.append(code)

            # 【診断】日次の資金使用率(株式評価額 / 総資産)を記録
            if equity_now > 0:
                utilization_history.append(pf.stock_value(close_lookup) / equity_now)

            pf.record_equity(date, close_lookup)

        equity_df = pf.equity_dataframe()
        trades_df = pf.trades_dataframe()
        metrics = compute_metrics(equity_df, trades_df, self.initial_capital)

        diagnostics = self._compute_diagnostics(
            equity_df=equity_df, trades_df=trades_df, skip_log=skip_log,
            signal_count=signal_count, utilization_history=utilization_history,
        )
        skip_log_df = pd.DataFrame(skip_log) if skip_log else pd.DataFrame(columns=["date", "code", "reason"])

        bh_equity_df, bh_metrics = self._buy_and_hold(equity_df.index)

        return BacktestResult(
            portfolio=pf, equity_df=equity_df, trades_df=trades_df, metrics=metrics,
            settings=settings, diagnostics=diagnostics, skip_log_df=skip_log_df,
            buy_hold_equity_df=bh_equity_df, buy_hold_metrics=bh_metrics,
        )

    # ------------------------------------------------------------------
    # 保有ポジションのリスク管理（損切り／トレーリングストップ／利確）
    # ------------------------------------------------------------------
    def _apply_position_risk_management(self, date, pf: Portfolio, low_lookup, close_lookup,
                                          high_lookup, open_lookup, settings: RiskSettings):
        for code, pos in list(pf.positions.items()):
            if code not in low_lookup or code not in close_lookup:
                continue

            exited = False

            # --- 損切り判定（当日の安値がストップ価格を下回ったか） ---
            stop_price = calc_stop_loss_price(pos.entry_price, settings)
            if low_lookup[code] <= stop_price:
                fill_price = min(stop_price, open_lookup.get(code, stop_price))
                exec_price = apply_slippage(fill_price, "sell")
                commission = calc_commission(pos.shares * exec_price)
                pf.close_position(date, code, exec_price, commission, "損切り")
                exited = True

            # --- トレーリングストップ判定（【重要3】日足OHLC問題への対応） ---
            # 判定に使う high_since_entry は「前営業日までに確定した値」であり、
            # 当日のHighはまだ反映していない。これにより、
            # 「当日のHigh到達 → その後同日中に引き上げ後の水準までLowで急落」という、
            # 実際には順序が不明な値動きを未来参照的に使ってしまうことを防いでいる。
            if not exited:
                if is_trailing_stop_active(pos.entry_price, pos.high_since_entry, settings):
                    trail_price = calc_trailing_stop_price(pos.high_since_entry, settings)
                    if low_lookup[code] <= trail_price:
                        exec_price = apply_slippage(trail_price, "sell")
                        commission = calc_commission(pos.shares * exec_price)
                        pf.close_position(date, code, exec_price, commission, "トレーリングストップ")
                        exited = True

            # --- 利益確定判定（当日の終値が目標値以上か） ---
            if not exited:
                take_profit_price = calc_take_profit_price(pos.entry_price, settings)
                if close_lookup[code] >= take_profit_price:
                    exec_price = apply_slippage(close_lookup[code], "sell")
                    commission = calc_commission(pos.shares * exec_price)
                    pf.close_position(date, code, exec_price, commission, "利益確定")
                    exited = True

            # --- high_since_entry の更新は、上記のストップ判定がすべて終わった後に行う ---
            # 【重要3】ここで当日のHighを反映することで、新しく引き上げられたトレーリングストップ
            # 水準は「翌営業日」の判定から初めて使われることになり、同日内の未来参照を避けられる。
            if code in pf.positions:  # 当日中に決済されず、まだ保有中の場合のみ更新
                day_high = high_lookup.get(code, close_lookup[code])
                pf.positions[code].update_high(day_high)

    # ------------------------------------------------------------------
    # Buy & Hold 比較
    # ------------------------------------------------------------------
    def _buy_and_hold(self, dates: pd.DatetimeIndex):
        """
        初日に均等配分で購入し、最後まで保有し続けるBuy & Hold戦略との比較用データを作る。

        【重要4対応】
        100株単位の制約により、多くの銘柄が購入できず現金が大量に余る可能性があるため、
        「投資された金額」「未使用現金」「実際に購入できた銘柄数」を bh_metrics に含める。
        未使用現金の比率が大きい場合は「大量の未使用現金によって成績が歪んでいる可能性」を
        示す警告フラグ(unused_cash_warning)も付与する。
        """
        if len(dates) == 0 or not self.data:
            return None, None

        codes = list(self.data.keys())
        first_date = dates[0]
        capital_per_stock = self.initial_capital / max(len(codes), 1)

        shares_map: Dict[str, int] = {}
        cash = self.initial_capital
        invested_amount = 0.0
        for code in codes:
            df = self.data[code]
            if first_date not in df.index:
                continue
            price = float(df.loc[first_date, "Open"])
            exec_price = apply_slippage(price, "buy")
            shares = int(capital_per_stock // (exec_price * SHARE_UNIT)) * SHARE_UNIT
            if shares <= 0:
                continue
            commission = calc_commission(shares * exec_price)
            cost = shares * exec_price + commission
            if cost > cash:
                continue
            cash -= cost
            invested_amount += cost
            shares_map[code] = shares

        records = []
        for date in dates:
            value = cash
            for code, shares in shares_map.items():
                df = self.data[code]
                if date in df.index:
                    value += shares * float(df.loc[date, "Close"])
                else:
                    prior = df.index[df.index <= date]
                    if len(prior) > 0:
                        value += shares * float(df.loc[prior[-1], "Close"])
            records.append({"date": date, "equity": value})

        bh_df = pd.DataFrame(records).set_index("date")
        bh_metrics = compute_metrics(bh_df, pd.DataFrame(), self.initial_capital)

        unused_cash = cash
        unused_cash_ratio = unused_cash / self.initial_capital if self.initial_capital else 0.0
        bh_metrics.update({
            "投資済み金額": invested_amount,
            "未使用現金": unused_cash,
            "実購入銘柄数": len(shares_map),
            "対象銘柄数": len(codes),
            "未使用現金比率": unused_cash_ratio,
            # 未使用現金比率が30%を超える場合、Buy&Holdの成績が「買えなかった現金」に
            # 大きく左右されている可能性が高いため警告フラグを立てる
            "unused_cash_warning": bool(unused_cash_ratio >= 0.30),
        })
        return bh_df, bh_metrics

    # ------------------------------------------------------------------
    # 診断情報（戦略の問題か、資金不足の問題かを切り分けるための指標）
    # ------------------------------------------------------------------
    def _compute_diagnostics(self, equity_df: pd.DataFrame, trades_df: pd.DataFrame,
                               skip_log: List[Dict], signal_count: int,
                               utilization_history: List[float]) -> Dict:
        buy_trades = trades_df[trades_df["side"] == "買い"] if not trades_df.empty else trades_df
        entry_count = len(buy_trades) if buy_trades is not None else 0
        purchasable_stock_count = buy_trades["code"].nunique() if entry_count > 0 else 0

        if not equity_df.empty:
            days = (equity_df.index[-1] - equity_df.index[0]).days
            years = days / 365.25 if days > 0 else 1 / 252
        else:
            years = 0

        annual_trade_count = (entry_count / years) if years > 0 else 0

        avg_utilization = float(np.mean(utilization_history)) if utilization_history else 0.0
        max_utilization = float(np.max(utilization_history)) if utilization_history else 0.0
        cash_ratio = 1.0 - avg_utilization

        return {
            "購入できた銘柄数": purchasable_stock_count,
            "資金不足でスキップした回数": len(skip_log),
            "シグナル発生回数": signal_count,
            "実際のエントリー回数": entry_count,
            "平均資金使用率": avg_utilization,
            "最大資金使用率": max_utilization,
            "現金比率(平均)": cash_ratio,
            "年間取引回数": annual_trade_count,
        }


def compute_metrics(equity_df: pd.DataFrame, trades_df: pd.DataFrame, initial_capital: float) -> Dict:
    if equity_df is None or equity_df.empty:
        return {}

    final_equity = float(equity_df["equity"].iloc[-1])
    total_profit = final_equity - initial_capital
    profit_ratio = total_profit / initial_capital if initial_capital else 0

    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25 if days > 0 else 1 / 252
    if final_equity > 0 and years > 0:
        annual_return = (final_equity / initial_capital) ** (1 / years) - 1
    else:
        annual_return = 0.0

    if "drawdown" in equity_df.columns:
        max_dd = float(equity_df["drawdown"].max())
    else:
        running_max = equity_df["equity"].cummax()
        max_dd = float(((running_max - equity_df["equity"]) / running_max).max())

    daily_returns = equity_df["equity"].pct_change().dropna()
    sharpe = 0.0
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252))

    metrics = {
        "初期資金": initial_capital,
        "最終資産": final_equity,
        "総利益": total_profit,
        "利益率": profit_ratio,
        "年間リターン": annual_return,
        "最大ドローダウン": max_dd,
        "Sharpe Ratio": sharpe,
    }

    # 【重要2対応】勝率・平均利益・平均損失・Profit Factor は、
    # portfolio.close_position() で計算されたネット損益(pnl = 価格差 - 購入手数料 - 売却手数料)
    # を使って算出する。
    if trades_df is not None and not trades_df.empty and "pnl" in trades_df.columns:
        closed = trades_df[trades_df["pnl"].notna()]
        total_trades = len(closed)
        wins = closed[closed["pnl"] > 0]
        losses = closed[closed["pnl"] <= 0]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = float(wins["pnl"].mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses["pnl"].mean()) if len(losses) > 0 else 0.0
        gross_profit = float(wins["pnl"].sum()) if len(wins) > 0 else 0.0
        gross_loss = float(abs(losses["pnl"].sum())) if len(losses) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan

        hold_days = []
        buy_queues: Dict[str, list] = {}
        for _, r in trades_df.sort_values("datetime").iterrows():
            code = r["code"]
            if r["side"] == "買い":
                buy_queues.setdefault(code, []).append(r["datetime"])
            elif r["side"] == "売り" and buy_queues.get(code):
                bdate = buy_queues[code].pop(0)
                hold_days.append((r["datetime"] - bdate).days)
        avg_hold_days = float(np.mean(hold_days)) if hold_days else 0.0

        metrics.update({
            "勝率": win_rate,
            "総取引回数": total_trades,
            "平均利益": avg_win,
            "平均損失": avg_loss,
            "Profit Factor": profit_factor,
            "平均保有日数": avg_hold_days,
        })
    else:
        metrics.update({
            "勝率": 0, "総取引回数": 0, "平均利益": 0, "平均損失": 0,
            "Profit Factor": np.nan, "平均保有日数": 0,
        })

    return metrics
