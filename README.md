# 日本株 自動売買シミュレーター（バックテスト・ペーパートレード版）

初期資金50万円から日本株の自動売買（トレンドフォロー戦略）を行った場合の
資産推移を検証する **Streamlit製バックテストアプリ** です。
PC・スマートフォンの両方から使いやすいUIになっており、
Streamlit Community Cloud等へそのまま公開できる構成です。

> ⚠️ **本アプリは仮想売買（ペーパートレード）専用です。**
> 実際の証券口座には一切接続せず、実発注コードも含まれていません。
> `config.py` の `PAPER_MODE = True` が安全スイッチとなっており、
> `main.py` はこれが `True` でない場合、`if not PAPER_MODE: st.error(...); st.stop()`
> により確実にアプリを停止します（`assert` の最適化無効化リスクを避けるための対応）。
> 公開URLを誰が開いても、実売買が発生することはありません。

---

## 目次

1. [全体設計](#1-全体設計)
2. [フォルダ構成](#2-フォルダ構成)
3. [必要ライブラリ](#3-必要ライブラリ)
4. [実装済みの主な機能](#4-実装済みの主な機能)
5. [スマホ対応・UIについて](#5-スマホ対応uiについて)
6. [PCでの起動方法（Windows）](#6-pcでの起動方法windows)
7. [スマートフォンから使う方法（同一Wi-Fi内）](#7-スマートフォンから使う方法同一wi-fi内)
8. [Streamlit Community Cloudへの公開手順](#8-streamlit-community-cloudへの公開手順)
9. [環境変数・Secretsの扱い](#9-環境変数secretsの扱い)
10. [ホーム画面に追加する方法（アプリのように使う）](#10-ホーム画面に追加する方法アプリのように使う)
11. [注意事項・免責事項](#11-注意事項免責事項)
12. [スマホだけで完結させる場合（PC不要）](#12-スマホだけで完結させる場合pc不要)

---

## 1. 全体設計

```
[data_provider.py]  無料データ(yfinance)から日足OHLCVを取得
        │
[indicators.py]     SMA/RSI/MACD/ATR/出来高平均などのテクニカル指標を計算
        │
[strategy.py]        買い条件(6項目)・売り条件(テクニカル部分)を判定
        │
[risk_manager.py]    RiskSettings（画面から変更可能なリスクパラメータ）に基づき、
                      ポジションサイズ計算・損切り/利確/トレーリング・
                      1日の損失上限・最大ドローダウン停止・資金不足判定を行う
        │
[backtester.py]      日々のシグナル確定→翌営業日始値で約定、というルールで
                      Look-ahead biasを排除しながらバックテストを実行。
                      Buy&Holdとの比較、診断情報、各種成績指標の計算も行う
        │
[portfolio.py]       現金・保有ポジション・取引履歴・資産推移を管理
                      （実現損益は購入時・売却時の手数料を差し引いたネット損益）
        │
[trade_logger.py]    取引履歴をCSV出力
        │
[dashboard.py]       Streamlit UI部品（レスポンシブなカードグリッド・
                      スマホ対応テーブル・グラフ設定など、表示専用）
        │
[main.py]            アプリ全体の画面構成・設定の相互同期・表示モード切替
```

**計算ロジックとUIの分離**: `backtester.py` / `risk_manager.py` / `portfolio.py` /
`strategy.py` / `indicators.py` / `data_provider.py` / `trade_logger.py` は
バックテストの計算そのものを担うモジュールで、スマホ対応の際も一切変更していません。
UI（表示・操作性）に関する変更は `dashboard.py` と `main.py` のみに閉じています。

## 2. フォルダ構成

```
jp_stock_sim/
├── main.py                    # Streamlitアプリのエントリーポイント（画面構成・設定同期）
├── config.py                   # 設定値（初期資金・リスク管理パラメータ・銘柄リスト・Secrets読込）
├── data_provider.py             # 株価データ取得（yfinance、将来API差し替え可能）
├── indicators.py                  # テクニカル指標計算
├── strategy.py                     # 売買シグナル判定
├── risk_manager.py                  # リスク管理（RiskSettings・ポジションサイズ・損切り等）
├── backtester.py                     # バックテストエンジン
├── portfolio.py                       # 資産・ポジション・取引履歴管理
├── trade_logger.py                     # 取引履歴CSV出力
├── dashboard.py                         # Streamlit UI部品（レスポンシブ対応）
├── requirements.txt
├── .env.example                         # ローカル用の環境変数サンプル
├── .streamlit/
│   ├── config.toml                       # サーバー・テーマ設定
│   └── secrets.toml.example               # Streamlit Cloud用Secretsのサンプル
├── .gitignore
└── README.md
```

## 3. 必要ライブラリ

`requirements.txt` に実際に使用しているライブラリをすべて記載しています。

- `streamlit` — Webアプリのフレームワーク
- `pandas` / `numpy` — データ処理・数値計算
- `yfinance` — 無料の株価データ取得
- `plotly` — 資産推移グラフ
- `python-dotenv` — ローカル実行時の `.env` 読み込み

バージョンは下限のみを指定しています（上限固定にすると、クラウド側の
クリーンビルドで将来的にインストールが失敗しやすくなるため）。理由の詳細は
`requirements.txt` 内のコメントを参照してください。

---

## 4. 実装済みの主な機能

- 対象銘柄（初期登録・画面から追加/削除可能、東証コード10銘柄）
- シンプルなトレンドフォロー戦略（SMA/RSI/MACD/出来高による買い条件、
  デッドクロス・損切り・利確・トレーリングストップによる売り条件）
- リスク管理（1取引最大リスク・1銘柄最大投資比率・最大同時保有数・損切り幅を
  画面から変更可能。手数料・スリッページを考慮したポジションサイズ計算）
- Look-ahead biasを排除したバックテスト（シグナル確定の翌営業日始値で約定）
- 手数料・スリッページ・100株単位・購入可能資金・同時保有数を考慮
- ネット損益（購入時・売却時手数料を差し引いた実現損益）に基づく成績集計
- Buy & Holdとの比較（投資済み金額・未使用現金・実購入銘柄数も表示）
- 資金不足で購入できなかった記録のログ表示
- 「戦略が悪いのか／資金不足なのか」を切り分ける診断セクション
- 取引履歴のCSVダウンロード
- **広域スクリーニング**: バックテスト対象の10銘柄とは別に、大型株ユニバース
  （約99銘柄、独自にまとめた概算リスト）全体に対して現在の買いシグナルを一覧表示
  （画面上部の「🔍 広域スクリーニング」から、バックテスト未実行でもいつでも単独で使える。
  銘柄リストは`config.py`の`SCREENING_UNIVERSE`で編集可能。JPX公式のTOPIX100構成銘柄とは
  完全には一致しない場合があります）

---

## 5. スマホ対応・UIについて

- **レスポンシブなカード表示**: ダッシュボードの指標・使用リスク設定値・
  診断情報・Buy&Hold内訳は、CSS Grid（`auto-fit, minmax()`）による
  自動折り返しカードで表示しています。JavaScriptによる端末判定を使わず、
  画面幅が狭くなれば自動的に1〜2列に折り返され、PCでは3〜6列程度で表示されます。
- **設定の二重管理防止**: バックテスト期間・リスクパラメータ・対象銘柄は、
  PC向けの「サイドバー」とスマホ向けの「メイン画面上部のexpander」の
  両方から操作できますが、`st.session_state` のコールバックで常に相互同期しており、
  どちらを操作しても同じ設定として扱われます（`main.py` の `_linked_slider` 参照）。
- **タップしやすいボタン・入力欄**: 主要ボタンは横幅いっぱい・大きめのフォント・
  タップ領域を確保するCSSを適用しています。「バックテスト実行」ボタンは
  特に目立つスタイルにしています。
- **グラフのスマホ対応**: `width="stretch"` を維持しつつ、「かんたん表示」時は
  グラフの高さと凡例フォントを抑えます。ピンチズーム・横スクロールを
  妨げないPlotly設定（`scrollZoom: True` 等）を使用しています。
- **テーブルのスマホ対応**: 重要な列（日時・銘柄コード・売買・損益など）を
  先頭に配置し、Streamlit標準の横スクロールに委ねることで、列がはみ出しても
  表が崩れないようにしています。「現在の買いシグナル」はカード形式で、
  銘柄・総合判定・購入可能株数・必要最低購入金額・資金状況を最優先表示し、
  SMA/RSI/MACD/出来高の内訳は折りたたみ（expander）に格納しています。
- **かんたん表示 / 詳細表示**: 画面上部のトグルで切り替えられます。
  かんたん表示では「総資産・利益率・最大ドローダウン・資産推移グラフ・
  現在の買いシグナル」のみを表示し、詳細表示ではすべての指標・タブ
  （保有銘柄・売買履歴・銘柄ごとの成績・資金不足ログ等）を表示します。
  端末の自動判定は行っていません（不安定になりやすいため、手動切り替えとしています）。

---

## 6. PCでの起動方法（Windows）

### 6-1. Pythonのインストール

1. [Python公式サイト](https://www.python.org/downloads/) から Python 3.10〜3.12 系のインストーラをダウンロード
2. インストーラ起動時、**「Add python.exe to PATH」に必ずチェック**を入れてから「Install Now」
3. インストール後、コマンドプロンプト（`Win + R` → `cmd` → Enter）で確認

```bat
python --version
```

と入力し、`Python 3.x.x` と表示されればOKです。

### 6-2. アプリのファイルを配置

このフォルダ（`jp_stock_sim`）を、例えば `C:\Users\あなたの名前\jp_stock_sim` に配置してください。

### 6-3. 仮想環境の作成（推奨）

```bat
cd C:\Users\あなたの名前\jp_stock_sim
python -m venv venv
venv\Scripts\activate
```

`(venv)` が行頭に表示されれば仮想環境が有効になっています。

### 6-4. 必要ライブラリのインストール

```bat
pip install -r requirements.txt
```

エラーが出た場合は、先に以下を実行してから再度お試しください。

```bat
python -m pip install --upgrade pip
```

### 6-5. .envファイルの準備（今回のMVPでは必須ではありません）

```bat
copy .env.example .env
```

将来証券会社APIと接続する際に使用する設定です。今回は空のままで問題ありません。

### 6-6. Streamlitアプリの起動

```bat
streamlit run main.py
```

自動的にブラウザが起動し、`http://localhost:8501` で
「日本株 自動売買シミュレーター」の画面が表示されます。

### 6-7. アプリの終了

コマンドプロンプトで `Ctrl + C` を押すとアプリが停止します。

---

## 7. スマートフォンから使う方法（同一Wi-Fi内）

PCとスマートフォンが**同じWi-Fiに接続されている**必要があります。

### 7-1. PC側の準備

1. 上記「6. PCでの起動方法」の手順で `streamlit run main.py` を実行します。
2. コマンドプロンプトに表示される起動ログを確認します。

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

`Network URL`（`http://192.168.x.x:8501` のような形式）がスマホからアクセスするURLです。

3. Windowsの「ファイアウォールでこのアプリの通信を許可しますか？」という
   確認ダイアログが出た場合は「アクセスを許可する」を選択してください。
   （プライベートネットワークのみ許可すれば十分です）

### 7-2. スマートフォン側の操作

1. スマートフォンをPCと同じWi-Fiに接続します。
2. ブラウザ（Safari / Chrome等）を開き、`Network URL` に表示されたアドレス
   （例: `http://192.168.1.23:8501`）を入力してアクセスします。
3. 画面上部の「表示モード」を「かんたん表示」にすると、必要最小限の情報のみが表示されます。
4. 「⚙️ バックテスト設定」のexpanderをタップして開き、期間・リスクパラメータ・
   対象銘柄を設定して「🚀 バックテスト実行」をタップしてください。

うまく接続できない場合、PC側のセキュリティソフトやファイアウォールが
通信をブロックしている可能性があります。その場合は一時的に許可設定を確認してください。

---

## 8. Streamlit Community Cloudへの公開手順

### 8-1. GitHubへの配置手順

1. [GitHub](https://github.com/) のアカウントを作成（未作成の場合）。
2. 新しいリポジトリを作成します（例: `jp-stock-sim`）。Public / Privateどちらでも構いません。
3. このフォルダ（`jp_stock_sim`）の中身一式をリポジトリにアップロードします。
   - GitHub Desktop を使う場合: リポジトリをクローン → フォルダの中身をコピー → コミット → プッシュ
   - コマンドラインを使う場合の例:

```bat
cd C:\Users\あなたの名前\jp_stock_sim
git init
git add .
git commit -m "Initial commit: 日本株自動売買シミュレーター"
git branch -M main
git remote add origin https://github.com/あなたのユーザー名/jp-stock-sim.git
git push -u origin main
```

   **`.env` や `.streamlit/secrets.toml` は `.gitignore` に含まれているため、
   誤ってGitHubにアップロードされることはありません。**

### 8-2. Streamlit Community Cloudでのデプロイ

1. [Streamlit Community Cloud](https://streamlit.io/cloud) にアクセスし、GitHubアカウントでログインします。
2. 「New app」（新しいアプリを作成）をクリックします。
3. 以下を設定します。
   - **Repository**: 先ほど作成したリポジトリ（例: `あなたのユーザー名/jp-stock-sim`）
   - **Branch**: `main`
   - **Main file path**: `main.py`
4. 「Deploy」をクリックすると、`requirements.txt` に基づいて自動的に環境が構築され、
   数分でアプリが公開されます。
5. 公開されたURL（例: `https://jp-stock-sim-xxxx.streamlit.app`）に、
   PC・スマートフォンどちらからでもアクセスできます。

### 8-3. requirements.txtの使い方

Streamlit Community Cloud は、リポジトリ直下（またはmain.pyと同じ階層）の
`requirements.txt` を自動的に検出し、記載されたライブラリを順にインストールします。
本アプリでは追加のインストール作業は不要です。ローカルでも同じファイルを使うため、
ローカル環境とクラウド環境で依存ライブラリのズレが起きにくい構成になっています。

---

## 9. 環境変数・Secretsの扱い

本アプリは今回のMVPでは証券会社APIキー等を**使用しません**が、
将来の拡張に備えて以下の二段構えの読み込み構造を用意しています（`config.py`参照）。

| 実行環境 | 読み込み元 | 設定ファイル |
|---|---|---|
| ローカル（PC） | `.env`（python-dotenv） | `.env`（`.env.example` をコピーして作成） |
| Streamlit Community Cloud | `st.secrets` | アプリ管理画面の「Settings → Secrets」 |

`config.py` の `_get_secret()` 関数が `st.secrets` を優先的に確認し、
存在しない場合は環境変数（`.env` 経由を含む）にフォールバックします。
どちらの環境でも**APIキー等をソースコードに直書きすることはありません**。

Streamlit Community Cloudでの設定例（アプリ管理画面のSecretsに貼り付ける内容。
`.streamlit/secrets.toml.example` と同じ形式です）:

```toml
BROKER_API_KEY = ""
BROKER_API_SECRET = ""
BROKER_ACCOUNT_ID = ""
```

**`.env` および `.streamlit/secrets.toml` は絶対にGitへコミットしないでください**
（`.gitignore` で既に除外されています）。

---

## 10. ホーム画面に追加する方法（アプリのように使う）

本格的なPWA（Progressive Web App）化は今回のスコープ外ですが、
スマートフォンのブラウザ機能を使って簡易的にアプリのように使うことができます。

**ページタイトル**は `日本株 自動売買シミュレーター`、**アイコン**は 📈（絵文字）を
`st.set_page_config(page_title=..., page_icon="📈", ...)` で設定済みです。

### iPhone（Safari）の場合
1. アプリのURLをSafariで開く
2. 画面下部の「共有」アイコンをタップ
3. 「ホーム画面に追加」を選択
4. 名前を確認して「追加」をタップ

### Android（Chrome）の場合
1. アプリのURLをChromeで開く
2. 右上のメニュー（縦三点アイコン）をタップ
3. 「ホーム画面に追加」または「アプリをインストール」を選択
4. 名前を確認して「追加」をタップ

これにより、ホーム画面のアイコンからブラウザのアドレスバーなしで
アプリのように起動できます（Streamlitアプリ自体はブラウザ上で動作します）。

---

## 11. 注意事項・免責事項

- 株価データはYahoo! Finance（yfinance経由）の無料データを使用しています。
  データの正確性・取得可否は保証されません。取得できない銘柄がある場合は
  画面上に警告が表示されます。
- 本アプリはあくまで**教育・検証目的のシミュレーター**であり、将来の運用成績を
  保証するものではありません。「必ず資産が2倍になる」ことを目的とした
  戦略ではなく、リスクとリターンの関係を検証するためのツールです。
- 実際の株式投資は元本割れのリスクを伴います。投資判断は自己責任で行ってください。
- 本アプリは**ペーパートレード専用**です。`config.py` の `PAPER_MODE = True` が
  安全スイッチとなっており、実口座への発注機能・実売買コードは一切含まれていません。
  公開URLを第三者が開いても、実際の売買が発生することはありません。
- 次のステップとして証券会社APIと接続する場合は、`data_provider.py` の
  `BaseDataProvider` を継承する形で新しいデータ取得クラスを追加し、
  発注処理についても新しいモジュールとして慎重に設計・実装してください。

---

## 12. スマホだけで完結させる場合（PC不要）

**PCを一切使わず、スマートフォン（Android / iPhone）のブラウザだけ**で、
「コード一式の取得 → GitHubへの配置 → Streamlit Community Cloudへの公開 →
アプリの利用」まですべて完結させることができます。
GitHub・Streamlit Community Cloudのサイトはどちらもモバイルブラウザ対応（レスポンシブ）なので、
特別なアプリのインストールは不要です（GitHubの公式アプリも補助的に使えますが必須ではありません）。

### 12-1. 全体の流れ

```
① このチャットからZIPファイルをスマホにダウンロード
        │
② スマホの「ファイル」アプリ（iPhone）/「Files」アプリ（Android）でZIPを展開
        │
③ github.com にスマホのブラウザでログイン（アカウントがなければ作成）
        │
④ 新しいリポジトリを作成
        │
⑤ 展開したファイルをブラウザから「Upload files」でアップロード
        │
⑥ share.streamlit.io（Streamlit Community Cloud）にログインし「New app」で公開
        │
⑦ 公開されたURLにスマホからアクセスして完了
```

### 12-2. ①ZIPファイルのダウンロード

このチャットに添付されている `jp_stock_sim.zip` をタップし、スマホの
ダウンロード（またはファイル）フォルダに保存してください。

### 12-3. ②ZIPファイルの展開

- **iPhone**: 標準の「ファイル」アプリを開く → 「ダウンロード」フォルダの
  `jp_stock_sim.zip` を長押し（または軽くタップ）→ 「展開」を選択すると、
  同じ場所に `jp_stock_sim` フォルダが作成されます。
- **Android**: 標準の「Files」アプリ（または「ファイル」アプリ）を開く →
  ダウンロードフォルダの `jp_stock_sim.zip` をタップ →
  「解凍」「Extract」等のメニューを選択します。
  機種によって「Files」アプリに展開機能がない場合は、Playストアで
  「ZIP Extractor」等の無料アプリを追加してください。

展開すると、`main.py` や `config.py` などのファイル一式と、
隠しフォルダ `.streamlit`（`config.toml` と `secrets.toml.example` を含む）が
展開先フォルダの中に見えるようになります。
**`.streamlit` のような「.（ドット）」から始まるフォルダ・ファイルは、
ファイルアプリの設定で「隠しファイルを表示」をONにしないと見えないことがあります。**
見えない場合でも心配は不要です（後述の方法でカバーできます）。

### 12-4. ③④ GitHubでアカウント作成・リポジトリ作成

1. スマホのブラウザで [https://github.com](https://github.com) を開きます。
2. アカウントがなければ「Sign up」から作成します（メールアドレス・パスワードのみで作成可能）。
3. ログイン後、画面右上の「+」アイコン（またはメニュー）から
   「New repository」を選択します。
4. 以下を入力します。
   - **Repository name**: 例 `jp-stock-sim`
   - **Public / Private**: どちらでも構いません（Publicにすると誰でもコードを閲覧できます）
   - 「Add a README file」はチェックを**外したまま**で構いません
5. 「Create repository」をタップします。

### 12-5. ⑤ ファイルのアップロード

作成したリポジトリの画面で、以下の操作をします。

1. 「Add file」→「Upload files」をタップします。
2. 「choose your files」（またはファイル選択エリア）をタップし、
   ②で展開したフォルダの中身を選択します。
   - スマホの機種・ブラウザによっては**複数ファイルを一度に選択**できます
     （フォルダの中を開いて全選択、またはCtrl/Shiftに相当する長押し選択）。
   - 一度に選択できない場合は、何回かに分けてアップロードしても問題ありません
     （後から追加でアップロードできます）。
3. 通常のファイル（`main.py`、`config.py`、`requirements.txt`、`README.md` など）は
   そのままアップロードすれば、リポジトリの直下に配置されます。
4. **`.streamlit` フォルダの中身（`config.toml`、`secrets.toml.example`）が
   ファイル選択画面に出てこない場合**は、以下のどちらかの方法で対応してください。
   - 方法A: 「Add file」→「Create new file」を選び、ファイル名の入力欄に
     `.streamlit/config.toml` と**スラッシュ区切りで直接入力**します
     （GitHubがこの入力だけで自動的にフォルダを作成してくれます）。
     中身は、このチャットに表示された `config.toml` の内容をコピー＆ペーストしてください。
     同じ手順で `.streamlit/secrets.toml.example` も作成します。
   - 方法B: ZIP展開アプリの設定で「隠しファイルを表示」をONにしてから、
     もう一度アップロード操作をやり直します。
5. 画面下部の「Commit changes」（コミットメッセージ欄）に
   `Initial commit` などと入力し、「Commit changes」ボタンをタップします。

これでリポジトリへのファイル配置が完了です。
リポジトリのトップページに `main.py` や `requirements.txt` が
表示されていれば成功です。

> 💡 **もっと簡単な方法（ファイル数が多くて大変なとき）**:
> ZIPの展開・アップロードが難しい場合は、各ファイルごとに
> 「Add file」→「Create new file」でファイル名を入力し、
> このチャットに表示されているコードをそのままコピー＆ペーストして
> 1つずつ作成する方法でも、まったく同じ結果になります（手間はかかりますが、
> ZIP展開アプリが使えない場合の確実な代替手段です）。

### 12-6. ⑥ Streamlit Community Cloudで公開

1. スマホのブラウザで [https://share.streamlit.io](https://share.streamlit.io) を開きます。
2. 「Continue with GitHub」等でログインします（GitHubアカウントでの認証を許可します）。
3. 「Create app」または「New app」をタップします。
4. 以下を設定します。
   - **Repository**: 先ほど作成したリポジトリ（例 `あなたのユーザー名/jp-stock-sim`）
   - **Branch**: `main`
   - **Main file path**: `main.py`
5. 「Deploy」をタップします。数分待つとビルドが完了し、
   `https://xxxxx.streamlit.app` のような公開URLが発行されます。

Secrets（今回のMVPでは空のままで構いません）を設定する場合は、
アプリ管理画面の「Settings」→「Secrets」からスマホでも入力できます
（内容は `.streamlit/secrets.toml.example` を参照）。

### 12-7. ⑦ 公開されたアプリを使う

発行されたURL（`https://xxxxx.streamlit.app`）にスマホのブラウザでアクセスすれば、
以降はPC不要で、どこからでも（同じWi-Fiでなくても）このシミュレーターを
利用できます。「10. ホーム画面に追加する方法」の手順で、
このURLをホーム画面に追加しておくと、アプリのようにワンタップで開けて便利です。

### 12-8. うまくいかないときは

- アップロード後にStreamlit Cloud側で赤い「Error」が表示された場合、
  ほとんどは `requirements.txt` が正しくアップロードされていない、
  または `.streamlit/config.toml` のパスが誤っていることが原因です。
  リポジトリのファイル一覧を開いて、フォルダ構成が
  「2. フォルダ構成」の表と一致しているか確認してください。
- ログ（エラー内容）はStreamlit Cloudのアプリ管理画面の「Manage app」→
  ログ表示エリアでスマホからでも確認できます。
8. [Streamlit Community Cloudへの公開手順](#8-streamlit-community-cloudへの公開手順)
9. [環境変数・Secretsの扱い](#9-環境変数secretsの扱い)
10. [ホーム画面に追加する方法（アプリのように使う）](#10-ホーム画面に追加する方法アプリのように使う)
11. [注意事項・免責事項](#11-注意事項免責事項)
12. [スマホだけで完結させる場合（PC不要）](#12-スマホだけで完結させる場合pc不要)

---

## 1. 全体設計

```
[data_provider.py]  無料データ(yfinance)から日足OHLCVを取得
        │
[indicators.py]     SMA/RSI/MACD/ATR/出来高平均などのテクニカル指標を計算
        │
[strategy.py]        買い条件(6項目)・売り条件(テクニカル部分)を判定
        │
[risk_manager.py]    RiskSettings（画面から変更可能なリスクパラメータ）に基づき、
                      ポジションサイズ計算・損切り/利確/トレーリング・
                      1日の損失上限・最大ドローダウン停止・資金不足判定を行う
        │
[backtester.py]      日々のシグナル確定→翌営業日始値で約定、というルールで
                      Look-ahead biasを排除しながらバックテストを実行。
                      Buy&Holdとの比較、診断情報、各種成績指標の計算も行う
        │
[portfolio.py]       現金・保有ポジション・取引履歴・資産推移を管理
                      （実現損益は購入時・売却時の手数料を差し引いたネット損益）
        │
[trade_logger.py]    取引履歴をCSV出力
        │
[dashboard.py]       Streamlit UI部品（レスポンシブなカードグリッド・
                      スマホ対応テーブル・グラフ設定など、表示専用）
        │
[main.py]            アプリ全体の画面構成・設定の相互同期・表示モード切替
```

**計算ロジックとUIの分離**: `backtester.py` / `risk_manager.py` / `portfolio.py` /
`strategy.py` / `indicators.py` / `data_provider.py` / `trade_logger.py` は
バックテストの計算そのものを担うモジュールで、スマホ対応の際も一切変更していません。
UI（表示・操作性）に関する変更は `dashboard.py` と `main.py` のみに閉じています。

## 2. フォルダ構成

```
jp_stock_sim/
├── main.py                    # Streamlitアプリのエントリーポイント（画面構成・設定同期）
├── config.py                   # 設定値（初期資金・リスク管理パラメータ・銘柄リスト・Secrets読込）
├── data_provider.py             # 株価データ取得（yfinance、将来API差し替え可能）
├── indicators.py                  # テクニカル指標計算
├── strategy.py                     # 売買シグナル判定
├── risk_manager.py                  # リスク管理（RiskSettings・ポジションサイズ・損切り等）
├── backtester.py                     # バックテストエンジン
├── portfolio.py                       # 資産・ポジション・取引履歴管理
├── trade_logger.py                     # 取引履歴CSV出力
├── dashboard.py                         # Streamlit UI部品（レスポンシブ対応）
├── requirements.txt
├── .env.example                         # ローカル用の環境変数サンプル
├── .streamlit/
│   ├── config.toml                       # サーバー・テーマ設定
│   └── secrets.toml.example               # Streamlit Cloud用Secretsのサンプル
├── .gitignore
└── README.md
```

## 3. 必要ライブラリ

`requirements.txt` に実際に使用しているライブラリをすべて記載しています。

- `streamlit` — Webアプリのフレームワーク
- `pandas` / `numpy` — データ処理・数値計算
- `yfinance` — 無料の株価データ取得
- `plotly` — 資産推移グラフ
- `python-dotenv` — ローカル実行時の `.env` 読み込み

バージョンは下限のみを指定しています（上限固定にすると、クラウド側の
クリーンビルドで将来的にインストールが失敗しやすくなるため）。理由の詳細は
`requirements.txt` 内のコメントを参照してください。

---

## 4. 実装済みの主な機能

- 対象銘柄（初期登録・画面から追加/削除可能、東証コード10銘柄）
- シンプルなトレンドフォロー戦略（SMA/RSI/MACD/出来高による買い条件、
  デッドクロス・損切り・利確・トレーリングストップによる売り条件）
- リスク管理（1取引最大リスク・1銘柄最大投資比率・最大同時保有数・損切り幅を
  画面から変更可能。手数料・スリッページを考慮したポジションサイズ計算）
- Look-ahead biasを排除したバックテスト（シグナル確定の翌営業日始値で約定）
- 手数料・スリッページ・100株単位・購入可能資金・同時保有数を考慮
- ネット損益（購入時・売却時手数料を差し引いた実現損益）に基づく成績集計
- Buy & Holdとの比較（投資済み金額・未使用現金・実購入銘柄数も表示）
- 資金不足で購入できなかった記録のログ表示
- 「戦略が悪いのか／資金不足なのか」を切り分ける診断セクション
- 取引履歴のCSVダウンロード

---

## 5. スマホ対応・UIについて

- **レスポンシブなカード表示**: ダッシュボードの指標・使用リスク設定値・
  診断情報・Buy&Hold内訳は、CSS Grid（`auto-fit, minmax()`）による
  自動折り返しカードで表示しています。JavaScriptによる端末判定を使わず、
  画面幅が狭くなれば自動的に1〜2列に折り返され、PCでは3〜6列程度で表示されます。
- **設定の二重管理防止**: バックテスト期間・リスクパラメータ・対象銘柄は、
  PC向けの「サイドバー」とスマホ向けの「メイン画面上部のexpander」の
  両方から操作できますが、`st.session_state` のコールバックで常に相互同期しており、
  どちらを操作しても同じ設定として扱われます（`main.py` の `_linked_slider` 参照）。
- **タップしやすいボタン・入力欄**: 主要ボタンは横幅いっぱい・大きめのフォント・
  タップ領域を確保するCSSを適用しています。「バックテスト実行」ボタンは
  特に目立つスタイルにしています。
- **グラフのスマホ対応**: `width="stretch"` を維持しつつ、「かんたん表示」時は
  グラフの高さと凡例フォントを抑えます。ピンチズーム・横スクロールを
  妨げないPlotly設定（`scrollZoom: True` 等）を使用しています。
- **テーブルのスマホ対応**: 重要な列（日時・銘柄コード・売買・損益など）を
  先頭に配置し、Streamlit標準の横スクロールに委ねることで、列がはみ出しても
  表が崩れないようにしています。「現在の買いシグナル」はカード形式で、
  銘柄・総合判定・購入可能株数・必要最低購入金額・資金状況を最優先表示し、
  SMA/RSI/MACD/出来高の内訳は折りたたみ（expander）に格納しています。
- **かんたん表示 / 詳細表示**: 画面上部のトグルで切り替えられます。
  かんたん表示では「総資産・利益率・最大ドローダウン・資産推移グラフ・
  現在の買いシグナル」のみを表示し、詳細表示ではすべての指標・タブ
  （保有銘柄・売買履歴・銘柄ごとの成績・資金不足ログ等）を表示します。
  端末の自動判定は行っていません（不安定になりやすいため、手動切り替えとしています）。

---

## 6. PCでの起動方法（Windows）

### 6-1. Pythonのインストール

1. [Python公式サイト](https://www.python.org/downloads/) から Python 3.10〜3.12 系のインストーラをダウンロード
2. インストーラ起動時、**「Add python.exe to PATH」に必ずチェック**を入れてから「Install Now」
3. インストール後、コマンドプロンプト（`Win + R` → `cmd` → Enter）で確認

```bat
python --version
```

と入力し、`Python 3.x.x` と表示されればOKです。

### 6-2. アプリのファイルを配置

このフォルダ（`jp_stock_sim`）を、例えば `C:\Users\あなたの名前\jp_stock_sim` に配置してください。

### 6-3. 仮想環境の作成（推奨）

```bat
cd C:\Users\あなたの名前\jp_stock_sim
python -m venv venv
venv\Scripts\activate
```

`(venv)` が行頭に表示されれば仮想環境が有効になっています。

### 6-4. 必要ライブラリのインストール

```bat
pip install -r requirements.txt
```

エラーが出た場合は、先に以下を実行してから再度お試しください。

```bat
python -m pip install --upgrade pip
```

### 6-5. .envファイルの準備（今回のMVPでは必須ではありません）

```bat
copy .env.example .env
```

将来証券会社APIと接続する際に使用する設定です。今回は空のままで問題ありません。

### 6-6. Streamlitアプリの起動

```bat
streamlit run main.py
```

自動的にブラウザが起動し、`http://localhost:8501` で
「日本株 自動売買シミュレーター」の画面が表示されます。

### 6-7. アプリの終了

コマンドプロンプトで `Ctrl + C` を押すとアプリが停止します。

---

## 7. スマートフォンから使う方法（同一Wi-Fi内）

PCとスマートフォンが**同じWi-Fiに接続されている**必要があります。

### 7-1. PC側の準備

1. 上記「6. PCでの起動方法」の手順で `streamlit run main.py` を実行します。
2. コマンドプロンプトに表示される起動ログを確認します。

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

`Network URL`（`http://192.168.x.x:8501` のような形式）がスマホからアクセスするURLです。

3. Windowsの「ファイアウォールでこのアプリの通信を許可しますか？」という
   確認ダイアログが出た場合は「アクセスを許可する」を選択してください。
   （プライベートネットワークのみ許可すれば十分です）

### 7-2. スマートフォン側の操作

1. スマートフォンをPCと同じWi-Fiに接続します。
2. ブラウザ（Safari / Chrome等）を開き、`Network URL` に表示されたアドレス
   （例: `http://192.168.1.23:8501`）を入力してアクセスします。
3. 画面上部の「表示モード」を「かんたん表示」にすると、必要最小限の情報のみが表示されます。
4. 「⚙️ バックテスト設定」のexpanderをタップして開き、期間・リスクパラメータ・
   対象銘柄を設定して「🚀 バックテスト実行」をタップしてください。

うまく接続できない場合、PC側のセキュリティソフトやファイアウォールが
通信をブロックしている可能性があります。その場合は一時的に許可設定を確認してください。

---

## 8. Streamlit Community Cloudへの公開手順

### 8-1. GitHubへの配置手順

1. [GitHub](https://github.com/) のアカウントを作成（未作成の場合）。
2. 新しいリポジトリを作成します（例: `jp-stock-sim`）。Public / Privateどちらでも構いません。
3. このフォルダ（`jp_stock_sim`）の中身一式をリポジトリにアップロードします。
   - GitHub Desktop を使う場合: リポジトリをクローン → フォルダの中身をコピー → コミット → プッシュ
   - コマンドラインを使う場合の例:

```bat
cd C:\Users\あなたの名前\jp_stock_sim
git init
git add .
git commit -m "Initial commit: 日本株自動売買シミュレーター"
git branch -M main
git remote add origin https://github.com/あなたのユーザー名/jp-stock-sim.git
git push -u origin main
```

   **`.env` や `.streamlit/secrets.toml` は `.gitignore` に含まれているため、
   誤ってGitHubにアップロードされることはありません。**

### 8-2. Streamlit Community Cloudでのデプロイ

1. [Streamlit Community Cloud](https://streamlit.io/cloud) にアクセスし、GitHubアカウントでログインします。
2. 「New app」（新しいアプリを作成）をクリックします。
3. 以下を設定します。
   - **Repository**: 先ほど作成したリポジトリ（例: `あなたのユーザー名/jp-stock-sim`）
   - **Branch**: `main`
   - **Main file path**: `main.py`
4. 「Deploy」をクリックすると、`requirements.txt` に基づいて自動的に環境が構築され、
   数分でアプリが公開されます。
5. 公開されたURL（例: `https://jp-stock-sim-xxxx.streamlit.app`）に、
   PC・スマートフォンどちらからでもアクセスできます。

### 8-3. requirements.txtの使い方

Streamlit Community Cloud は、リポジトリ直下（またはmain.pyと同じ階層）の
`requirements.txt` を自動的に検出し、記載されたライブラリを順にインストールします。
本アプリでは追加のインストール作業は不要です。ローカルでも同じファイルを使うため、
ローカル環境とクラウド環境で依存ライブラリのズレが起きにくい構成になっています。

---

## 9. 環境変数・Secretsの扱い

本アプリは今回のMVPでは証券会社APIキー等を**使用しません**が、
将来の拡張に備えて以下の二段構えの読み込み構造を用意しています（`config.py`参照）。

| 実行環境 | 読み込み元 | 設定ファイル |
|---|---|---|
| ローカル（PC） | `.env`（python-dotenv） | `.env`（`.env.example` をコピーして作成） |
| Streamlit Community Cloud | `st.secrets` | アプリ管理画面の「Settings → Secrets」 |

`config.py` の `_get_secret()` 関数が `st.secrets` を優先的に確認し、
存在しない場合は環境変数（`.env` 経由を含む）にフォールバックします。
どちらの環境でも**APIキー等をソースコードに直書きすることはありません**。

Streamlit Community Cloudでの設定例（アプリ管理画面のSecretsに貼り付ける内容。
`.streamlit/secrets.toml.example` と同じ形式です）:

```toml
BROKER_API_KEY = ""
BROKER_API_SECRET = ""
BROKER_ACCOUNT_ID = ""
```

**`.env` および `.streamlit/secrets.toml` は絶対にGitへコミットしないでください**
（`.gitignore` で既に除外されています）。

---

## 10. ホーム画面に追加する方法（アプリのように使う）

本格的なPWA（Progressive Web App）化は今回のスコープ外ですが、
スマートフォンのブラウザ機能を使って簡易的にアプリのように使うことができます。

**ページタイトル**は `日本株 自動売買シミュレーター`、**アイコン**は 📈（絵文字）を
`st.set_page_config(page_title=..., page_icon="📈", ...)` で設定済みです。

### iPhone（Safari）の場合
1. アプリのURLをSafariで開く
2. 画面下部の「共有」アイコンをタップ
3. 「ホーム画面に追加」を選択
4. 名前を確認して「追加」をタップ

### Android（Chrome）の場合
1. アプリのURLをChromeで開く
2. 右上のメニュー（縦三点アイコン）をタップ
3. 「ホーム画面に追加」または「アプリをインストール」を選択
4. 名前を確認して「追加」をタップ

これにより、ホーム画面のアイコンからブラウザのアドレスバーなしで
アプリのように起動できます（Streamlitアプリ自体はブラウザ上で動作します）。

---

## 11. 注意事項・免責事項

- 株価データはYahoo! Finance（yfinance経由）の無料データを使用しています。
  データの正確性・取得可否は保証されません。取得できない銘柄がある場合は
  画面上に警告が表示されます。
- 本アプリはあくまで**教育・検証目的のシミュレーター**であり、将来の運用成績を
  保証するものではありません。「必ず資産が2倍になる」ことを目的とした
  戦略ではなく、リスクとリターンの関係を検証するためのツールです。
- 実際の株式投資は元本割れのリスクを伴います。投資判断は自己責任で行ってください。
- 本アプリは**ペーパートレード専用**です。`config.py` の `PAPER_MODE = True` が
  安全スイッチとなっており、実口座への発注機能・実売買コードは一切含まれていません。
  公開URLを第三者が開いても、実際の売買が発生することはありません。
- 次のステップとして証券会社APIと接続する場合は、`data_provider.py` の
  `BaseDataProvider` を継承する形で新しいデータ取得クラスを追加し、
  発注処理についても新しいモジュールとして慎重に設計・実装してください。

---

## 12. スマホだけで完結させる場合（PC不要）

**PCを一切使わず、スマートフォン（Android / iPhone）のブラウザだけ**で、
「コード一式の取得 → GitHubへの配置 → Streamlit Community Cloudへの公開 →
アプリの利用」まですべて完結させることができます。
GitHub・Streamlit Community Cloudのサイトはどちらもモバイルブラウザ対応（レスポンシブ）なので、
特別なアプリのインストールは不要です（GitHubの公式アプリも補助的に使えますが必須ではありません）。

### 12-1. 全体の流れ

```
① このチャットからZIPファイルをスマホにダウンロード
        │
② スマホの「ファイル」アプリ（iPhone）/「Files」アプリ（Android）でZIPを展開
        │
③ github.com にスマホのブラウザでログイン（アカウントがなければ作成）
        │
④ 新しいリポジトリを作成
        │
⑤ 展開したファイルをブラウザから「Upload files」でアップロード
        │
⑥ share.streamlit.io（Streamlit Community Cloud）にログインし「New app」で公開
        │
⑦ 公開されたURLにスマホからアクセスして完了
```

### 12-2. ①ZIPファイルのダウンロード

このチャットに添付されている `jp_stock_sim.zip` をタップし、スマホの
ダウンロード（またはファイル）フォルダに保存してください。

### 12-3. ②ZIPファイルの展開

- **iPhone**: 標準の「ファイル」アプリを開く → 「ダウンロード」フォルダの
  `jp_stock_sim.zip` を長押し（または軽くタップ）→ 「展開」を選択すると、
  同じ場所に `jp_stock_sim` フォルダが作成されます。
- **Android**: 標準の「Files」アプリ（または「ファイル」アプリ）を開く →
  ダウンロードフォルダの `jp_stock_sim.zip` をタップ →
  「解凍」「Extract」等のメニューを選択します。
  機種によって「Files」アプリに展開機能がない場合は、Playストアで
  「ZIP Extractor」等の無料アプリを追加してください。

展開すると、`main.py` や `config.py` などのファイル一式と、
隠しフォルダ `.streamlit`（`config.toml` と `secrets.toml.example` を含む）が
展開先フォルダの中に見えるようになります。
**`.streamlit` のような「.（ドット）」から始まるフォルダ・ファイルは、
ファイルアプリの設定で「隠しファイルを表示」をONにしないと見えないことがあります。**
見えない場合でも心配は不要です（後述の方法でカバーできます）。

### 12-4. ③④ GitHubでアカウント作成・リポジトリ作成

1. スマホのブラウザで [https://github.com](https://github.com) を開きます。
2. アカウントがなければ「Sign up」から作成します（メールアドレス・パスワードのみで作成可能）。
3. ログイン後、画面右上の「+」アイコン（またはメニュー）から
   「New repository」を選択します。
4. 以下を入力します。
   - **Repository name**: 例 `jp-stock-sim`
   - **Public / Private**: どちらでも構いません（Publicにすると誰でもコードを閲覧できます）
   - 「Add a README file」はチェックを**外したまま**で構いません
5. 「Create repository」をタップします。

### 12-5. ⑤ ファイルのアップロード

作成したリポジトリの画面で、以下の操作をします。

1. 「Add file」→「Upload files」をタップします。
2. 「choose your files」（またはファイル選択エリア）をタップし、
   ②で展開したフォルダの中身を選択します。
   - スマホの機種・ブラウザによっては**複数ファイルを一度に選択**できます
     （フォルダの中を開いて全選択、またはCtrl/Shiftに相当する長押し選択）。
   - 一度に選択できない場合は、何回かに分けてアップロードしても問題ありません
     （後から追加でアップロードできます）。
3. 通常のファイル（`main.py`、`config.py`、`requirements.txt`、`README.md` など）は
   そのままアップロードすれば、リポジトリの直下に配置されます。
4. **`.streamlit` フォルダの中身（`config.toml`、`secrets.toml.example`）が
   ファイル選択画面に出てこない場合**は、以下のどちらかの方法で対応してください。
   - 方法A: 「Add file」→「Create new file」を選び、ファイル名の入力欄に
     `.streamlit/config.toml` と**スラッシュ区切りで直接入力**します
     （GitHubがこの入力だけで自動的にフォルダを作成してくれます）。
     中身は、このチャットに表示された `config.toml` の内容をコピー＆ペーストしてください。
     同じ手順で `.streamlit/secrets.toml.example` も作成します。
   - 方法B: ZIP展開アプリの設定で「隠しファイルを表示」をONにしてから、
     もう一度アップロード操作をやり直します。
5. 画面下部の「Commit changes」（コミットメッセージ欄）に
   `Initial commit` などと入力し、「Commit changes」ボタンをタップします。

これでリポジトリへのファイル配置が完了です。
リポジトリのトップページに `main.py` や `requirements.txt` が
表示されていれば成功です。

> 💡 **もっと簡単な方法（ファイル数が多くて大変なとき）**:
> ZIPの展開・アップロードが難しい場合は、各ファイルごとに
> 「Add file」→「Create new file」でファイル名を入力し、
> このチャットに表示されているコードをそのままコピー＆ペーストして
> 1つずつ作成する方法でも、まったく同じ結果になります（手間はかかりますが、
> ZIP展開アプリが使えない場合の確実な代替手段です）。

### 12-6. ⑥ Streamlit Community Cloudで公開

1. スマホのブラウザで [https://share.streamlit.io](https://share.streamlit.io) を開きます。
2. 「Continue with GitHub」等でログインします（GitHubアカウントでの認証を許可します）。
3. 「Create app」または「New app」をタップします。
4. 以下を設定します。
   - **Repository**: 先ほど作成したリポジトリ（例 `あなたのユーザー名/jp-stock-sim`）
   - **Branch**: `main`
   - **Main file path**: `main.py`
5. 「Deploy」をタップします。数分待つとビルドが完了し、
   `https://xxxxx.streamlit.app` のような公開URLが発行されます。

Secrets（今回のMVPでは空のままで構いません）を設定する場合は、
アプリ管理画面の「Settings」→「Secrets」からスマホでも入力できます
（内容は `.streamlit/secrets.toml.example` を参照）。

### 12-7. ⑦ 公開されたアプリを使う

発行されたURL（`https://xxxxx.streamlit.app`）にスマホのブラウザでアクセスすれば、
以降はPC不要で、どこからでも（同じWi-Fiでなくても）このシミュレーターを
利用できます。「10. ホーム画面に追加する方法」の手順で、
このURLをホーム画面に追加しておくと、アプリのようにワンタップで開けて便利です。

### 12-8. うまくいかないときは

- アップロード後にStreamlit Cloud側で赤い「Error」が表示された場合、
  ほとんどは `requirements.txt` が正しくアップロードされていない、
  または `.streamlit/config.toml` のパスが誤っていることが原因です。
  リポジトリのファイル一覧を開いて、フォルダ構成が
  「2. フォルダ構成」の表と一致しているか確認してください。
- ログ（エラー内容）はStreamlit Cloudのアプリ管理画面の「Manage app」→
  ログ表示エリアでスマホからでも確認できます。
