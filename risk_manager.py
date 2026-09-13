"""
リスク管理モジュール。

・1取引あたりの許容最大損失（デフォルト: 総資産の1%）からポジションサイズを逆算
  - 買い手数料・想定売り手数料・スリッページも可能な範囲で考慮する（重要5対応）
・1銘柄への最大投資額（デフォルト: 総資産の25%）の上限
・最大同時保有銘柄数（デフォルト: 4銘柄）
・損切り(デフォルト-5%) / 利確(+10%) / トレーリングストップ(含み益+5%以上でトリガー、高値から-3%)
・1日の損失が総資産の3%を超えたら新規停止
・ピークから20%下落したら新規停止
・ナンピン（損失ポジションへの買い増し）は本アプリの構造上そもそも発生しない
  （1銘柄1ポジションまでとし、保有中銘柄への追加購入ロジックを実装していない）

【重要1対応】
リスクパラメータ（1取引最大リスク・1銘柄最大投資比率・最大同時保有数・損切り幅）は
Streamlit画面から変更できるよう、RiskSettings データクラスとして受け渡しできるようにした。
バックテスト実行時に確定した設定値は BacktestResult に保持し、画面に必ず表示する。

【重要1対応: 資金不足判定】
「現在の総資産で単元株(100株)を購入可能か」を判定する can_afford_min_lot() を追加。
購入不能な場合は呼び出し側（backtester.py）で「資金不足」としてログ・画面表示する。
"""
from dataclasses import dataclass, field

from config import (
    MAX_LOSS_PER_TRADE_RATIO, MAX_POSITION_RATIO, MAX_POSITIONS,
    STOP_LOSS_RATIO, TAKE_PROFIT_RATIO, TRAILING_STOP_TRIGGER_RATIO,
    TRAILING_STOP_DRAWDOWN_RATIO, DAILY_LOSS_LIMIT_RATIO,
    MAX_DRAWDOWN_HALT_RATIO, SHARE_UNIT, COMMISSION_RATE, MIN_COMMISSION, SLIPPAGE_RATE,
)


@dataclass
class RiskSettings:
    """画面から変更可能なリスクパラメータをまとめたデータクラス。

    バックテスト実行時にこのオブジェクトを Backtester に渡すことで、
    リスク管理ロジック側は常にこの設定値を参照する（config.py のグローバル定数には依存しない）。
    """
    max_loss_per_trade_ratio: float = MAX_LOSS_PER_TRADE_RATIO   # 1取引最大リスク (画面変更可: 0.5%〜3%)
    max_position_ratio: float = MAX_POSITION_RATIO               # 1銘柄最大投資比率 (画面変更可: 10%〜50%)
    max_positions: int = MAX_POSITIONS                             # 最大同時保有数 (画面変更可: 1〜5)
    stop_loss_ratio: float = STOP_LOSS_RATIO                       # 損切りライン (画面変更可: -2%〜-10%)
    take_profit_ratio: float = TAKE_PROFIT_RATIO
    trailing_stop_trigger_ratio: float = TRAILING_STOP_TRIGGER_RATIO
    trailing_stop_drawdown_ratio: float = TRAILING_STOP_DRAWDOWN_RATIO
    daily_loss_limit_ratio: float = DAILY_LOSS_LIMIT_RATIO
    max_drawdown_halt_ratio: float = MAX_DRAWDOWN_HALT_RATIO

    def as_display_dict(self) -> dict:
        """バックテスト結果画面に表示するための整形済み辞書"""
        return {
            "1取引最大リスク": f"{self.max_loss_per_trade_ratio * 100:.2f}%",
            "1銘柄最大投資比率": f"{self.max_position_ratio * 100:.1f}%",
            "最大同時保有数": f"{self.max_positions}銘柄",
            "損切りライン": f"{self.stop_loss_ratio * 100:.2f}%",
            "利益確定ライン": f"{self.take_profit_ratio * 100:.2f}%",
            "トレーリング発動": f"含み益{self.trailing_stop_trigger_ratio * 100:.1f}%以上",
            "トレーリング幅": f"高値から{self.trailing_stop_drawdown_ratio * 100:.1f}%",
            "1日の損失上限": f"{self.daily_loss_limit_ratio * 100:.1f}%",
            "最大ドローダウン停止": f"{self.max_drawdown_halt_ratio * 100:.1f}%",
        }


def min_purchase_amount(price: float, shares: int = SHARE_UNIT) -> float:
    """最低購入金額（単元株分）"""
    if price is None or price <= 0:
        return 0.0
    return price * shares


def can_afford_min_lot(cash: float, total_equity: float, price: float, settings: RiskSettings) -> bool:
    """
    現在の資金・総資産で単元株(100株)を購入できるかを判定する。
    ・cash: 現金が最低購入金額を下回っていないか
    ・total_equity × 1銘柄最大投資比率: 100株分の金額がこの上限を超えていないか
    """
    if price is None or price <= 0:
        return False
    min_amount = min_purchase_amount(price)
    max_position_amount = total_equity * settings.max_position_ratio
    if min_amount > max_position_amount:
        return False
    if min_amount > cash:
        return False
    return True


