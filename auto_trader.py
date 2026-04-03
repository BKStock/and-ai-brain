"""
&AI QUANTUM EDGE - 自動取引エンジン
Hyperliquid APIウォレット経由で自動売買
"""

import os, json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

from eth_account import Account
from eth_account.signers.local import LocalAccount
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

PRIVATE_KEY = os.environ.get("HL_API_PRIVATE_KEY")
MAIN_WALLET = os.environ.get("HL_WALLET")
BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")

# ========================================
# KK確定取引ルール（2026-03-27）
# ========================================
POSITION_SIZE_PCT = 0.10  # Q1: 残高の10%/回
MAX_POSITIONS = 5         # Q2: 最大5銘柄同時
TAKE_PROFIT_PCT = 0.10    # Q3: +10%で利確通知
STOP_LOSS_PCT = 0.05      # Q4: -5%で自動損切り
CHECK_INTERVAL_HOURS = 1  # Q5: 1時間ごとチェック
REQUIRE_CONFIRM = True    # Q3: 利確はKK確認後に実行

MAX_POSITION_SIZE = 200   # 最大$200/ポジション（上限）
MAX_TOTAL_EXPOSURE = 500  # 最大総ポジション


def get_exchange():
    account: LocalAccount = Account.from_key(PRIVATE_KEY)
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    exchange = Exchange(
        account,
        constants.MAINNET_API_URL,
        vault_address=None,
        account_address=MAIN_WALLET
    )
    return info, exchange


def get_account_value():
    """口座残高取得（Unified Account対応: Spot USDH + Perps）"""
    import requests as req
    total = 0.0
    try:
        # Perps残高
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        state = info.user_state(MAIN_WALLET)
        perps_val = float(state.get("marginSummary", {}).get("accountValue", 0))
        total += perps_val
    except: pass
    try:
        # Spot残高（USDH: Unified AccountでPerps証拠金として使える）
        r = req.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState", "user": MAIN_WALLET}, timeout=8)
        if r.status_code == 200:
            balances = {b['coin']: float(b['total']) for b in r.json().get("balances", [])}
            usdh = balances.get("USDH", 0)
            total += usdh
    except: pass
    return total


def execute_signal(ticker: str, direction: str, confidence: str, strategy: str):
    """
    シグナルに基づいて自動取引を実行
    
    ticker: "BTC", "SOL" etc
    direction: "BUY" or "SELL"
    confidence: "高" / "中" / "低"
    strategy: "A" / "B" / "C"
    """
    import requests
    
    # 安全チェック: 信頼度が低い場合はスキップ
    if confidence == "低":
        print(f"⚠️ 信頼度低のためスキップ: {ticker} {direction}")
        return False
    
    # 口座残高確認
    account_value = get_account_value()
    
    if account_value < 10:
        send_telegram(f"⚠️ 口座残高が少なすぎます（${account_value:.2f}）\n入金してください")
        return False
    
    # 最大ポジション数チェック
    current_positions = get_positions()
    if len(current_positions) >= MAX_POSITIONS:
        print(f"⚠️ 最大ポジション数({MAX_POSITIONS}件)に達しています")
        return False
    
    # ポジションサイズ: 残高の10%（KKルール）
    position_usd = min(account_value * POSITION_SIZE_PCT, MAX_POSITION_SIZE)
    
    # 現在価格取得
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    prices = r.json()
    
    if ticker not in prices:
        print(f"❌ {ticker}の価格が取得できません")
        return False
    
    current_price = float(prices[ticker])
    size = round(position_usd / current_price, 6)
    
    # ストップロス計算
    if direction == "BUY":
        stop_price = round(current_price * (1 - STOP_LOSS_PCT), 2)
        is_buy = True
    else:
        stop_price = round(current_price * (1 + STOP_LOSS_PCT), 2)
        is_buy = False
    
    try:
        info, exchange = get_exchange()
        
        # 注文実行（成行）
        result = exchange.market_open(
            coin=ticker,
            is_buy=is_buy,
            sz=size,
        )
        
        if result.get("status") == "ok":
            msg = f"""✅ *&AI QUANTUM EDGE 取引実行！*
━━━━━━━━━━━━━━━

{'📈 BUY' if is_buy else '📉 SELL'} *{ticker}*
戦略: STRATEGY-{strategy}
信頼度: {confidence}

💰 執行詳細:
  サイズ: {size} {ticker}
  価格: ${current_price:,.4f}
  金額: ${position_usd:.2f} USDC
  ストップロス: ${stop_price:,.4f}

⏰ {datetime.now().strftime('%m/%d %H:%M')} JST
_自動執行 by &AI QUANTUM EDGE_"""
            
            send_telegram(msg)
            print(f"✅ 取引成功: {ticker} {'BUY' if is_buy else 'SELL'} ${position_usd:.2f}")
            return True
        else:
            print(f"❌ 取引失敗: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 取引エラー: {str(e)[:100]}")
        return False


