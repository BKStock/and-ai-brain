"""
&AI QUANTUM EDGE - Tier1自動売買エンジン v1.0
KK承認: 2026-03-29

エントリー条件（全条件AND）:
  Z値 ≤ -1.5 × NVT ≤ 80 × F&G ≤ 30 × FR ≤ 0.05%（Tier2: KK承認 2026-03-30）
  同銘柄の直近損切りから3日以上

ポジション:
  サイズ: 証拠金の15% / レバ: 2倍 / 最大: 1ポジション（Tier2設定）

損切り: -7% OR Z値が-1.0を上回った時
利確①: Z値が-1.0に戻った時 → 50%（KK確認）
利確②: Z値が0（MA）に戻った時 → 残り（KK確認）

安全装置:
  月間損失-10%で自動停止
  損切り後3日間クールダウン
"""

import os, json, requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
GROUP_ID = "-1003799035163"
GROUP_THREAD = 9  # Hyperliquid自動売買トピック

STATE_FILE = '/Users/mr.k/Projects/and-ai-brain/tier1_state.json'
COINGECKO_KEY = os.environ.get("COINGECKO_API_KEY", "CG-7zNtq5S1sugcNgncGbJqdsY2")

HL_WALLET = "0xe5941eeF19C30A09f05b23b4D512301b3388c9Ed"
HL_API_KEY = os.environ.get("HL_API_PRIVATE_KEY", "")
DYDX_ADDR = "dydx182rjzngn7qzsjunszne4srkr2r2tpplgvc4ct0"

# ルール定数
Z_ENTRY = -1.5   # Tier2: KK承認 2026-03-30
NVT_MAX = 80    # Tier2: KK承認 2026-03-30
FG_MAX = 30
FR_MAX = 0.0005  # 0.05%
COOLDOWN_DAYS = 3
POSITION_SIZE_PCT = 0.15  # 15%（Tier2設定）
LEVERAGE = 2  # Tier2: レバ2倍維持（Tier1と同じ）
STOP_LOSS_PCT = -0.07  # -7%
MONTHLY_MAX_LOSS = -0.10  # -10%


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "positions": {},
        "monthly_pnl": 0.0,
        "month": datetime.now().strftime("%Y-%m"),
        "last_trades": {},
        "stopped": False,
        "trade_log": [],
    }


def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send(msg: str, thread_id: int = None):
    params = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=params, timeout=10)
    if thread_id:
        params2 = {**params, "chat_id": GROUP_ID, "message_thread_id": thread_id}
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=params2, timeout=10)


def get_z_score(ticker_yf: str) -> tuple:
    """Z値と200MAを計算"""
    try:
        prices = yf.Ticker(ticker_yf).history(
            start=(datetime.now()-timedelta(days=250)).strftime('%Y-%m-%d'),
            end=datetime.now().strftime('%Y-%m-%d'))['Close']
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        if len(prices) < 200:
            return None, None, None
        current = float(prices.iloc[-1])
        ma200 = float(prices.rolling(200).mean().iloc[-1])
        std200 = float(prices.rolling(200).std().iloc[-1])
        z = (current - ma200) / std200 if std200 > 0 else 0
        return round(z, 3), round(ma200, 4), round(current, 4)
    except:
        return None, None, None


def get_nvt(coin_id: str) -> float:
    """NVT比率を取得"""
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}",
            headers={"x-cg-demo-api-key": COINGECKO_KEY},
            params={"localization": "false", "tickers": "false",
                    "community_data": "false", "developer_data": "false"},
            timeout=8)
        if r.status_code == 200:
            md = r.json().get("market_data", {})
            mc = md.get("market_cap", {}).get("usd", 0)
            vol = md.get("total_volume", {}).get("usd", 0)
            return mc / vol if vol > 0 else 999
    except:
        pass
    return 999


def get_fg() -> int:
    """Fear&Greed取得"""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        return int(r.json()['data'][0]['value'])
    except:
        return 50


def get_fr(ticker: str) -> float:
    """ファンディングレート取得"""
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"}, timeout=8)
        meta = r.json()[0]['universe']
        ctxs = r.json()[1]
        for i, asset in enumerate(meta):
            if asset['name'] == ticker and i < len(ctxs):
                return float(ctxs[i].get('funding', 0))
    except:
        pass
    return 0.0


