"""ポートフォリオ管理モジュール（現金・保有ポジション・取引履歴・資産推移）

【重要2対応】
Position に entry_commission（購入時手数料）を保持し、決済時の実現損益(pnl)を

    (売値 - 買値) × 株数 - 購入時手数料 - 売却時手数料

として計算する（従来は購入時手数料が損益計算から漏れていた）。
勝率・平均利益・平均損失・Profit Factor はすべてこのネット損益(pnl)から算出される
（backtester.compute_metrics を参照）。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class Position:
    code: str
    name: str
    shares: int
    entry_price: float
    entry_date: object
    high_since_entry: float
    entry_commission: float = 0.0  # 購入時手数料（重要2対応: 決済損益の計算に必ず含める）

    def update_high(self, high_price: float):
        if high_price > self.high_since_entry:
            self.high_since_entry = high_price

    def market_value(self, current_price: float) -> float:
        return self.shares * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.shares

    def unrealized_pnl_ratio(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price


@dataclass
class TradeRecord:
    datetime: object
    code: str
    name: str
    side: str  # "買い" or "売り"
    shares: int
    price: float
    amount: float
    commission: float
    pnl: Optional[float]
    reason: str


class Portfolio:
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[TradeRecord] = []
        self.equity_curve: List[Dict] = []
        self.peak_equity = initial_capital

    def total_equity(self, price_lookup: Dict[str, float]) -> float:
        return self.cash + self.stock_value(price_lookup)

    def stock_value(self, price_lookup: Dict[str, float]) -> float:
        return sum(
            pos.market_value(price_lookup.get(code, pos.entry_price))
            for code, pos in self.positions.items()
        )

    def open_position(self, date, code: str, name: str, shares: int, price: float, commission: float):
        cost = shares * price + commission
        self.cash -= cost
        self.positions[code] = Position(
            code=code, name=name, shares=shares, entry_price=price,
            entry_date=date, high_since_entry=price,
            entry_commission=commission,  # 重要2対応: 購入時手数料を保持し、決済時の損益計算に使う
        )
        self.trades.append(TradeRecord(
            datetime=date, code=code, name=name, side="買い", shares=shares,
            price=price, amount=shares * price, commission=commission,
            pnl=None, reason="新規エントリー",
        ))

    def close_position(self, date, code: str, price: float, commission: float, reason: str):
        pos = self.positions.pop(code, None)
        if pos is None:
            return
        proceeds = pos.shares * price - commission
        self.cash += proceeds
        # 重要2対応: 実現損益 = (売値-買値)×株数 - 購入時手数料 - 売却時手数料
        # (従来は購入時手数料 pos.entry_commission が計算から漏れていた)
        pnl = (price - pos.entry_price) * pos.shares - pos.entry_commission - commission
        self.trades.append(TradeRecord(
            datetime=date, code=code, name=pos.name, side="売り", shares=pos.shares,
            price=price, amount=pos.shares * price, commission=commission,
            pnl=pnl, reason=reason,
        ))

    def record_equity(self, date, price_lookup: Dict[str, float]):
        equity = self.total_equity(price_lookup)
        stock_val = self.stock_value(price_lookup)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.equity_curve.append({
            "date": date, "equity": equity, "cash": self.cash,
            "stock_value": stock_val, "peak": self.peak_equity, "drawdown": drawdown,
        })

    def equity_dataframe(self) -> pd.DataFrame:
        if not self.equity_curve:
            return pd.DataFrame(columns=["date", "equity", "cash", "stock_value", "peak", "drawdown"]).set_index("date")
        df = pd.DataFrame(self.equity_curve)
        df.set_index("date", inplace=True)
        return df

    def trades_dataframe(self) -> pd.DataFrame:
        cols = ["datetime", "code", "name", "side", "shares", "price", "amount", "commission", "pnl", "reason"]
        if not self.trades:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([t.__dict__ for t in self.trades])[cols]