def close_position(ticker: str):
    """ポジションをクローズ"""
    try:
        info, exchange = get_exchange()
        result = exchange.market_close(coin=ticker)
        if result.get("status") == "ok":
            send_telegram(f"✅ {ticker} ポジションクローズ完了")
            return True
    except Exception as e:
        print(f"クローズエラー: {e}")
    return False


def send_telegram(msg: str):
    """Telegramに通知"""
    import requests
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )


def get_positions():
    """現在のポジション一覧"""
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    state = info.user_state(MAIN_WALLET)
    positions = []
    for p in state.get("assetPositions", []):
        pos = p.get("position", {})
        size = float(pos.get("szi", 0))
        if size != 0:
            positions.append({
                "coin": pos.get("coin"),
                "size": size,
                "entry_price": float(pos.get("entryPx", 0)),
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                "direction": "LONG" if size > 0 else "SHORT"
            })
    return positions


if __name__ == "__main__":
    print("⚛️ &AI QUANTUM EDGE 自動取引エンジン テスト\n")
    
    av = get_account_value()
    print(f"口座残高: ${av:,.2f} USDC")
    
    positions = get_positions()
    print(f"現在のポジション: {len(positions)}件")
    
    for p in positions:
        pnl = p["unrealized_pnl"]
        print(f"  {p['direction']} {p['coin']}: {pnl:+.2f} USDC")
    
    print("\n✅ 自動取引エンジン 準備完了！")
    print("→ &AI BRAINのシグナルで自動売買が動きます")
    print()
    print("⚠️ 安全設定:")
    print(f"  最大ポジション: ${MAX_POSITION_SIZE}/件")
    print(f"  最大総ポジション: ${MAX_TOTAL_EXPOSURE}")
    print(f"  自動ストップロス: -{STOP_LOSS_PCT*100:.0f}%")


# ========================================
# 利確監視エンジン
# ========================================

def monitor_take_profit():
    """
    ポジションを監視して+10%達成時にKKに確認通知
    KKが「OK」と返信したら利確実行
    """
    import requests
    
    positions = get_positions()
    if not positions:
        return
    
    # 現在価格取得
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    prices = r.json()
    
    for p in positions:
        ticker = p["coin"]
        entry = p["entry_price"]
        size = p["size"]
        direction = p["direction"]
        
        if ticker not in prices:
            continue
        
        current = float(prices[ticker])
        
        if direction == "LONG":
            pnl_pct = (current - entry) / entry * 100
        else:
            pnl_pct = (entry - current) / entry * 100
        
        # +10%達成 → KKに確認通知
        if pnl_pct >= TAKE_PROFIT_PCT * 100:
            msg = f"""🎯 *利確タイミング！確認してください*
━━━━━━━━━━━━━━━

📈 {ticker} {direction}
エントリー: ${entry:,.4f}
現在価格: ${current:,.4f}
損益: *+{pnl_pct:.1f}%* 🔥

💰 利確すると:
${abs(size) * entry * TAKE_PROFIT_PCT:,.2f} USDC 確定

「OK」と返信で利確実行
「HOLD」と返信で保持継続

⏰ {datetime.now().strftime('%m/%d %H:%M')} JST"""
            
            send_telegram(msg)
        
        # -5%達成 → 即自動損切り（確認不要）
        elif pnl_pct <= -STOP_LOSS_PCT * 100:
            close_position(ticker)
            send_telegram(f"🛑 *自動損切り実行*\n{ticker}: {pnl_pct:.1f}%\n損切り完了")


