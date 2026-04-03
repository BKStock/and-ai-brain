"""
&AI QUANTUM EDGE - A10S戦略（グリッド・ラダー）
10段階ラダーで平均コストを最適化する統計ベース戦略
&AI BRAINのデータで稼働/停止を自動判定
"""

import requests, os, json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ========================================
# A10S設定
# ========================================
A10S_CONFIG = {
    "ticker": "ETH",          # 取引銘柄
    "step_pct": 0.4,          # ラダー間隔（%）
    "max_steps": 10,          # 最大ステップ数
    "step_size_pct": 0.10,    # 1ステップの資金比率（総資産の10%）
    "take_profit_pct": 0.5,   # 利確幅（%）
    "full_tp_pct": 1.2,       # 全利確幅（%）
    "stop_loss_pct": 2.0,     # 損切り幅（平均単価から）
    "max_leverage": 3,        # 最大レバレッジ
    "state_file": "/Users/mr.k/Projects/and-ai-brain/a10s_state.json"
}

MAIN_WALLET = os.environ.get("HL_WALLET", "0xe5941eeF19C30A09f05b23b4D512301b3388c9Ed")
API_KEY = os.environ.get("HL_API_PRIVATE_KEY")
BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")


def load_state():
    """A10S状態を読み込む"""
    if os.path.exists(A10S_CONFIG["state_file"]):
        with open(A10S_CONFIG["state_file"]) as f:
            return json.load(f)
    return {
        "active": False,
        "steps": [],  # 各ステップのエントリー情報
        "avg_price": 0,
        "total_size": 0,
        "current_step": 0,
        "base_price": 0,  # 最初のエントリー価格
        "created_at": None
    }


