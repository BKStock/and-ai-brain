"""
&AI QUANTUM EDGE - Hyperliquid接続モジュール
KYCなしで仮想通貨先物取引のシグナル + リアルタイム価格
"""

import requests
from datetime import datetime
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

HL_API = "https://api.hyperliquid.xyz/info"

# Hyperliquidで取引可能なKK対象銘柄
HL_TRADEABLE = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum", 
    "SOL": "Solana",
    "XRP": "Ripple",
    "TRX": "TRON",
    "TON": "Toncoin",
    "DOGE": "Dogecoin",
    "BNB": "BNB",
    "AVAX": "Avalanche",
    "ARB": "Arbitrum",
    "LINK": "Chainlink",
}

# 株式系はdYdX / Synthetixで対応
STOCK_ALTERNATIVES = {
    "NVDA": "https://dydx.exchange/trade/NVDA-USD",
    "MSFT": "https://app.synthetix.io",
    "ARM":  "https://dydx.exchange/trade/ARM-USD",
    "AMD":  "https://dydx.exchange/trade/AMD-USD",
}


def get_hl_prices():
    """Hyperliquidのリアルタイム価格取得"""
    r = requests.post(HL_API, json={"type": "allMids"}, timeout=10)
    if r.status_code == 200:
        return r.json()
    return {}


def get_hl_funding_rates():
    """ファンディングレート取得（先物のコスト指標）"""
    r = requests.post(HL_API, json={"type": "metaAndAssetCtxs"}, timeout=10)
    if r.status_code == 200:
        data = r.json()
        ctxs = data[1] if len(data) > 1 else []
        meta = data[0].get("universe", [])
        
        rates = {}
        for i, asset in enumerate(meta):
            name = asset.get("name", "")
            if name in HL_TRADEABLE and i < len(ctxs):
                ctx = ctxs[i]
                funding = float(ctx.get("funding", 0)) * 100  # %表示
                oi = float(ctx.get("openInterest", 0))
                rates[name] = {
                    "funding_rate": round(funding, 4),
                    "open_interest": round(oi, 0),
                    "funding_label": "🔴 高コスト" if abs(funding) > 0.05 else "🟢 低コスト"
                }
        return rates
    return {}


def format_hl_signal(ticker, signal_type, entry_price, stop_loss, take_profit, confidence):
    """
    取引シグナルをHyperliquidリンク付きでフォーマット
    
    signal_type: "BUY" or "SELL"
    """
    direction = "LONG" if signal_type == "BUY" else "SHORT"
    emoji = "📈" if signal_type == "BUY" else "📉"
    
    # Hyperliquidの取引URLを生成
    if ticker in HL_TRADEABLE:
        trade_url = f"https://app.hyperliquid.xyz/trade/{ticker}"
        platform = "Hyperliquid（KYCなし）"
    elif ticker in STOCK_ALTERNATIVES:
        trade_url = STOCK_ALTERNATIVES[ticker]
        platform = "dYdX（KYCなし）"
    else:
        trade_url = "https://app.hyperliquid.xyz"
        platform = "Hyperliquid"
    
    signal = f"""
{emoji} *&AI QUANTUM EDGE シグナル*
━━━━━━━━━━━━━━━

💹 銘柄: *{ticker}*
方向: *{direction}*
信頼度: *{confidence}*

📊 価格設定:
  エントリー: ${entry_price:,.4f}
  利確目標:   ${take_profit:,.4f} (+{((take_profit/entry_price)-1)*100:.1f}%)
  損切り:     ${stop_loss:,.4f} (-{(1-(stop_loss/entry_price))*100:.1f}%)

🔗 今すぐ取引（KYCなし）:
{platform}
{trade_url}

⏰ {datetime.now().strftime('%m/%d %H:%M')} JST
_※本シグナルは情報提供のみです_"""
    
    return signal


def get_wallet_balance(wallet_address: str):
    """KKのウォレット残高・ポジション取得"""
    r = requests.post(
        HL_API,
        json={"type": "clearinghouseState", "user": wallet_address},
        timeout=10
    )
    if r.status_code != 200:
        return None
    
    d = r.json()
    margin = d.get("marginSummary", {})
    account_value = float(margin.get("accountValue", 0))
    positions = d.get("assetPositions", [])
    
    active_positions = []
    for p in positions:
        pos = p.get("position", {})
        size = float(pos.get("szi", 0))
        if size != 0:
            active_positions.append({
                "coin": pos.get("coin", ""),
                "size": size,
                "entry_price": float(pos.get("entryPx", 0)),
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                "direction": "LONG" if size > 0 else "SHORT"
            })
    
    return {
        "account_value": account_value,
        "positions": active_positions,
        "position_count": len(active_positions)
    }