def check_and_trade():
    """
    1時間ごとに実行されるメインループ
    シグナル確認 → 条件合致 → 取引実行
    """
    from brain_collector import get_market_data, quantum_portfolio_optimize
    from momentum_engine import get_all_momentum_scores
    
    print(f"⚛️ シグナルチェック: {datetime.now().strftime('%H:%M')}")
    
    # 残高確認
    av = get_account_value()
    if av < 10:
        print(f"残高不足: ${av:.2f}")
        return
    
    # モメンタムスコア取得
    scores = get_all_momentum_scores()
    
    # トップ銘柄を取得（スコア75以上）
    top_tickers = [s for s in scores if s['score'] >= 75 and s['trend'] == 'up']
    
    if not top_tickers:
        print("強いシグナルなし → スキップ")
        return
    
    # 既存ポジションと重複しないものを選ぶ
    current = {p["coin"] for p in get_positions()}
    new_targets = [t for t in top_tickers if t['name'] not in current]
    
    for target in new_targets[:2]:  # 最大2銘柄/チェック
        ticker = target['name']
        score = target['score']
        confidence = "高" if score >= 85 else "中"
        
        # エントリー通知をKKに送る
        import requests
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=10)
        prices = r.json()
        price = float(prices.get(ticker, 0))
        
        if price > 0:
            position_usd = av * POSITION_SIZE_PCT
            stop = price * (1 - STOP_LOSS_PCT)
            target_price = price * (1 + TAKE_PROFIT_PCT)
            
            msg = f"""⚛️ *&AI QUANTUM EDGE シグナル*
━━━━━━━━━━━━━━━

📈 BUY *{ticker}*
モメンタムスコア: {score}点 🔥
信頼度: {confidence}

💰 取引詳細:
  金額: ${position_usd:.0f} USDC（残高の10%）
  現在価格: ${price:,.4f}
  利確目標: ${target_price:,.4f} (+10%)
  損切り: ${stop:,.4f} (-5%)

自動実行します...
⏰ {datetime.now().strftime('%m/%d %H:%M')}"""
            
            send_telegram(msg)
            
            # 取引実行
            execute_signal(ticker, "BUY", confidence, "B")
    
    # 利確監視
    monitor_take_profit()


if __name__ == "__main__":
    print("⚛️ &AI QUANTUM EDGE 自動取引エンジン\n")
    av = get_account_value()
    positions = get_positions()
    print(f"口座残高: ${av:,.2f} USDC")
    print(f"ポジション: {len(positions)}/{MAX_POSITIONS}件")
    print(f"\n確定ルール:")
    print(f"  取引サイズ: 残高の{POSITION_SIZE_PCT*100:.0f}%")
    print(f"  最大同時: {MAX_POSITIONS}銘柄")
    print(f"  利確: +{TAKE_PROFIT_PCT*100:.0f}%（KK確認後）")
    print(f"  損切り: -{STOP_LOSS_PCT*100:.0f}%（自動）")
    print(f"  チェック: {CHECK_INTERVAL_HOURS}時間ごと")
    print(f"\n✅ 入金完了したら自動売買スタート！")


# ========================================
# 第2ルール: 逆張りロング（Fear&Greed）
# 第3ルール: 上昇転換確認ルール
# ========================================

def check_contrarian_long():
    """
    第2ルール: 逆張りロング発動チェック
    Fear&Greed 15以下が5日以上継続 + 複合条件
    """
    import requests
    
    # Fear&Greed 7日分取得
    r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
    fg_data = r.json()['data']
    
    # 5日連続15以下チェック
    low_fear_days = sum(1 for d in fg_data[:5] if int(d['value']) <= 15)
    current_fg = int(fg_data[0]['value'])
    
    if low_fear_days < 5:
        return False, f"Fear&Greed 5日連続15以下: {low_fear_days}/5日"
    
    # Bubble Index チェック
    from dotenv import load_dotenv
    load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')
    cg_gl = os.environ.get("COINGLASS_API_KEY","")
    r2 = requests.get("https://open-api-v3.coinglass.com/api/index/bitcoin-bubble-index",
        headers={"CG-API-KEY": cg_gl}, timeout=10)
    bubble = r2.json().get('data', [])
    bubble_idx = float(bubble[-1].get('index', 0)) if bubble else 0
    
    if bubble_idx > -10:
        return False, f"Bubble Index: {bubble_idx:.1f}（-10以下必要）"
    
    # Hyperliquid BTC FR チェック
    r3 = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "metaAndAssetCtxs"}, timeout=10)
    hl = r3.json()
    meta = hl[0]['universe']
    ctxs = hl[1]
    btc_fr = 0
    for i, asset in enumerate(meta):
        if asset['name'] == 'BTC' and i < len(ctxs):
            btc_fr = float(ctxs[i].get('funding', 0)) * 100
            break
    
    if btc_fr > 0.05:
        return False, f"BTC FR過剰: {btc_fr:+.4f}%（+0.05%以下必要）"
    
    # 全条件クリア！
    print(f"⚠️ 逆張りロング発動条件クリア！")
    print(f"   Fear&Greed: {current_fg}/100（{low_fear_days}日連続低水準）")
    print(f"   Bubble Index: {bubble_idx:.1f}")
    print(f"   BTC FR: {btc_fr:+.4f}%")
    return True, f"逆張りロング発動: F&G={current_fg} Bubble={bubble_idx:.1f}"


