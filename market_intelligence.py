"""
&AI QUANTUM EDGE - マーケットインテリジェンス統合エンジン
5つのMCPスキルを統合した情報収集基盤

① yfinance-mcp-server → 全世界銘柄データ
② market-snapshot（Fear&Greed + マクロ）
③ Binance-Claw相当（価格閾値監視）
④ Agent Trading Atlas相当（ガバナンス）
⑤ tavily-web-search（設定後に有効化）
"""

import os, json, requests, time
from datetime import datetime
from dotenv import load_dotenv
import yfinance as yf

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")


# ==============================
# ① yfinance-mcp-server 統合
# ==============================

def get_market_snapshot_yfinance(tickers: list = None) -> dict:
    """
    yfinance-mcp-serverと同等の機能
    全世界銘柄の包括的データを取得
    """
    if tickers is None:
        tickers = [
            # 仮想通貨
            "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "TRX-USD", "TON-USD",
            # AI×テック株
            "NVDA", "MSFT", "AMD", "ARM",
            # iGaming
            "LVS", "MLCO", "DKNG",
            # ASEAN
            "SE", "GRAB",
            # 安全資産
            "GC=F",  # Gold
            # インデックス
            "^GSPC",  # S&P500
            "^N225",  # 日経225
        ]

    results = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            hist = t.history(period="5d")

            price = info.last_price or 0
            if len(hist) >= 2:
                prev = hist['Close'].iloc[-2]
                change_pct = (price - prev) / prev * 100 if prev > 0 else 0
                volume_5d = hist['Volume'].mean()
                volume_today = hist['Volume'].iloc[-1] if len(hist) > 0 else 0
                volume_ratio = volume_today / volume_5d if volume_5d > 0 else 1
            else:
                change_pct = 0
                volume_ratio = 1

            results[ticker] = {
                "price": round(price, 6),
                "change_pct": round(change_pct, 2),
                "volume_ratio": round(volume_ratio, 2),
                "market_cap": getattr(info, 'market_cap', 0) or 0,
            }
        except Exception:
            pass

    return results


def screen_stocks(criteria: dict = None) -> list:
    """
    銘柄スクリーニング機能
    criteria例: {"min_change": 1.5, "min_volume_ratio": 1.5}
    """
    if criteria is None:
        criteria = {"min_change": 1.0, "min_volume_ratio": 1.3}

    data = get_market_snapshot_yfinance()
    results = []

    for ticker, info in data.items():
        if (info["change_pct"] >= criteria.get("min_change", 0) and
                info["volume_ratio"] >= criteria.get("min_volume_ratio", 0)):
            results.append({
                "ticker": ticker,
                **info,
                "score": info["change_pct"] * info["volume_ratio"]
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)


# ==============================
# ② market-snapshot（マクロ統合）
# ==============================

def get_macro_snapshot() -> dict:
    """
    Fear&Greed + BTC支配率 + 経済カレンダーを統合取得
    mcp-server-fear-greedと同等
    """
    snapshot = {}

    # Fear & Greed
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=8)
        data = r.json()['data']
        snapshot['fear_greed'] = {
            'value': int(data[0]['value']),
            'label': data[0]['value_classification'],
            '7day_avg': sum(int(d['value']) for d in data) // len(data),
            'trend': 'rising' if int(data[0]['value']) > int(data[-1]['value']) else 'falling'
        }
    except:
        snapshot['fear_greed'] = {'value': 50, 'label': 'Neutral'}

    # BTC支配率
    try:
        cg_key = os.environ.get("COINGECKO_API_KEY", "")
        r2 = requests.get("https://api.coingecko.com/api/v3/global",
            headers={"x-cg-demo-api-key": cg_key}, timeout=8)
        g = r2.json()['data']
        snapshot['btc_dominance'] = round(g['market_cap_percentage']['btc'], 1)
        snapshot['total_market_cap_trillion'] = round(g['total_market_cap']['usd'] / 1e12, 2)
    except:
        snapshot['btc_dominance'] = 50

    # 経済カレンダー（次の重要指標）
    try:
        from advanced_data import get_economic_calendar
        events = get_economic_calendar()
        snapshot['upcoming_events'] = events[:3] if events else []
    except:
        snapshot['upcoming_events'] = []

    return snapshot


# ==============================
# ③ Binance-Claw相当（価格閾値監視）
# ==============================

PRICE_ALERTS_FILE = '/Users/mr.k/Projects/and-ai-brain/price_alerts.json'


def load_price_alerts() -> dict:
    if os.path.exists(PRICE_ALERTS_FILE):
        with open(PRICE_ALERTS_FILE) as f:
            return json.load(f)
    return {}