def get_hl_market_summary():
    """Hyperliquid市場サマリー（レポート用）"""
    import os, requests as req
    prices = get_hl_prices()
    rates = get_hl_funding_rates()
    
    summary = "\n━━━━━━━━━━━━━━━\n"
    summary += "🔵 *Hyperliquid × 💎 dYdX 残高*\n\n"
    
    # HL残高（Unified Account: Spot USDH）
    HL_MAIN = "0xe5941eeF19C30A09f05b23b4D512301b3388c9Ed"
    hl_total = 0.0
    hl_positions = []
    try:
        r = req.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState", "user": HL_MAIN}, timeout=8)
        if r.status_code == 200:
            balances = {b['coin']: float(b['total']) for b in r.json().get("balances", [])}
            usdh = balances.get("USDH", 0)
            sol = balances.get("USOL", 0)
            hype = balances.get("HYPE", 0)
            # 現在価格で換算
            btc_price = float(prices.get("BTC", 0))
            sol_price = float(prices.get("SOL", 0))
            hl_total = usdh + sol * sol_price + hype * 40  # HYPE概算
            summary += f"🔵 Hyperliquid: ${hl_total:,.2f}\n"
            summary += f"   USDH: ${usdh:,.2f} / SOL: {sol:.3f} / HYPE: {hype:.3f}\n"
        # Perpsポジション確認
        r2 = req.post("https://api.hyperliquid.xyz/info",
            json={"type": "clearinghouseState", "user": HL_MAIN}, timeout=8)
        if r2.status_code == 200:
            pos = r2.json().get("assetPositions", [])
            if pos:
                hl_positions = pos
                summary += f"   ポジション: {len(pos)}件\n"
            else:
                summary += f"   ポジション: なし\n"
    except Exception as e:
        summary += f"🔵 Hyperliquid: 取得中...\n"
    
    # dYdX残高
    DYDX_ADDR = "dydx182rjzngn7qzsjunszne4srkr2r2tpplgvc4ct0"
    dydx_total = 0.0
    try:
        r3 = req.get(f"https://indexer.dydx.trade/v4/addresses/{DYDX_ADDR}", timeout=8)
        if r3.status_code == 200:
            subs = r3.json().get("subaccounts", [])
            if subs:
                dydx_total = float(subs[0].get("equity", 0))
                dydx_pos = subs[0].get("openPerpetualPositions", {})
                summary += f"💎 dYdX: ${dydx_total:,.2f} USDC\n"
                summary += f"   ポジション: {len(dydx_pos)}件\n"
    except:
        summary += f"💎 dYdX: 取得中...\n"
    
    # 合計
    grand_total = hl_total + dydx_total
    summary += f"\n💰 *合計証拠金: ${grand_total:,.2f}*\n"
    
    # 価格セクション
    summary += "\n━━━━━━━━━━━━━━━\n"
    summary += "⚡ *Hyperliquid 価格*\n\n"
    for ticker in ["BTC", "ETH", "SOL", "TRX", "XRP"]:
        if ticker in prices:
            price = float(prices[ticker])
            rate_info = rates.get(ticker, {})
            funding = rate_info.get("funding_rate", 0)
            funding_str = f"  FR:{funding:+.4f}%" if funding != 0 else ""
            summary += f"  `{ticker:4s}`: ${price:>12,.4f}{funding_str}\n"
    
    summary += f"\n🔗 HL: app.hyperliquid.xyz | dYdX: dydx.trade"
    return summary


if __name__ == "__main__":
    print("⚡ Hyperliquid 接続テスト\n")
    
    prices = get_hl_prices()
    print("📊 リアルタイム価格:")
    for ticker in list(HL_TRADEABLE.keys())[:8]:
        if ticker in prices:
            print(f"  {ticker}: ${float(prices[ticker]):,.4f}")
    
    print("\n📈 サンプルシグナル:")
    signal = format_hl_signal(
        ticker="BTC",
        signal_type="BUY",
        entry_price=68500,
        stop_loss=65000,
        take_profit=75000,
        confidence="高"
    )
    print(signal)
    
    print("\n" + get_hl_market_summary())
