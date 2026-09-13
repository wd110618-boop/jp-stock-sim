"""
アプリ全体の設定値をまとめたモジュール。

APIキー等の秘匿情報は .env から読み込み、ソースコードには直書きしない。
PAPER_MODE は「実売買コードが誤って実行されない」ための安全スイッチ。
今回のMVPでは実際の証券会社APIとの接続コード自体が存在しないため、
PAPER_MODE を False にしても実発注は行われない(将来の拡張に備えた安全弁)。
"""
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 安全スイッチ
# ============================================================
PAPER_MODE = True  # ペーパートレード専用。実口座とは接続しません。

# ============================================================
# 初期資金・売買単位
# ============================================================
INITIAL_CAPITAL = 500_000      # 初期資金 50万円
TARGET_CAPITAL = 1_000_000     # 目標資産 100万円（グラフ表示用の目安ライン）
SHARE_UNIT = 100                # 単元株数（日本株の基本単位）

# ============================================================
# リスク管理パラメータ
# ============================================================
MAX_LOSS_PER_TRADE_RATIO = 0.01       # 1取引あたり許容最大損失: 総資産の1%
MAX_POSITION_RATIO = 0.25             # 1銘柄への最大投資額: 総資産の25%
MAX_POSITIONS = 4                     # 最大同時保有銘柄数
STOP_LOSS_RATIO = -0.05               # 初期損切りライン: 購入価格から-5%
TAKE_PROFIT_RATIO = 0.10              # 利益確定ライン: +10%
TRAILING_STOP_TRIGGER_RATIO = 0.05    # 含み益がこの水準を超えたらトレーリングストップ有効
TRAILING_STOP_DRAWDOWN_RATIO = 0.03   # 高値からの許容下落率（トレーリング幅）
DAILY_LOSS_LIMIT_RATIO = 0.03         # 1日の損失が総資産の3%を超えたらその日は新規停止
MAX_DRAWDOWN_HALT_RATIO = 0.20        # 総資産がピークから20%下落したら新規停止
ALLOW_AVERAGING_DOWN = False           # ナンピン禁止（固定）

# ============================================================
# テクニカル指標パラメータ
# ============================================================
SMA_SHORT = 5
SMA_MID = 20
SMA_LONG = 60
RSI_PERIOD = 14
RSI_BUY_MIN = 50
RSI_BUY_MAX = 70
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
VOLUME_AVG_PERIOD = 20

# ============================================================
# バックテスト設定
# ============================================================
DEFAULT_BACKTEST_YEARS = 5

COMMISSION_RATE = 0.0005   # 手数料率（約定代金に対する割合・片道）
MIN_COMMISSION = 55        # 最低手数料（円）
SLIPPAGE_RATE = 0.001      # スリッページ（約定価格に対する割合）

# ============================================================
# 対象銘柄（初期登録） コード: 銘柄名
# ============================================================
DEFAULT_UNIVERSE: List[Dict[str, str]] = [
    {"code": "7203", "name": "トヨタ自動車"},
    {"code": "8306", "name": "三菱UFJフィナンシャル・グループ"},
    {"code": "9984", "name": "ソフトバンクグループ"},
    {"code": "6758", "name": "ソニーグループ"},
    {"code": "6501", "name": "日立製作所"},
    {"code": "8035", "name": "東京エレクトロン"},
    {"code": "6861", "name": "キーエンス"},
    {"code": "9432", "name": "NTT"},
    {"code": "8058", "name": "三菱商事"},
    {"code": "4063", "name": "信越化学工業"},
]


def to_ticker(code: str) -> str:
    """東証コードをyfinance用ティッカーに変換 (例: 7203 -> 7203.T)"""
    code = code.strip()
    if code.upper().endswith(".T"):
        return code.upper()
    return f"{code}.T"


# ============================================================
# 証券会社API設定（将来拡張用・現MVPでは未使用）
# .env に記載し、ソースコードには直書きしない。
#
# 【クラウド公開対応】
# ローカル実行では .env（python-dotenv）から、Streamlit Community Cloud等に
# デプロイした場合は st.secrets（Secrets管理画面で設定）から読み込めるよう、
# st.secrets を優先しつつ .env / 環境変数にフォールバックする構造にしている。
# st.secrets はStreamlitの実行コンテキスト外や secrets.toml が存在しない環境では
# 例外を送出することがあるため、必ず try/except で保護する。
# ============================================================
def _get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st  # 遅延importでStreamlit実行コンテキスト外でも壊れないようにする
        if hasattr(st, "secrets"):
            try:
                if key in st.secrets:
                    return st.secrets[key]
            except Exception:
                pass  # secrets.toml が存在しない等の場合は無視してフォールバック
    except Exception:
        pass
    return os.getenv(key, default)


BROKER_API_KEY = _get_secret("BROKER_API_KEY", "")
BROKER_API_SECRET = _get_secret("BROKER_API_SECRET", "")
BROKER_ACCOUNT_ID = _get_secret("BROKER_ACCOUNT_ID", "")