def save_state(state):
    with open(A10S_CONFIG["state_file"], 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def should_a10s_run():
    """
    &AI BRAINのデータでA10S稼働判定
    稼働OK: True / 停止: False
    """
    reasons_stop = []
    
    try:
        # Fear & Greed チェック
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        fg = int(r.json()['data'][0]['value'])
        if fg < 15:
            reasons_stop.append(f"Fear&Greed低すぎ({fg}/100) → 暴落リスク")
        
        # Deribit IV チェック
        r2 = requests.get(
            "https://www.deribit.com/api/v2/public/get_historical_volatility",
            params={"currency": "BTC"}, timeout=10
        )
        vol_data = r2.json().get("result", [])
        if vol_data and isinstance(vol_data[-1], list):
            iv = float(vol_data[-1][1])
            if iv > 100:
                reasons_stop.append(f"IV超高({iv:.0f}%) → 異常ボラ")
        
        # 経済カレンダーチェック
        r3 = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10
        )
        events = r3.json()
        for e in events:
            if e.get('impact') == 'High' and e.get('country') == 'USD':
                title = e.get('title', '')
                date_str = e.get('date', '')
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    hours = (dt - datetime.now().astimezone()).total_seconds() / 3600
                    if 0 <= hours <= 12:
                        reasons_stop.append(f"重要指標12時間以内: {title}")
                        break
                except:
                    pass
        
        # BTC 24h変化チェック
        import yfinance as yf
        hist = yf.Ticker('BTC-USD').history(period='2d')
        if len(hist) >= 2:
            btc_chg = (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100
            if btc_chg < -5:
                reasons_stop.append(f"BTC急落({btc_chg:.1f}%) → リスクオフ")
        
        # ファンディングレートチェック
        r4 = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"}, timeout=10)
        hl_data = r4.json()
        meta = hl_data[0]['universe']
        ctxs = hl_data[1]
        
        ticker = A10S_CONFIG["ticker"]
        for i, asset in enumerate(meta):
            if asset['name'] == ticker and i < len(ctxs):
                fr = float(ctxs[i].get('funding', 0)) * 100
                if fr > 0.05:
                    reasons_stop.append(f"FR過高({fr:+.4f}%) → ロング過剰")
                break
    
    except Exception as e:
        pass
    
    if reasons_stop:
        return False, reasons_stop
    return True, []


def get_current_price(ticker):
    """現在価格を取得"""
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    return float(r.json().get(ticker, 0))


def calculate_ladder(base_price, account_value):
    """10段階ラダーを計算"""
    steps = []
    step_usd = account_value * A10S_CONFIG["step_size_pct"]
    
    for i in range(A10S_CONFIG["max_steps"]):
        pct_down = i * A10S_CONFIG["step_pct"] / 100
        entry_price = base_price * (1 - pct_down)
        size = step_usd / entry_price
        
        steps.append({
            "step": i + 1,
            "entry_price": round(entry_price, 4),
            "size": round(size, 5),
            "usd": round(step_usd, 2),
            "filled": False
        })
    
    return steps


def get_average_price(state):
    """現在のポジションの平均単価を計算"""
    filled = [s for s in state["steps"] if s.get("filled")]
    if not filled:
        return 0
    
    total_usd = sum(s["usd"] for s in filled)
    total_size = sum(s["size"] for s in filled)
    
    return total_usd / total_size if total_size > 0 else 0


def a10s_check_and_trade():
    """A10Sのメイン実行（1時間ごとに呼び出す）"""
    state = load_state()
    
    # 稼働判定
    can_run, stop_reasons = should_a10s_run()
    
    if not can_run:
        msg = f"⏸️ *A10S 稼働停止*\n\n"
        msg += "理由:\n"
        for r in stop_reasons:
            msg += f"  • {r}\n"
        
        if state["active"]:
            send_telegram(msg)
        return False, stop_reasons
    
    # 現在価格取得
    ticker = A10S_CONFIG["ticker"]
    current_price = get_current_price(ticker)
    
    if current_price == 0:
        return False, ["価格取得失敗"]
    
    # 口座残高取得
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    user_state = info.user_state(MAIN_WALLET)
    account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
    
    if account_value < 10:
        return False, [f"残高不足: ${account_value:.2f}"]
    
    # A10S未開始の場合 → 開始
    if not state["active"]:
        state["active"] = True
        state["base_price"] = current_price
        state["steps"] = calculate_ladder(current_price, account_value)
        state["created_at"] = datetime.now().strftime("%Y/%m/%d %H:%M")
        
        # 1stエントリー実行
        first_step = state["steps"][0]
        account = Account.from_key(API_KEY)
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=MAIN_WALLET)
        
        result = exchange.market_open(ticker, True, first_step["size"])
        if result.get("status") == "ok":
            state["steps"][0]["filled"] = True
            state["current_step"] = 1
            save_state(state)
            
            msg = f"""🎯 *A10S スタート！*
━━━━━━━━━━━━━━━

📈 {ticker} ラダー戦略開始
1st エントリー: ${current_price:,.2f}
サイズ: {first_step['size']} {ticker}
金額: ${first_step['usd']:.0f}

📊 ラダー設定:
  間隔: -{A10S_CONFIG['step_pct']}%/ステップ
  最大: {A10S_CONFIG['max_steps']}ステップ
  利確: +{A10S_CONFIG['take_profit_pct']}%

🦴 &AI QUANTUM EDGE A10S"""
            send_telegram(msg)
            return True, []
    
    # A10S稼働中 → 状態チェック
    avg_price = get_average_price(state)
    if avg_price == 0:
        return True, []
    
    pnl_pct = (current_price - avg_price) / avg_price * 100
    
    # 利確チェック
    if pnl_pct >= A10S_CONFIG["take_profit_pct"]:
        account = Account.from_key(API_KEY)
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=MAIN_WALLET)
        
        result = exchange.market_close(ticker)
        if result.get("status") == "ok":
            filled_count = len([s for s in state["steps"] if s.get("filled")])
            total_usd = sum(s["usd"] for s in state["steps"] if s.get("filled"))
            profit = total_usd * pnl_pct / 100
            
            # 状態リセット
            state = {"active": False, "steps": [], "avg_price": 0,
                    "total_size": 0, "current_step": 0, "base_price": 0}
            save_state(state)
            
            msg = f"""✅ *A10S 利確完了！*
━━━━━━━━━━━━━━━

📈 {ticker} 利確
平均単価: ${avg_price:,.4f}
利確価格: ${current_price:,.4f}
利益: *+{pnl_pct:.2f}%* (+${profit:.2f})
ステップ数: {filled_count}段階

🔄 次のラダーを準備中...
🦴 &AI QUANTUM EDGE A10S"""
            send_telegram(msg)
            return True, ["利確完了"]
    
    # 損切りチェック
    if pnl_pct <= -A10S_CONFIG["stop_loss_pct"]:
        account = Account.from_key(API_KEY)
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=MAIN_WALLET)
        
        exchange.market_close(ticker)
        loss = sum(s["usd"] for s in state["steps"] if s.get("filled")) * abs(pnl_pct) / 100
        
        state = {"active": False, "steps": [], "avg_price": 0,
                "total_size": 0, "current_step": 0, "base_price": 0}
        save_state(state)
        
        msg = f"🛑 *A10S 損切り*\n{ticker} -{abs(pnl_pct):.2f}% (-${loss:.2f})\nラダー再構築待機中..."
        send_telegram(msg)
        return True, ["損切り"]
    
    # 次のステップエントリーチェック
    next_step_idx = None
    for i, step in enumerate(state["steps"]):
        if not step.get("filled"):
            if current_price <= step["entry_price"]:
                next_step_idx = i
                break
    
    if next_step_idx is not None:
        account = Account.from_key(API_KEY)
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=MAIN_WALLET)
        
        step = state["steps"][next_step_idx]
        result = exchange.market_open(ticker, True, step["size"])
        
        if result.get("status") == "ok":
            state["steps"][next_step_idx]["filled"] = True
            state["current_step"] = next_step_idx + 1
            new_avg = get_average_price(state)
            save_state(state)
            
            msg = f"""📉 *A10S Step {next_step_idx + 1} エントリー*
{ticker} ${current_price:,.4f}
新平均単価: ${new_avg:,.4f}
利確目標: ${new_avg * (1 + A10S_CONFIG['take_profit_pct']/100):,.4f}"""
            send_telegram(msg)
    
    return True, []