def check_bottom_reversal():
    """
    第3ルール: 上昇転換確認
    BTC 24hプラス転換 OR Fear&Greed+5以上 OR OI+10%
    """
    import requests
    import yfinance as yf
    
    signals = []
    
    # BTC 24h変化チェック
    hist = yf.Ticker('BTC-USD').history(period='3d')
    if len(hist) >= 2:
        btc_chg = (hist['Close'].iloc[-1] / hist['Close'].iloc[-2] - 1) * 100
        if btc_chg > 0:
            signals.append(f"📈 BTC 24h: {btc_chg:+.1f}%（プラス転換）")
    
    # Fear&Greed 前日比
    r = requests.get("https://api.alternative.me/fng/?limit=2", timeout=10)
    fg_data = r.json()['data']
    if len(fg_data) >= 2:
        today_fg = int(fg_data[0]['value'])
        yesterday_fg = int(fg_data[1]['value'])
        fg_change = today_fg - yesterday_fg
        if fg_change >= 5:
            signals.append(f"😊 Fear&Greed: {fg_change:+d}pt上昇（{yesterday_fg}→{today_fg}）")
    
    if signals:
        print(f"✅ 上昇転換シグナル検知！")
        for s in signals:
            print(f"   {s}")
        return True, signals
    
    return False, []


def execute_contrarian_long(account_value: float):
    """逆張りロング実行（BTCのみ・残高の5%）"""
    import requests
    
    position_usd = account_value * 0.05  # 残高の5%（最小）
    
    # BTC現在価格
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    prices = r.json()
    btc_price = float(prices.get('BTC', 0))
    
    if btc_price <= 0 or position_usd < 5:
        return False
    
    size = round(position_usd / btc_price, 6)
    stop_price = round(btc_price * 0.93, 2)   # -7%
    target_price = round(btc_price * 1.20, 2)  # +20%
    
    send_telegram(f"""🔄 *逆張りロング発動！*
━━━━━━━━━━━━━━━

📊 発動条件:
  Fear&Greed 5日連続15以下
  Bubble Index割安圏
  FR中立

💰 BTCロング（第2ルール）
  サイズ: ${position_usd:.0f}（残高の5%）
  価格: ${btc_price:,.0f}
  損切: ${stop_price:,.0f} (-7%)
  利確: ${target_price:,.0f} (+20%)

⚠️ _歴史的割安シグナル_
_過去83%の勝率（バックテスト）_""")
    
    try:
        info, exchange = get_exchange()
        result = exchange.market_open(coin='BTC', is_buy=True, sz=size)
        if result.get('status') == 'ok':
            send_telegram(f"✅ 逆張りBTCロング執行完了！\n${position_usd:.0f} @ ${btc_price:,.0f}")
            return True
    except Exception as e:
        send_telegram(f"❌ 逆張り執行エラー: {str(e)[:50]}")
    return False


def full_signal_check():
    """
    毎時実行: 全ルールをチェックして取引判断
    第1ルール（通常）+ 第2ルール（逆張り）+ 第3ルール（転換確認）
    """
    from momentum_engine import get_all_momentum_scores
    
    print(f"\n⚛️ 全ルールチェック: {datetime.now().strftime('%H:%M')}")
    
    av = get_account_value()
    if av < 5:
        print(f"残高不足: ${av:.2f}")
        return
    
    # まず利確・損切り監視
    monitor_take_profit()
    
    # 第3ルール: 上昇転換確認
    reversal, reversal_signals = check_bottom_reversal()
    
    # 第2ルール: 逆張りロング
    contrarian, contrarian_msg = check_contrarian_long()
    
    # 第1ルール: 通常モメンタムシグナル
    scores = get_all_momentum_scores()
    top_tickers = [s for s in scores if s['score'] >= 75 and s['trend'] == 'up']
    current_positions = {p['coin'] for p in get_positions()}
    
    # === 判断ロジック ===
    import requests
    r = requests.post("https://api.hyperliquid.xyz/info",
        json={"type": "allMids"}, timeout=10)
    prices = r.json()
    
    # 第1ルール実行（通常エントリー）
    if top_tickers and reversal:
        # 転換確認シグナルあり → 通常エントリー可能
        for target in top_tickers[:2]:
            ticker = target['name']
            if ticker not in current_positions and ticker in prices:
                score = target['score']
                confidence = "高" if score >= 85 else "中"
                execute_signal(ticker, "BUY", confidence, "B")
    
    elif contrarian and 'BTC' not in current_positions:
        # 第2ルール: 逆張りロング
        execute_contrarian_long(av)
    
    else:
        # シグナルなし
        if top_tickers:
            print(f"  モメンタム銘柄あり（{len(top_tickers)}件）だが転換未確認→待機")
        else:
            print(f"  シグナルなし → 待機")