def save_price_alerts(alerts: dict):
    with open(PRICE_ALERTS_FILE, 'w') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def set_price_alert(ticker: str, threshold: float, direction: str = "above", label: str = ""):
    """
    価格閾値アラートを設定
    direction: "above"（上抜け）or "below"（下抜け）
    """
    alerts = load_price_alerts()
    alert_id = f"{ticker}_{direction}_{threshold}"
    alerts[alert_id] = {
        "ticker": ticker,
        "threshold": threshold,
        "direction": direction,
        "label": label or f"{ticker} {direction} ${threshold}",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "triggered": False
    }
    save_price_alerts(alerts)
    print(f"✅ アラート設定: {ticker} {direction} ${threshold:,.4f}")


def check_price_alerts() -> list:
    """
    全アラートをチェックしてトリガーされたものを返す
    Binance-Clawの価格閾値監視と同等
    """
    alerts = load_price_alerts()
    triggered = []

    # HL価格取得
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    mids = {k: float(v) for k, v in r.json().items()}

    # yfinanceでの価格も取得
    stock_tickers = [a["ticker"] for a in alerts.values()
                     if a["ticker"] not in mids and not a.get("triggered")]
    if stock_tickers:
        yf_data = get_market_snapshot_yfinance(list(set(stock_tickers))[:10])

    for alert_id, alert in alerts.items():
        if alert.get("triggered"):
            continue

        ticker = alert["ticker"]
        threshold = alert["threshold"]
        direction = alert["direction"]

        # 現在価格取得
        current_price = float(mids.get(ticker, 0))
        if current_price == 0:
            yf_ticker = ticker + "-USD" if not ticker.endswith("-USD") else ticker
            current_price = yf_data.get(yf_ticker, {}).get("price", 0) if stock_tickers else 0

        if current_price == 0:
            continue

        # 閾値チェック
        triggered_now = False
        if direction == "above" and current_price >= threshold:
            triggered_now = True
        elif direction == "below" and current_price <= threshold:
            triggered_now = True

        if triggered_now:
            alert["triggered"] = True
            alert["triggered_price"] = current_price
            alert["triggered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            triggered.append(alert)

    save_price_alerts(alerts)

    # トリガーされたアラートをTelegram通知
    for alert in triggered:
        direction_jp = "上抜け" if alert["direction"] == "above" else "下抜け"
        msg = f"""⚡ *価格アラート発動！*

🎯 {alert['ticker']}: {direction_jp}
設定値: ${alert['threshold']:,.4f}
現在値: ${alert['triggered_price']:,.4f}

→ シグナルチェックを開始します！
🦴 &AI QUANTUM EDGE"""
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

    return triggered


# ==============================
# ④ Agent Trading Atlas相当（ガバナンス）
# ==============================

def calculate_fund_metrics() -> dict:
    """
    3ファンドのリスク指標を自動計算
    ATA（Agent Trading Atlas）相当
    """
    from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
    import math

    metrics = {}

    for fund_id in ["fund_1", "fund_2", "fund_3"]:
        fd = load_fund(fund_id)
        cfg = FUNDS[fund_id]
        history = fd.get("history", [])

        if len(history) < 2:
            metrics[fund_id] = {
                "name": cfg["name"],
                "sharpe": None,
                "max_dd": 0,
                "var_95": None,
                "note": "データ蓄積中"
            }
            continue

        # 日次リターン
        returns = [h.get("day_return_pct", 0) / 100 for h in history[1:]]

        if not returns:
            continue

        # シャープレシオ（リスクフリーレート=0と仮定）
        avg_return = sum(returns) / len(returns)
        std_return = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 0
        sharpe = (avg_return / std_return * math.sqrt(252)) if std_return > 0 else None

        # 最大ドローダウン
        peak = INITIAL_CAPITAL
        max_dd = 0
        for h in history:
            val = h.get("value", INITIAL_CAPITAL)
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # VaR (95%): 下位5%のリターン
        sorted_returns = sorted(returns)
        var_idx = max(0, int(len(sorted_returns) * 0.05))
        var_95 = sorted_returns[var_idx] * 100 if sorted_returns else None

        # 現在の資産価値
        current_val = fd.get("portfolio_value", INITIAL_CAPITAL)
        total_return = (current_val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

        metrics[fund_id] = {
            "name": cfg["name"],
            "label": cfg["label"],
            "target_monthly": cfg["target_monthly"],
            "current_value": current_val,
            "total_return_pct": round(total_return, 2),
            "sharpe": round(sharpe, 2) if sharpe else None,
            "max_drawdown": round(max_dd, 2),
            "var_95": round(var_95, 2) if var_95 else None,
            "trade_days": len(history),
            "win_days": fd.get("win_days", 0),
        }

    return metrics


def format_ata_report() -> str:
    """ATA形式のガバナンスレポート"""
    metrics = calculate_fund_metrics()
    lines = ["⚛️ *ファンドガバナンスレポート（ATA）*\n"]

    total_val = 0
    for fund_id, m in metrics.items():
        total_val += m.get("current_value", 10_000_000)
        val = m.get("current_value", 10_000_000)
        pnl_pct = m.get("total_return_pct", 0)
        sharpe = m.get("sharpe")
        max_dd = m.get("max_drawdown", 0)
        var95 = m.get("var_95")
        note = m.get("note", "")

        lines.append(f"{m.get('label','')}: {m.get('name','')} （月利{m.get('target_monthly',0)}%目標）")
        lines.append(f"  残高: ¥{val:,.0f} ({pnl_pct:+.2f}%)")
        if note:
            lines.append(f"  ⏳ {note}")
        else:
            if sharpe is not None:
                lines.append(f"  シャープレシオ: {sharpe:.2f}")
            lines.append(f"  最大DD: {max_dd:.2f}%")
            if var95 is not None:
                lines.append(f"  VaR(95%): {var95:.2f}%")
        lines.append("")

    lines.append(f"合計: ¥{total_val:,.0f}")
    return "\n".join(lines)


# ==============================
# ⑤ tavily-web-search（APIキー設定後有効化）
# ==============================

def search_financial_news(query: str, max_results: int = 5) -> list:
    """
    Tavilyでクリーンな金融ニュースを取得
    APIキー設定が必要: TAVILY_API_KEY
    """
    if not TAVILY_API_KEY:
        return [{"title": "Tavily APIキー未設定", "url": "", "content": "https://tavily.com でAPIキーを取得してください"}]

    try:
        r = requests.post("https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": True,
            }, timeout=15)

        if r.status_code == 200:
            data = r.json()
            results = []
            if data.get("answer"):
                results.append({"title": "AI要約", "content": data["answer"], "url": ""})
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:200],
                    "published": item.get("published_date", ""),
                })
            return results
        return []
    except Exception as e:
        return [{"title": f"エラー: {str(e)[:50]}", "url": "", "content": ""}]