def get_hl_balance() -> float:
    """Hyperliquid残高（USDH）取得"""
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState", "user": HL_WALLET}, timeout=8)
        balances = {b['coin']: float(b['total']) for b in r.json().get("balances", [])}
        return balances.get("USDH", 0)
    except:
        return 0


def execute_hl_order(ticker: str, direction: str, size_usd: float, leverage: int = 2) -> bool:
    """
    Hyperliquidで実際に注文を執行
    dYdX APIキーを使用
    """
    try:
        from hyperliquid.exchange import Exchange
        from hyperliquid.utils import constants
        from eth_account import Account

        account = Account.from_key(HL_API_KEY)
        exchange = Exchange(account, constants.MAINNET_API_URL)

        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=8)
        price = float(r.json().get(ticker, 0))
        if price <= 0:
            return False

        size = round(size_usd * leverage / price, 4)
        is_buy = direction == "LONG"

        result = exchange.market_open(ticker, is_buy, size, None, 0.01)
        return result.get("status") == "ok"
    except Exception as e:
        send(f"⚠️ 注文エラー: {str(e)[:100]}")
        return False


def check_and_trade():
    """メインロジック: シグナルチェック → 自動売買"""
    state = load_state()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    this_month = now.strftime("%Y-%m")

    # 月が変わったらリセット
    if state.get("month") != this_month:
        state["monthly_pnl"] = 0.0
        state["month"] = this_month
        state["stopped"] = False
        send("🔄 月次リセット: Tier1システム再開")

    # 月間損失-10%で停止中
    if state.get("stopped"):
        return

    # 対象銘柄
    targets = [
        {"name": "BTC", "yf": "BTC-USD", "cg": "bitcoin", "hl": "BTC"},
        {"name": "ETH", "yf": "ETH-USD", "cg": "ethereum", "hl": "ETH"},
    ]

    fg = get_fg()
    hl_balance = get_hl_balance()

    print(f"チェック: F&G={fg} / HL残高=${hl_balance:,.2f}")

    for t in targets:
        ticker = t["name"]

        # ===== 既存ポジションの管理 =====
        pos = state["positions"].get(ticker)
        if pos and pos.get("status") == "OPEN":
            z, ma200, current = get_z_score(t["yf"])
            if z is None:
                continue

            pnl_pct = (current - pos["entry_price"]) / pos["entry_price"] * 100

            # 損切り判定
            stop_hit = pnl_pct <= STOP_LOSS_PCT * 100
            z_stop = z is not None and z > -1.0  # Z値が-1.0を上回った

            if stop_hit or z_stop:
                reason = "損切り(-7%)" if stop_hit else "Z値回復(-1.0超え)"
                pos["status"] = "CLOSED"
                pos["exit_price"] = current
                pos["exit_pnl_pct"] = round(pnl_pct, 2)
                pos["exit_reason"] = reason
                pos["exit_date"] = today

                state["monthly_pnl"] += pnl_pct
                state["last_trades"][ticker] = today

                msg = (f"🔴 *Tier1 損切り実行*\n\n"
                       f"銘柄: {ticker}\n"
                       f"理由: {reason}\n"
                       f"損益: {pnl_pct:+.2f}%\n"
                       f"月間累計: {state['monthly_pnl']:+.2f}%")
                send(msg, GROUP_THREAD)

                # 月間損失チェック
                if state["monthly_pnl"] <= MONTHLY_MAX_LOSS * 100:
                    state["stopped"] = True
                    send("🚨 *月間損失-10%達成 → Tier1システム停止*\n来月まで待機", GROUP_THREAD)

            # 利確通知（Z値が-1.0/-0.5/0に戻った時）
            elif z >= -0.5 and not pos.get("tp1_notified"):
                pos["tp1_notified"] = True
                msg = (f"🎯 *Tier1 利確①シグナル*\n\n"
                       f"銘柄: {ticker}\n"
                       f"Z値: {z:.2f}（-0.5まで回復）\n"
                       f"現在PnL: {pnl_pct:+.2f}%\n\n"
                       f"50%利確を推奨します\n"
                       f"実行する場合は手動で: app.hyperliquid.xyz")
                send(msg, GROUP_THREAD)

            elif z >= 0 and not pos.get("tp2_notified"):
                pos["tp2_notified"] = True
                msg = (f"🎯 *Tier1 利確②シグナル*\n\n"
                       f"銘柄: {ticker}\n"
                       f"Z値: {z:.2f}（200MAまで回復！）\n"
                       f"現在PnL: {pnl_pct:+.2f}%\n\n"
                       f"残り全利確を推奨します")
                send(msg, GROUP_THREAD)

            save_state(state)
            continue

        # ===== 新規エントリー判定 =====
        # クールダウンチェック
        last_trade = state["last_trades"].get(ticker)
        if last_trade:
            days_since = (now - datetime.strptime(last_trade, "%Y-%m-%d")).days
            if days_since < COOLDOWN_DAYS:
                print(f"  {ticker}: クールダウン中（{days_since}/{COOLDOWN_DAYS}日）")
                continue

        # 既にポジションあり
        if pos and pos.get("status") == "OPEN":
            continue

        # 指標取得
        z, ma200, current = get_z_score(t["yf"])
        if z is None:
            continue

        nvt = get_nvt(t["cg"])
        fr = get_fr(t["hl"])

        print(f"  {ticker}: Z={z:.2f} NVT={nvt:.1f} F&G={fg} FR={fr:.4f}")

        # Tier1判定
        tier1 = (
            z <= Z_ENTRY and
            nvt <= NVT_MAX and
            fg <= FG_MAX and
            fr <= FR_MAX
        )

        if tier1:
            # エントリーサイズ計算
            size_usd = hl_balance * POSITION_SIZE_PCT

            if size_usd < 10:
                print(f"  {ticker}: 残高不足（${size_usd:.2f}）")
                continue

            # 実際に注文
            success = execute_hl_order(ticker, "LONG", size_usd, LEVERAGE)

            if success:
                state["positions"][ticker] = {
                    "status": "OPEN",
                    "ticker": ticker,
                    "direction": "LONG",
                    "entry_price": current,
                    "entry_date": today,
                    "size_usd": round(size_usd, 2),
                    "leverage": LEVERAGE,
                    "z_entry": z,
                    "nvt_entry": nvt,
                    "fg_entry": fg,
                    "stop_price": round(current * (1 + STOP_LOSS_PCT), 4),
                    "tp1_notified": False,
                    "tp2_notified": False,
                }
                save_state(state)

                msg = (f"⚛️ *Tier1 自動エントリー実行！*\n\n"
                       f"銘柄: {ticker} LONG\n"
                       f"価格: ${current:,.4f}\n"
                       f"サイズ: ${size_usd:,.0f}（レバ{LEVERAGE}倍）\n\n"
                       f"📊 シグナル:\n"
                       f"  Z値: {z:.2f} ✅（閾値: {Z_ENTRY}）\n"
                       f"  NVT: {nvt:.1f} ✅（閾値: {NVT_MAX}）\n"
                       f"  F&G: {fg}/100 ✅（閾値: {FG_MAX}）\n"
                       f"  FR: {fr:.4f}% ✅\n\n"
                       f"🛑 損切り: ${current*(1+STOP_LOSS_PCT):,.4f}（-7%）\n"
                       f"🎯 利確①: Z=-1.0時（50%）\n"
                       f"🎯 利確②: Z=0時（残り）\n\n"
                       f"200MA: ${ma200:,.4f}\n"
                       f"🦴 &AI QUANTUM EDGE Tier1")
                send(msg, GROUP_THREAD)

            else:
                # シミュレーションモード（HL実行失敗時）
                msg = (f"🔵 *Tier1 シグナル検知（シミュレーション）*\n\n"
                       f"銘柄: {ticker}\n"
                       f"Z値: {z:.2f} / NVT: {nvt:.1f} / F&G: {fg}\n\n"
                       f"実際の注文は手動で実行してください\n"
                       f"app.hyperliquid.xyz\n🦴")
                send(msg, GROUP_THREAD)

        # Tier2通知（エントリーはしないが監視強化）
        elif z <= -1.5 and nvt <= 80 and fg <= 40:
            print(f"  {ticker}: Tier2シグナル（監視中）")
            # Tier2はTelegramに通知のみ（1日1回）
            if state.get(f"tier2_{ticker}_date") != today:
                state[f"tier2_{ticker}_date"] = today
                msg = (f"⚡ *Tier2 監視シグナル*\n\n"
                       f"銘柄: {ticker}\n"
                       f"Z値: {z:.2f} / NVT: {nvt:.1f} / F&G: {fg}\n\n"
                       f"Tier1（Z≤-2.0 かつ NVT≤50 かつ F&G≤30）まであと少し\n"
                       f"監視継続中 🦴")
                send(msg)
                save_state(state)

    print("✅ Tier1チェック完了")


if __name__ == "__main__":
    check_and_trade()