def max_shares_by_risk(
    total_equity: float,
    entry_price: float,
    stop_price: float,
    settings: RiskSettings,
    commission_rate: float = COMMISSION_RATE,
    min_commission: float = MIN_COMMISSION,
    slippage_rate: float = SLIPPAGE_RATE,
) -> int:
    """
    1取引の最大許容損失額(総資産×max_loss_per_trade_ratio)から逆算した最大株数(単元株丸め)。

    【重要5対応】
    損切り時に実際に発生する損失には、価格差だけでなく
    「買い手数料」「売り手数料（損切り約定時）」「スリッページ」も含まれる。
    これらを考慮せずに株数を決めると、「1%リスク」のつもりが手数料・スリッページ分
    だけ実際の損失が予算を超えてしまう。

    そこで、
      1) まず手数料を比例部分のみで概算した株数を求め、
      2) 実際の手数料（最低手数料の下限あり）を使って想定損失を再計算し、
         予算(max_loss_amount)を超えている場合は単元株単位で株数を減らして再調整する。
    という2段階の計算で「損切り時の総損失が可能な限り総資産のX%以内に収まる」ようにする。
    """
    if entry_price <= 0 or stop_price >= entry_price:
        return 0

    max_loss_amount = total_equity * settings.max_loss_per_trade_ratio
    if max_loss_amount <= 0:
        return 0

    # 損切り約定時の想定価格（スリッページで不利な方向に約定する）
    exit_price_est = stop_price * (1 - slippage_rate)
    price_risk_per_share = entry_price - exit_price_est
    if price_risk_per_share <= 0:
        return 0

    # 1) 手数料を比例部分のみで概算した株数（最低手数料は無視した粗い見積もり）
    effective_risk_per_share = price_risk_per_share + commission_rate * (entry_price + exit_price_est)
    if effective_risk_per_share <= 0:
        return 0
    approx_shares = int(max_loss_amount / effective_risk_per_share)
    shares = (approx_shares // SHARE_UNIT) * SHARE_UNIT

    def estimated_total_loss(sh: int) -> float:
        if sh <= 0:
            return 0.0
        entry_comm = max(sh * entry_price * commission_rate, min_commission)
        exit_comm = max(sh * exit_price_est * commission_rate, min_commission)
        return price_risk_per_share * sh + entry_comm + exit_comm

    # 2) 最低手数料も含めた正確な想定損失で、予算内に収まるまで株数を単元株単位で削る
    while shares > 0 and estimated_total_loss(shares) > max_loss_amount:
        shares -= SHARE_UNIT

    return max(shares, 0)


def max_shares_by_position_limit(total_equity: float, entry_price: float, settings: RiskSettings) -> int:
    """1銘柄への最大投資額(総資産×max_position_ratio)から逆算した最大株数(単元株丸め)"""
    if entry_price <= 0:
        return 0
    max_amount = total_equity * settings.max_position_ratio
    shares = int(max_amount / entry_price)
    shares = (shares // SHARE_UNIT) * SHARE_UNIT
    return max(shares, 0)


def calc_stop_loss_price(entry_price: float, settings: RiskSettings) -> float:
    return entry_price * (1 + settings.stop_loss_ratio)


def calc_take_profit_price(entry_price: float, settings: RiskSettings) -> float:
    return entry_price * (1 + settings.take_profit_ratio)


def is_trailing_stop_active(entry_price: float, high_since_entry: float, settings: RiskSettings) -> bool:
    if entry_price <= 0:
        return False
    gain_ratio = (high_since_entry - entry_price) / entry_price
    return gain_ratio >= settings.trailing_stop_trigger_ratio


def calc_trailing_stop_price(high_since_entry: float, settings: RiskSettings) -> float:
    return high_since_entry * (1 - settings.trailing_stop_drawdown_ratio)


@dataclass
class ExitCheckResult:
    should_exit: bool
    reason: str = ""


def can_open_new_position(current_positions: int, settings: RiskSettings) -> bool:
    return current_positions < settings.max_positions


def daily_loss_limit_hit(daily_pnl: float, equity_start_of_day: float, settings: RiskSettings) -> bool:
    """当日の損益が総資産のX%を超えて悪化した場合True（当日の新規取引を停止する）"""
    if equity_start_of_day <= 0:
        return False
    return (daily_pnl / equity_start_of_day) <= -settings.daily_loss_limit_ratio


def drawdown_halt_hit(current_equity: float, peak_equity: float, settings: RiskSettings) -> bool:
    """ピークからのドローダウンがX%以上の場合True（新規取引を停止する）"""
    if peak_equity <= 0:
        return False
    drawdown = (peak_equity - current_equity) / peak_equity
    return drawdown >= settings.max_drawdown_halt_ratio