def get_a10s_status():
    """A10Sの現在状態を取得"""
    state = load_state()
    ticker = A10S_CONFIG["ticker"]
    current_price = get_current_price(ticker)
    
    if not state["active"]:
        can_run, reasons = should_a10s_run()
        return {
            "active": False,
            "can_run": can_run,
            "stop_reasons": reasons,
            "message": "待機中"
        }
    
    filled = [s for s in state["steps"] if s.get("filled")]
    avg_price = get_average_price(state)
    pnl_pct = (current_price - avg_price) / avg_price * 100 if avg_price > 0 else 0
    
    return {
        "active": True,
        "ticker": ticker,
        "current_price": current_price,
        "avg_price": avg_price,
        "pnl_pct": round(pnl_pct, 2),
        "steps_filled": len(filled),
        "steps_total": len(state["steps"]),
        "take_profit_price": round(avg_price * (1 + A10S_CONFIG["take_profit_pct"]/100), 4),
        "stop_loss_price": round(avg_price * (1 - A10S_CONFIG["stop_loss_pct"]/100), 4)
    }


def send_telegram(msg):
    import requests as req
    req.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10)


def format_a10s_section():
    """デイリーレポート用A10Sセクション"""
    status = get_a10s_status()
    
    section = "\n━━━━━━━━━━━━━━━\n"
    section += "🎯 *A10S グリッド戦略*\n"
    
    if status["active"]:
        pnl = status["pnl_pct"]
        icon = "📈" if pnl >= 0 else "📉"
        section += f"{icon} {status['ticker']}: {pnl:+.2f}%\n"
        section += f"  平均単価: ${status['avg_price']:,.4f}\n"
        section += f"  進行: {status['steps_filled']}/{status['steps_total']}ステップ\n"
        section += f"  利確目標: ${status['take_profit_price']:,.4f}\n"
    else:
        can_run = status.get("can_run", False)
        if can_run:
            section += "⏸️ 待機中（次の相場を待っています）\n"
        else:
            reasons = status.get("stop_reasons", [])
            section += f"🔴 停止中: {reasons[0] if reasons else '条件未達'}\n"
    
    return section


if __name__ == "__main__":
    print("🎯 A10S 状態確認\n")
    
    # 稼働判定テスト
    can_run, reasons = should_a10s_run()
    print(f"稼働判定: {'✅ OK' if can_run else '❌ 停止'}")
    if not can_run:
        for r in reasons:
            print(f"  理由: {r}")
    
    # 現在価格
    price = get_current_price(A10S_CONFIG["ticker"])
    print(f"\n{A10S_CONFIG['ticker']}現在価格: ${price:,.2f}")
    
    # ラダー計算例（$800で）
    steps = calculate_ladder(price, 800)
    print(f"\nラダー計算（$800, {len(steps)}ステップ）:")
    for s in steps[:5]:
        print(f"  Step {s['step']}: ${s['entry_price']:,.4f} × {s['size']} = ${s['usd']:.0f}")
    print(f"  ...")
    
    print(f"\n✅ A10S実装完了！")
    print(f"   開始: a10s_check_and_trade() を呼び出すと開始")