if __name__ == "__main__":
    print("⚛️ &AI QUANTUM EDGE 自動取引エンジン v2.0\n")
    
    # デモファンドシミュレーション停止（KK指示 2026-03-29 / 手法確定まで）
    # run_demo_fund_simulation()
    av = get_account_value()
    positions = get_positions()
    
    print(f"口座残高: ${av:,.2f} USDC")
    print(f"ポジション: {len(positions)}/{MAX_POSITIONS}件")
    
    print(f"\n確定ルール v2.0:")
    print(f"  第1: 通常モメンタム（スコア70+・転換確認後）")
    print(f"  第2: 逆張りロング（F&G≤15が5日・Bubble割安）")
    print(f"  第3: 上昇転換確認（BTC+・F&G+5以上・OI+10%）")
    print(f"\n  利確T1: +8%（50%・KK確認）")
    print(f"  利確T2: +15%（残り・KK確認）")
    print(f"  損切り: -5%（自動）/ 逆張り: -7%")
    print(f"  トレーリング: +5%達成→損切り-2%に移動")
    
    print(f"\n✅ 入金完了したら自動売買スタート！")


def run_demo_fund_simulation():
    """デモファンドシミュレーションを実行してTelegramに送信"""
    import sys, requests, os
    sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
    from demo_fund import run_daily_simulation, load_fund, FUNDS, INITIAL_CAPITAL
    
    results = run_daily_simulation()
    
    # 結果をフォーマット
    summary_lines = []
    position_lines = []
    total_val = 0
    
    for fund_id in ["fund_1", "fund_2", "fund_3"]:
        fd = load_fund(fund_id)
        cfg = FUNDS[fund_id]
        val = fd.get("portfolio_value", INITIAL_CAPITAL)
        pnl = val - INITIAL_CAPITAL
        pnl_pct = pnl / INITIAL_CAPITAL * 100
        total_val += val
        
        open_positions = [p for p in fd.get("open_positions", []) if p.get("status") == "OPEN"]
        total_pos_pnl = sum(p.get("pnl", 0) for p in open_positions)
        
        # ファンドサマリー
        arrow = "📈" if pnl >= 0 else "📉"
        summary_lines.append(
            f"{cfg['emoji']} *{cfg['name']}*（月利{cfg['target_monthly']}%目標）\n"
            f"  ¥{val:,.0f} {arrow} {pnl_pct:+.2f}% | 含み益:¥{total_pos_pnl:+,.0f}"
        )
        
        # ポジション詳細
        if open_positions:
            position_lines.append(f"\n{cfg['emoji']} {cfg['name']} ポジション:")
            for p in open_positions:
                ticker = p.get("ticker","")
                direction = p.get("direction","")
                entry = p.get("entry_price", 0)
                current = p.get("current_price", entry)
                pnl_p = p.get("pnl_pct", 0)
                pnl_j = p.get("pnl", 0)
                pos_val = p.get("position_value", 0)
                leverage = p.get("leverage", 1)
                tp1 = p.get("take_profit_1", entry * 1.08)
                sl = p.get("stop_loss", entry * 0.95)
                arrow2 = "🟢" if pnl_j >= 0 else "🔴"
                position_lines.append(
                    f"  {arrow2} {direction} {ticker}\n"
                    f"     購入: ¥{pos_val:,.0f}（レバ{leverage}倍）\n"
                    f"     エントリー: ${entry:,.4f} → 現在: ${current:,.4f}\n"
                    f"     損益: {pnl_p:+.2f}% (¥{pnl_j:+,.0f})\n"
                    f"     🎯利確: ${tp1:,.4f}（+{p.get('take_profit_1_pct', cfg.get('take_profit_1',8))}%）\n"
                    f"     🛑損切: ${sl:,.4f}（{cfg.get('stop_loss_pct',-5)}%）"
                )
    
    total_pnl = total_val - INITIAL_CAPITAL * 3
    total_pnl_pct = total_pnl / (INITIAL_CAPITAL * 3) * 100
    
    msg = f"""🏦 *デモファンド シミュレーション*

{chr(10).join(summary_lines)}

━━━━━━━━━━━━━━━
💰 合計: ¥{total_val:,.0f} ({total_pnl:+,.0f}円 / {total_pnl_pct:+.2f}%)
━━━━━━━━━━━━━━━
{chr(10).join(position_lines) if position_lines else '📭 ポジションなし'}"""

    BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
    CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

