"""
&AI QUANTUM EDGE - VIP投資家ウォッチ
VIP投資家のツイートをリアルタイム監視して投資シグナルを生成
"""

import requests, os, json, time
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

TWITTERAPI_KEY = os.environ.get("TWITTERAPI_IO_KEY")
BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
COMMAND_BOT_TOKEN = os.environ.get("QE_COMMAND_BOT_TOKEN")

# VIP監視リスト
VIP_LIST = {
    "elonmusk":     {"name": "イーロン・マスク",  "assets": ["BTC", "DOGE", "TSLA"], "impact": "超高"},
    "CathieWood":   {"name": "キャシー・ウッド",  "assets": ["NVDA", "TSLA", "ARM"], "impact": "高"},
    "naval":        {"name": "Naval Ravikant",    "assets": ["BTC", "ETH"],           "impact": "中"},
    "chamath":      {"name": "Chamath Palihapitiya","assets": ["BTC", "テック株"],    "impact": "中"},
    "WarrenBuffett":{"name": "ウォーレン・バフェット","assets": ["株式市場全般"],     "impact": "超高"},
}

SEEN_FILE = '/Users/mr.k/Projects/and-ai-brain/vip_seen_tweets.json'


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f)


def get_user_tweets(username, count=5):
    """ユーザーの最新ツイートを取得"""
    r = requests.get(
        "https://api.twitterapi.io/twitter/user/last_tweets",
        headers={"X-API-Key": TWITTERAPI_KEY},
        params={"userName": username, "count": count},
        timeout=15
    )
    if r.status_code == 200:
        d = r.json()
        data = d.get("data", {})
        if isinstance(data, dict):
            return data.get("tweets", [])
        return []
    return []


def analyze_tweet_with_claude(tweet_text, username, vip_info):
    """Claudeがツイートの投資的重要度を判断"""
    client = Anthropic()
    
    prompt = f"""あなたは投資シグナル分析AIです。
以下のツイートを分析してください。

【ツイート主】{vip_info['name']} (@{username})
【関連銘柄】{', '.join(vip_info['assets'])}
【影響力】{vip_info['impact']}

【ツイート内容】
{tweet_text}

以下の形式でJSONで回答してください:
{{
  "is_investment_related": true/false,
  "importance": "高/中/低/無関係",
  "affected_assets": ["銘柄1", "銘柄2"],
  "direction": "buy/sell/neutral",
  "summary": "30文字以内の要約",
  "signal": "シグナルの説明（50文字以内）"
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import re
    text = response.content[0].text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"is_investment_related": False, "importance": "無関係"}


def send_vip_alert(username, tweet_text, analysis, vip_info):
    """VIPアラートをTelegramに送信"""
    direction_emoji = "📈" if analysis.get("direction") == "buy" else "📉" if analysis.get("direction") == "sell" else "→"
    importance = analysis.get("importance", "低")
    importance_emoji = "🔴" if importance == "高" else "🟡" if importance == "中" else "🟢"
    
    msg = f"""🔔 *VIP投資家アラート*
━━━━━━━━━━━━━━━

{importance_emoji} 重要度: *{importance}*
👤 @{username}（{vip_info['name']}）
{direction_emoji} 方向: {analysis.get('direction','neutral').upper()}

💬 *ツイート:*
_{tweet_text[:150]}{'...' if len(tweet_text) > 150 else ''}_

📊 *AI分析:*
{analysis.get('signal', '')}

💹 *影響銘柄:*
{' / '.join(analysis.get('affected_assets', vip_info['assets']))}

