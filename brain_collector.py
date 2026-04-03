"""
&AI QUANTUM EDGE - データ収集エンジン v1.1
⚠️ 機密: アルゴリズム・API構成は非公開
"""

from dotenv import load_dotenv
import os
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

import yfinance as yf
import urllib.request
import json
import re
import requests
from datetime import datetime
from anthropic import Anthropic
from prediction_tracker import (
    save_prediction, verify_predictions, 
    format_verification_report, get_accuracy_summary
)
from feedback_tracker import send_feedback_buttons
from momentum_engine import get_all_momentum_scores, format_momentum_section
try:
    from market_intelligence import (
        screen_stocks, get_macro_snapshot,
        check_price_alerts, format_ata_report
    )
    MARKET_INTELLIGENCE_AVAILABLE = True
except:
    MARKET_INTELLIGENCE_AVAILABLE = False

# プラグインインポート（後方互換性のため関数名はそのまま維持）
from plugins.crypto_data import get_fear_greed, get_btc_dominance, get_coinglass_data
from plugins.sentiment import get_reddit_sentiment, get_x_sentiment, get_opencli_data, format_opencli_section
from plugins.onchain import get_whale_alerts, format_whale_section
from plugins.fundamental import quantum_portfolio_optimize
from plugins.macro_data import get_fred_macro, format_macro_section


# データ収集関数群


def get_market_data():
    """Yahoo Financeからリアルタイム価格・リターン・リスクを取得"""
    # &AI QUANTUM EDGE - KK専用12銘柄
    tickers = {
        # ⚡ 仮想通貨（5銘柄）
        'BTC-USD':  'BTC',    # 市場基準
        'ETH-USD':  'ETH',    # DeFi指標
        'TRX-USD':  'TRX',    # KK保有・ASEAN送金
        'SOL-USD':  'SOL',    # 次世代チェーン
        'XRP-USD':  'XRP',    # 送金特化
        # 📈 AI×テック（3銘柄）
        'NVDA':     'NVDA',   # AI半導体王者
        'MSFT':     'MSFT',   # Azure AI/OpenAI
        'ARM':      'ARM',    # スマホ×AI基盤
        # 🎰 iGaming×ASEAN（3銘柄）
        'LVS':      'LVS',    # マカオ×ASEAN指標
        'MLCO':     'MLCO',   # フィリピン×マカオ直結
        'SE':       'SEA',    # ASEAN最大テック
        # 🛡️ 安全資産（1銘柄）
        'GC=F':     'Gold',   # リスクオフ逃避先
    }
    
    results = {}
    for ticker, name in tickers.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period='90d')
            if len(hist) > 10:
                ret   = hist['Close'].pct_change().mean() * 252
                risk  = hist['Close'].pct_change().std() * (252**0.5)
                price = hist['Close'].iloc[-1]
                prev  = hist['Close'].iloc[-2]
                change_24h = (price - prev) / prev * 100
                
                results[name] = {
                    'ticker':    ticker,
                    'price':     round(price, 2),
                    'return':    round(ret, 4),
                    'risk':      round(risk, 4),
                    'sharpe':    round(ret/risk, 3) if risk > 0 else 0,
                    'change_24h':round(change_24h, 2),
                }
        except Exception as e:
            pass
    
    return results


# get_reddit_sentiment → plugins.sentiment に移動
# get_x_sentiment → plugins.sentiment に移動


def analyze_sentiment_with_claude(posts, market_data):
    """Claudeで感情分析 + 投資シグナルを生成"""
    client = Anthropic()
    
    # 上位投稿をまとめる
    top_posts = sorted(posts, key=lambda x: x['score'], reverse=True)[:15]
    posts_text = "\n".join([f"[{p['score']}↑] {p['title']}" for p in top_posts])
    
    # 市場データをまとめる
    market_text = "\n".join([
        f"{name}: {d['change_24h']:+.2f}% (年率リターン{d['return']*100:.1f}%, リスク{d['risk']*100:.1f}%)"
        for name, d in market_data.items()
    ])
    
    prompt = f"""あなたは&AI BRAINの感情分析エンジンです。
以下のRedditの投資コミュニティ投稿と市場データを分析してください。

# 【市場データ（リアルタイム）】
# {market_text}

# 【Reddit上位投稿（今日）】
# {posts_text}

以下の形式でJSONで回答してください:
# {{
#   "world_economy_score": -100から100の整数（全体的な市場センチメント）,
#   "status": "リスクオン" または "中立" または "リスクオフ",
#   "key_signals": ["重要シグナル1", "重要シグナル2", "重要シグナル3"],
#   "sentiment_by_asset": {{
    "BTC": {{"score": 0-10, "trend": "up/neutral/down", "reason": "理由"}},
    "ETH": {{"score": 0-10, "trend": "up/neutral/down", "reason": "理由"}},
    "NVDA": {{"score": 0-10, "trend": "up/neutral/down", "reason": "理由"}},
    "Gold": {{"score": 0-10, "trend": "up/neutral/down", "reason": "理由"}}
#   }},
#   "prediction_48h": {{
    "BTC":  {{"range": "+X〜+Y%", "probability": 整数}},
    "Gold": {{"range": "+X〜+Y%", "probability": 整数}}
#   }},
#   "summary": "3行以内の総括コメント"
# }}"""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = response.content[0].text
    # JSONを抽出
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return None


