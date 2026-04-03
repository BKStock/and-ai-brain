"""
&AI QUANTUM EDGE - dYdX自動売買エンジン
dYdX v4 Chain での自動取引
"""

import os, json, requests, time
from datetime import datetime
from eth_account import Account
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

DYDX_PRIVATE_KEY = os.environ.get("DYDX_PRIVATE_KEY")
DYDX_ADDRESS = os.environ.get("DYDX_ADDRESS", "dydx182rjzngn7qzsjunszne4srkr2r2tpplgvc4ct0")
BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")

INDEXER_URL = "https://indexer.dydx.trade/v4"
NODE_URL = "https://dydx-ops-rpc.kingnodes.com"

# 安全設定
POSITION_SIZE_PCT = 0.10   # 残高の10%
MAX_POSITIONS = 3           # 最大3ポジション（dYdXはHLより少なめ）
TAKE_PROFIT_PCT = 0.10      # +10%利確
STOP_LOSS_PCT = 0.05        # -5%損切り


def send_telegram(msg: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )


def get_account_info():
    """dYdX口座情報取得"""
    r = requests.get(f"{INDEXER_URL}/addresses/{DYDX_ADDRESS}", timeout=10)
    if r.status_code == 200:
        subaccounts = r.json().get("subaccounts", [])
        if subaccounts:
            sa = subaccounts[0]
            return {
                "equity": float(sa.get("equity", 0)),
                "free_collateral": float(sa.get("freeCollateral", 0)),
                "positions": sa.get("openPerpetualPositions", {})
            }
    return None


def get_market_price(ticker: str) -> float:
    """dYdXの現在価格取得"""
    market = f"{ticker}-USD"
    r = requests.get(f"{INDEXER_URL}/perpetualMarkets", timeout=10)
    if r.status_code == 200:
        markets = r.json().get("markets", {})
        if market in markets:
            return float(markets[market].get("oraclePrice", 0))
    return 0.0


def get_available_markets():
    """dYdXで取引可能な銘柄一覧"""
    r = requests.get(f"{INDEXER_URL}/perpetualMarkets", timeout=10)
    if r.status_code == 200:
        markets = r.json().get("markets", {})
        return {
            name.replace("-USD", ""): float(data.get("oraclePrice", 0))
            for name, data in markets.items()
            if data.get("status") == "ACTIVE"
        }
    return {}


def format_dydx_section():
    """デイリーレポート用dYdXセクション"""
    info = get_account_info()
    if not info:
        return ""
    
    section = "\n━━━━━━━━━━━━━━━\n"
    section += "💎 *dYdX口座*\n"
    section += f"残高: ${info['equity']:,.2f} USDC\n"
    section += f"利用可能: ${info['free_collateral']:,.2f}\n"
    
    positions = info.get("positions", {})
    if positions:
        section += f"ポジション: {len(positions)}件\n"
        for name, pos in list(positions.items())[:3]:
            size = float(pos.get("size", 0))
            entry = float(pos.get("entryPrice", 0))
            pnl = float(pos.get("unrealizedPnl", 0))
            direction = "LONG" if size > 0 else "SHORT"
            section += f"  {direction} {name}: ${pnl:+.2f}\n"
    else:
        section += "ポジション: なし\n"
    
    section += f"🔗 dydx.trade"
    return section


def check_dydx_signals():
    """dYdXでのシグナルチェック"""
    info = get_account_info()
    if not info or info["equity"] < 10:
        return
    
    account_value = info["equity"]
    position_usd = account_value * POSITION_SIZE_PCT
    
    # モメンタムスコアを取得
    from momentum_engine import get_all_momentum_scores
    scores = get_all_momentum_scores()
    
    # dYdXで取引可能な銘柄を確認
    dydx_markets = get_available_markets()
    
    # 高スコア銘柄でdYdXで取引可能なものを探す
    for score_data in scores[:5]:
        ticker = score_data['name']
        score = score_data['score']
        
        if score >= 75 and ticker in dydx_markets:
            price = dydx_markets[ticker]
            if price > 0:
                send_telegram(f"""⚡ *dYdX シグナル検知*

📈 {ticker}: スコア {score}点
現在価格: ${price:,.4f}
取引可能: dYdX ✅

💰 推奨サイズ: ${position_usd:.0f}
→ dydx.trade で手動確認してください

🦴 &AI QUANTUM EDGE""")
                break


if __name__ == "__main__":
    print("💎 dYdX 自動売買エンジン テスト\n")
    
    info = get_account_info()
    if info:
        print(f"✅ 口座接続成功！")
        print(f"   残高: ${info['equity']:,.2f} USDC")
        print(f"   利用可能: ${info['free_collateral']:,.2f}")
    
    markets = get_available_markets()
    print(f"\n取引可能銘柄: {len(markets)}種類")
    
    # KK対象銘柄との照合
    kk_tickers = ["BTC", "ETH", "SOL", "XRP", "TRX", "TON", "DOGE", "NVDA"]
    print("\nKK対象銘柄:")
    for t in kk_tickers:
        if t in markets:
            print(f"  ✅ {t}: ${markets[t]:,.4f}")
        else:
            print(f"  ❌ {t}: dYdXになし")
    
    print(f"\n✅ dYdX自動売買エンジン 準備完了！")
