# &AI QUANTUM EDGE

> 量子確率モデル × センチメント分析 × 衛星データを融合した、暗号資産・株式向けAI投資シグナルエンジン

## 🎯 概要

量子コンピューティング（Amazon Braket / IBM Quantum）、オンチェーンデータ、マクロインテリジェンスを組み合わせたマルチエージェント投資分析システム。
Hyperliquid・dYdXでのリアル運用（Tier-2）に対応し、Telegramボットで毎日自動シグナルを配信する。
Ray Dalio・Jim Simons・Paul Tudor Jonesの投資哲学をAIで再現。

## ✨ 主な機能

- **量子シグナル生成** — Amazon Braket + IBM Quantumによる確率的価格モデリング
- **マルチエージェント調査** — X/Reddit/ニュース → Claude LLM センチメントスコアリング
- **オンチェーン監視** — Whale Alert・Coinglass・CoinGeckoリアルタイム追跡
- **自動売買** — Hyperliquid / dYdX Tier-2 ポジション管理（10%/トレード、最大5ポジション）
- **予測市場分析** — Polymarket / Kalshiイベント相関シグナル
- **Telegramボット** — コマンド即時応答・日次シグナルレポート自動送信

## 🛠️ 技術スタック

- **フロントエンド:** Next.js（&AI QE ダッシュボード）
- **バックエンド:** Python 3.14+ + Anthropic Claude API + OpenAI
- **量子:** Amazon Braket / IBM Quantum / TimesFM（時系列予測）
- **取引所:** Hyperliquid / dYdX / Polymarket / Kalshi
- **データソース:** yfinance / CoinGecko / Coinglass / Whale Alert / FRED / J-Quants / Tavily
- **インフラ:** Vercel（ダッシュボード）/ Telegram Bot

## 🌐 URL

- **本番ダッシュボード:** Vercel（&AI QE Dashboard）
- **Telegramボット:** @bk_training_en_bot
- **開発:** http://localhost:8000

## 📊 ステータス

🟢 稼働中 — Tier-2リアル運用中（最新シグナル: 2026-04-06 06:30 UTC）

## 🔗 関連プロジェクト

- **統合元:** and-ai-brain（andai-trade-arena・TradingAgents統合）
- **連携先:** &AI AD（市場インサイト提供）、&AI INVEST COURSE（教育コンテンツ連携）

## 📁 プロジェクト構造

```
├── quantum_edge_bot.py      # メインコマンドボット & オーケストレーション
├── brain_collector.py       # データ収集エンジン v1.1
├── auto_trader.py           # Hyperliquid 自動売買
├── daily_research.py        # 日次分析 & 調査ログ
├── market_intelligence.py   # マクロ + 株式スクリーニング
├── prediction_market.py     # Polymarket / Kalshi 統合
├── portfolio_optimizer.py   # ポジションサイジング
├── backtest.py              # バックテスト・戦略検証
├── strategy_explorer.py     # 戦略評価エンジン
├── plugins/
│   ├── crypto_data.py       # 取引所データ
│   ├── macro_data.py        # マクロ指標
│   ├── onchain.py           # オンチェーン分析
│   ├── fundamental.py       # 企業ファンダメンタルズ
│   └── sentiment.py         # NLP センチメント
└── logs/                    # 戦略テストログ
```

## 🚀 開始方法

```bash
# 仮想環境セットアップ
python -m venv venv
source venv/bin/activate

# 依存関係インストール
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .env にAPIキー・ウォレットアドレスを設定

# Telegramボット起動
python quantum_edge_bot.py

# 日次シグナル手動実行
python daily_research.py
```

### 主要環境変数

```env
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
HYPERLIQUID_WALLET=
HYPERLIQUID_PRIVATE_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
COINGECKO_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

---
*BKグループ &AI ブランド / 2026-04-06*