# quantum_portfolio_optimize → plugins.fundamental に移動


# # ========================================
# # メインレポート生成
# # ========================================

def generate_brain_report():
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    print(f"⚛️ &AI BRAIN データ収集開始... {now}")
    
    # 1. 市場データ取得
    print("  📈 Yahoo Finance から価格データ取得中...")
    market_data = get_market_data()
    print(f"  → {len(market_data)}銘柄取得完了")
    
    # 1.1 FREDマクロ経済指標
    print("  📉 FREDマクロ指標取得中...")
    try:
        macro_data = get_fred_macro()
        print(f"  → {len([v for v in macro_data.values() if v.get('value')])}指標取得完了")
    except Exception:
        macro_data = {}
        print("  → FREDデータ取得スキップ")

    # 1.2 高度投資データ（経済カレンダー + Deribit IV）
    print("  📅 経済カレンダー + オプションIV取得中...")
    try:
        from advanced_data import get_all_advanced_data, format_advanced_section
        advanced = get_all_advanced_data()
    except:
        advanced = {}
    
    # 1.2 Hyperliquidリアルタイム価格（KYCなし取引所）
    try:
        from hyperliquid_connector import get_hl_prices, get_hl_market_summary
        hl_prices = get_hl_prices()
    except:
        hl_prices = {}
    
    # 1.5 衛星気候データ取得（NASA POWER）
    print("  🛰️ NASA衛星気候データ取得中...")
    try:
        from satellite_collector import get_climate_signals, calculate_climate_economy_score, format_climate_section
        climate_signals = get_climate_signals()
        climate_score, climate_key_signals = calculate_climate_economy_score(climate_signals)
        print(f"  → 気候スコア補正: {climate_score:+.1f}")
    except Exception as e:
        climate_signals = {}
        climate_score = 0
        climate_key_signals = []
        print(f"  → 衛星データ取得スキップ")
    
    # 2. Reddit感情データ取得
    print("  🧬 Reddit から投稿収集中...")
    posts = get_reddit_sentiment()
    print(f"  → {len(posts)}件の投稿収集完了")
    
    # 2.5 X(Twitter)リアル感情スコア
    print("  🐦 X(Twitter) リアル感情スコア取得中...")
    x_sentiment = get_x_sentiment()
    print(f"  → {len(x_sentiment)}銘柄のXデータ取得完了")
    
    # 3. Claude感情分析
    print("  🤖 Claude で感情分析中...")
    sentiment = analyze_sentiment_with_claude(posts, market_data)
    
    # 3.5 モメンタムスコア計算
    print("  🔥 モメンタムスコア計算中...")
    momentum_scores = get_all_momentum_scores()
    
    # 4. 量子ポートフォリオ最適化
    portfolio_balanced = quantum_portfolio_optimize(market_data, 0.5, sentiment)
    portfolio_aggressive = quantum_portfolio_optimize(market_data, 0.2, sentiment)
    portfolio_safe = quantum_portfolio_optimize(market_data, 0.8, sentiment)
    
    # 5. レポート構築
    econ_score = sentiment.get('world_economy_score', 0) if sentiment else 0
    status = sentiment.get('status', '中立') if sentiment else '中立'
    status_emoji = "🟢" if econ_score > 20 else "🟡" if econ_score > -20 else "🔴"
    
    report = {
        'timestamp': now,
        'economy_score': econ_score,
        'status': status,
        'market_data': market_data,
        'sentiment': sentiment,
        'portfolios': {
            'aggressive': portfolio_aggressive,
            'balanced':   portfolio_balanced,
            'safe':       portfolio_safe
        }
    }
    
    # 6. Telegram用メッセージ作成
    msg = f"""⚛️ *&AI BRAIN デイリーレポート*
# {now} JST

# ━━━━━━━━━━━━━━━
# 🌍 *世界経済スコア: {econ_score:+d}*
# {status_emoji} {status}
# """
    
    # Fear & Greed + BTC支配率 追가
    try:
        fg = get_fear_greed()
        dom = get_btc_dominance()
        if fg or dom:
            msg += "\n━━━━━━━━━━━━━━━\n"
            msg += "🧠 *マーケット体温計*\n"
            if fg:
                msg += f"😱 Fear&Greed: *{fg['score']}/100* {fg['signal']}\n"
            if dom:
                msg += f"₿ BTC支配率: *{dom['btc_dominance']}%* {dom['season']}\n"
                msg += f"🌍 市場時価総額: ${dom['total_market_cap_trillion']}兆\n"
    except:
        pass
    
    # FREDマクロセクション追加
    if macro_data:
        msg += format_macro_section(macro_data)

    # モメンタムセクション追加
    msg += "\n" + format_momentum_section(momentum_scores)
    
    # 高度データセクション追加
    if advanced:
        try:
            from advanced_data import format_advanced_section
            msg += format_advanced_section(advanced)
        except:
            pass
    
    # 衛星気候セクション追加
    if climate_signals:
        from satellite_collector import format_climate_section
        msg += format_climate_section(climate_signals)
    
    if sentiment and 'key_signals' in sentiment:
        for sig in sentiment['key_signals'][:3]:
            msg += f"  • {sig}\n"
    
    msg += f"""
# ━━━━━━━━━━━━━━━
# 📈 *リアルタイム価格*
# """
    for name, d in list(market_data.items())[:6]:
        arrow = "▲" if d['change_24h'] > 0 else "▼"
        msg += f"  {name}: ${d['price']:,} ({d['change_24h']:+.1f}% {arrow})\n"
    
    msg += f"""
# ━━━━━━━━━━━━━━━
# ⚛️ *量子ポートフォリオ（標準型）*
# """
    for ticker, pct in sorted(portfolio_balanced.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(pct / 10)
        msg += f"  {ticker}: {pct}% {bar}\n"
    
    if sentiment and 'sentiment_by_asset' in sentiment:
        msg += f"""
# ━━━━━━━━━━━━━━━
# 📊 *AI感情スコア*
# """
        for asset, data in sentiment['sentiment_by_asset'].items():
            trend = "▲" if data['trend'] == 'up' else "▼" if data['trend'] == 'down' else "→"
            # Xリアルスコアがあれば併記
            x_data = x_sentiment.get(asset, {})
            x_str = f"  🐦X:{x_data['score']}/10" if x_data else ""
            msg += f"  {asset}: {data['score']}/10 {trend}{x_str}\n"
    
    if sentiment and 'prediction_48h' in sentiment:
        msg += f"""
# ━━━━━━━━━━━━━━━
# 🎯 *48時間予測（量子AI）*
# """
        for asset, pred in sentiment['prediction_48h'].items():
            msg += f"  📈 {asset}: {pred['range']} (確率{pred['probability']}%)\n"
    
    if sentiment and 'summary' in sentiment:
        msg += f"""
# ━━━━━━━━━━━━━━━
# 💡 *AIサマリー*
# {sentiment['summary']}
# """
    
    # Hyperliquidセクション追加
    try:
        from hyperliquid_connector import get_hl_market_summary
        msg += get_hl_market_summary()
    except:
        pass
    
    msg += "\n🦴 *&AI QUANTUM EDGE* | Real Data × Quantum AI × Hyperliquid"
    
    # ========================================
    # 予測追跡: 前回の予測を検証
    # ========================================
    current_prices = {name: d['price'] for name, d in market_data.items()}
    
    # 前回予測の検証
    verified = verify_predictions(current_prices)
    accuracy = get_accuracy_summary()
    
    # 検証結果をレポートに追加
    if verified:
        verification_section = format_verification_report(verified, 
            {'total': accuracy['total'], 'correct': accuracy['correct']})
        msg += verification_section
    elif accuracy['total'] > 0:
        msg += f"""
# ━━━━━━━━━━━━━━━
# 🎯 *予測精度（累計）*
# {accuracy['message']}
# （検証待ち予測あり）
# """
    
    # 今日の予測を保存（明日検証用）
    if sentiment and 'prediction_48h' in sentiment:
        save_prediction(now, sentiment['prediction_48h'], current_prices)
    
    # デモファンド更新
    try:
        from demo_fund import update_portfolio, format_fund_report
        current_prices = {name: d['price'] for name, d in market_data.items()}
        fund_data, day_ret, total_ret = update_portfolio(portfolio_balanced, market_data)
        fund_report = format_fund_report()
        msg += fund_report
    except Exception as e:
        pass
    
    # フィードバックボタンを送信
    send_feedback_buttons(now[:10])
    
    # JSONも保存
    with open('/Users/mr.k/Projects/and-ai-brain/latest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    
    return msg, report


def send_to_telegram(message, bot_token, chat_id):
    """Telegramに送信"""
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    })
    return resp.status_code == 200


if __name__ == "__main__":
    import os
    
    BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
    CHAT_ID   = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
    
    msg, report = generate_brain_report()
    
    # ターミナルに表示
    print("\n" + "="*55)
    print(msg)
    print("="*55)
    
    # Telegramに送信
    success = send_to_telegram(msg, BOT_TOKEN, CHAT_ID)
    print(f"\n{'✅ Telegram送信成功！' if success else '❌ 送信失敗'}")
    print("✅ latest_report.json 保存完了")


# 上記の関数は全て plugins/ に移動済み
# get_fear_greed      → plugins.crypto_data
# get_btc_dominance   → plugins.crypto_data
# get_coinglass_data  → plugins.crypto_data
# get_opencli_data    → plugins.sentiment
# format_opencli_section → plugins.sentiment
# get_whale_alerts    → plugins.onchain
# format_whale_section → plugins.onchain
