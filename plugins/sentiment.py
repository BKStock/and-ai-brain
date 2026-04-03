"""
&AI BRAIN - センチメントデータプラグイン
Reddit / X(Twitter) / HackerNews
"""

import os
import json
import time
import urllib.request
import requests
from plugins import DataPlugin


class SentimentPlugin(DataPlugin):
    """ソーシャルセンチメントプラグイン"""

    def fetch(self) -> list[dict]:
        records = []

        # Reddit
        posts = get_reddit_sentiment()
        if posts:
            records.append(self._make_record(
                ticker="MARKET",
                value=float(len(posts)),
                source="reddit",
                category="sentiment",
                confidence=0.7,
                metadata={"post_count": len(posts)},
            ))

        # X(Twitter)
        x_scores = get_x_sentiment()
        for ticker, data in x_scores.items():
            records.append(self._make_record(
                ticker=ticker,
                value=float(data["score"]),
                source="twitter",
                category="sentiment",
                confidence=0.8,
                metadata=data,
            ))

        return records


# ========================================
# 個別取得関数（後方互換性のため維持）
# ========================================

def get_reddit_sentiment() -> list[dict]:
    """Reddit r/investing / r/bitcoin から感情スコアを算出"""
    subreddits = ["investing", "Bitcoin", "wallstreetbets"]
    all_posts = []

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            req = urllib.request.Request(
                url, headers={"User-Agent": "AndAIBrain/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())

            for post in data["data"]["children"]:
                p = post["data"]
                all_posts.append({
                    "title": p["title"],
                    "score": p["score"],
                    "subreddit": sub,
                })
        except Exception:
            pass

    return all_posts


def get_x_sentiment() -> dict:
    """twitterapi.io からリアルXデータの感情スコアを取得"""
    api_key = os.environ.get("TWITTERAPI_IO_KEY", "")
    if not api_key:
        return {}

    tickers = ["BTC", "ETH", "NVDA", "SOL", "XRP", "Gold"]
    positive = ["bullish", "moon", "pump", "buy", "up", "gain", "🚀", "🟢", "ATH", "long", "hodl"]
    negative = ["bearish", "dump", "sell", "down", "crash", "loss", "😱", "🔴", "rekt", "short"]

    scores = {}
    for ticker in tickers:
        for attempt in range(2):
            try:
                url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
                params = {"query": f"${ticker}", "queryType": "Latest", "count": 20}
                r = requests.get(
                    url,
                    headers={"X-API-Key": api_key},
                    params=params,
                    timeout=15,
                )

                if r.status_code == 200:
                    tweets = r.json().get("tweets", [])
                    pos = sum(
                        1 for t in tweets for w in positive
                        if w.lower() in t.get("text", "").lower()
                    )
                    neg = sum(
                        1 for t in tweets for w in negative
                        if w.lower() in t.get("text", "").lower()
                    )
                    total = pos + neg
                    score = round((pos / total * 10) if total > 0 else 5.0, 1)
                    scores[ticker] = {
                        "score": score,
                        "trend": "up" if score > 5.5 else "down" if score < 4.5 else "neutral",
                        "tweet_count": len(tweets),
                        "source": "X(Twitter)",
                    }
                    break
                time.sleep(2)
            except Exception:
                time.sleep(3)
        time.sleep(1.0)

    return scores


def get_opencli_data() -> dict:
    """opencli-rs でHackerNewsのAI・投資・テックニュースを取得"""
    import subprocess

    opencli_path = os.path.expanduser("~/.local/bin/opencli-rs")
    results: dict = {"hackernews_top": []}

    investment_kw = [
        "AI", "crypto", "bitcoin", "stock", "market",
        "nvidia", "agent", "LLM", "GPT", "model", "invest",
        "fund", "finance", "fed", "rate", "quantum",
    ]
    try:
        r = subprocess.run(
            [opencli_path, "hackernews", "top"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        title = parts[2].strip()
                        if len(title) > 10 and not any(
                            c in title for c in ["+", "=", "title", "rank"]
                        ):
                            if any(kw.lower() in title.lower() for kw in investment_kw):
                                results["hackernews_top"].append(title[:80])
    except Exception:
        pass

    return results


def format_opencli_section(data: dict) -> str:
    """opencli-rsデータをレポート用にフォーマット"""
    if not data:
        return ""

    hn_items = data.get("hackernews_top", [])
    if not hn_items:
        return ""

    section = "\n━━━━━━━━━━━━━━━\n"
    section += "💻 *テック・投資ニュース（HackerNews）*\n"
    for item in hn_items[:3]:
        section += f"  • {item}\n"

    return section