# ==============================
# 統合: 全データを一括取得
# ==============================

def get_full_market_intelligence() -> dict:
    """全5つのデータソースを統合取得"""
    print("🧠 マーケットインテリジェンス収集開始...")

    intelligence = {
        "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M JST"),
    }

    # ① yfinance（全銘柄）
    print("  ① yfinance: 全銘柄スキャン中...")
    intelligence["market_data"] = get_market_snapshot_yfinance()
    print(f"     → {len(intelligence['market_data'])}銘柄取得")

    # ② マクロスナップショット
    print("  ② macro-snapshot: F&G + BTC支配率...")
    intelligence["macro"] = get_macro_snapshot()
    fg = intelligence["macro"].get("fear_greed", {}).get("value", 50)
    print(f"     → F&G: {fg}/100")

    # ③ 価格アラートチェック
    print("  ③ Binance-Claw相当: 価格閾値チェック...")
    triggered = check_price_alerts()
    intelligence["triggered_alerts"] = len(triggered)
    print(f"     → トリガー: {len(triggered)}件")

    # ④ ファンドガバナンス
    print("  ④ ATA: ファンド指標計算...")
    intelligence["fund_metrics"] = calculate_fund_metrics()
    print(f"     → 3ファンド計算完了")

    # ⑤ Tavilyニュース（キーある場合）
    if TAVILY_API_KEY:
        print("  ⑤ Tavily: BTC/ETHニュース取得...")
        intelligence["news"] = search_financial_news("Bitcoin Ethereum crypto market 2026", max_results=3)
    else:
        intelligence["news"] = []
        print("  ⑤ Tavily: APIキー未設定（スキップ）")

    print("✅ 全データ収集完了")
    return intelligence


if __name__ == "__main__":
    print("=" * 60)
    print("⚛️ マーケットインテリジェンス統合テスト")
    print("=" * 60)

    # スクリーニングテスト
    print("\n📈 銘柄スクリーニング（変化率1%以上 + 出来高1.3倍以上）:")
    screened = screen_stocks({"min_change": 1.0, "min_volume_ratio": 1.3})
    for s in screened[:5]:
        print(f"  {s['ticker']}: +{s['change_pct']:.1f}% vol×{s['volume_ratio']:.1f}")

    # マクロスナップショット
    print("\n🌍 マクロスナップショット:")
    macro = get_macro_snapshot()
    fg = macro.get("fear_greed", {})
    print(f"  F&G: {fg.get('value')}/100 ({fg.get('label')})")
    print(f"  BTC支配率: {macro.get('btc_dominance')}%")

    # 価格アラート設定テスト
    print("\n⚡ 価格アラート設定テスト:")
    set_price_alert("BTC", 70000, "above", "BTC 7万ドル突破")
    set_price_alert("BTC", 60000, "below", "BTC 6万ドル割れ")
    set_price_alert("ETH", 2500, "above", "ETH 2500ドル突破")
    print("  アラート3件設定完了")

    # ATA ガバナンスレポート
    print("\n📊 ファンドガバナンス:")
    print(format_ata_report())

    print("\n✅ 全5つの機能テスト完了！")