⏰ {datetime.now().strftime('%m/%d %H:%M')} JST
🦴 &AI QUANTUM EDGE"""

    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )
    return r.status_code == 200


def check_all_vips():
    """全VIPのツイートをチェック"""
    seen = load_seen()
    new_alerts = []
    
    print(f"🔍 VIPウォッチ実行中... {datetime.now().strftime('%H:%M')}")
    
    for username, vip_info in VIP_LIST.items():
        try:
            tweets = get_user_tweets(username, count=3)
            
            if not tweets:
                continue
            
            # 未チェックのツイートを処理
            seen_ids = seen.get(username, [])
            
            for tweet in tweets:
                if not isinstance(tweet, dict):
                    continue
                    
                tweet_id = tweet.get("id", tweet.get("tweet_id", ""))
                tweet_text = tweet.get("text", tweet.get("full_text", ""))
                
                if not tweet_text or tweet_id in seen_ids:
                    continue
                
                # Claude で投資的重要度を判断
                analysis = analyze_tweet_with_claude(tweet_text, username, vip_info)
                
                if analysis.get("is_investment_related") and analysis.get("importance") in ["高", "中"]:
                    print(f"  ✅ {username}: 重要ツイート発見！({analysis.get('importance')})")
                    sent = send_vip_alert(username, tweet_text, analysis, vip_info)
                    if sent:
                        new_alerts.append({"username": username, "analysis": analysis})
                        print(f"  📱 Telegram通知送信！")
                else:
                    print(f"  → {username}: 通常ツイート（スキップ）")
                
                # 既読に追加
                if username not in seen:
                    seen[username] = []
                if tweet_id:
                    seen[username].append(tweet_id)
                    seen[username] = seen[username][-50:]  # 最新50件のみ保持
                
                time.sleep(1.5)
            
        except Exception as e:
            print(f"  ❌ {username}: エラー {str(e)[:50]}")
        
        time.sleep(2)
    
    save_seen(seen)
    return new_alerts


def get_trends():
    """世界トレンドTop10を取得"""
    r = requests.get(
        "https://api.twitterapi.io/twitter/trends",
        headers={"X-API-Key": TWITTERAPI_KEY},
        params={"woeid": 1},  # woeid=1で世界トレンド
        timeout=10
    )
    if r.status_code == 200:
        trends = r.json().get("trends", [])
        return [t.get("trend", "") for t in trends[:10]]
    return []


def is_investment_trend(trend_name: str) -> bool:
    """トレンドが投資に関連するかを判断"""
    investment_keywords = [
        # 仮想通貨
        "btc", "bitcoin", "eth", "ethereum", "crypto", "defi", "nft", "sol", "xrp", "trx",
        # 株式・市場
        "nasdaq", "dow", "s&p", "sp500", "nikkei", "stocks", "market", "fed", "fomc",
        "earnings", "ipo", "merger", "acquisition",
        # 企業・銘柄
        "nvda", "nvidia", "apple", "tesla", "microsoft", "amazon", "google",
        "aapl", "msft", "amzn", "googl", "meta", "arm", "amd",
        # 経済
        "inflation", "recession", "gdp", "rate", "interest", "economy",
        "インフレ", "景気", "金利", "株価", "仮想通貨", "ビットコイン",
        # iGaming関連
        "casino", "gaming", "bet", "gambling",
        # AI
        "ai", "chatgpt", "openai", "claude", "gemini", "llm",
    ]
    name_lower = trend_name.lower()
    return any(kw in name_lower for kw in investment_keywords)


def get_investment_trends():
    """投資に関連するトレンドのみ取得"""
    r = requests.get(
        "https://api.twitterapi.io/twitter/trends",
        headers={"X-API-Key": TWITTERAPI_KEY},
        params={"woeid": 1},
        timeout=10
    )
    if r.status_code != 200:
        return []
    
    all_trends = r.json().get("trends", [])
    investment_trends = []
    
    for t in all_trends:
        name = t.get("name", "") if isinstance(t, dict) else str(t)
        if is_investment_trend(name):
            investment_trends.append(name)
    
    return investment_trends


def format_vip_section_for_report():
    """毎朝レポート用のVIPセクションを生成（投資関連のみ）"""
    section = ""
    
    # 投資関連トレンドのみ
    inv_trends = get_investment_trends()
    if inv_trends:
        section += "\n━━━━━━━━━━━━━━━\n"
        section += "🔥 *投資関連トレンド*\n"
        for t in inv_trends[:5]:
            section += f"  {t}\n"
    
    return section


if __name__ == "__main__":
    print("🔔 VIP投資家ウォッチ - テスト実行")
    print("=" * 50)
    
    # トレンド取得テスト
    print("\n📊 世界トレンドTop10:")
    trends = get_trends()
    for i, t in enumerate(trends[:10], 1):
        print(f"  {i}. {t}")
    
    print("\n👤 VIP監視対象:")
    for username, info in VIP_LIST.items():
        print(f"  @{username} ({info['name']}) - 影響力: {info['impact']}")
    
    print("\n✅ 設定完了！")
    print("→ 毎時自動チェックはLaunchAgentで設定")
    print("→ 重要ツイートがあればTelegramに即通知")
