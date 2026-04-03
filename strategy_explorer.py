"""
&AI QUANTUM EDGE - 戦略自動探索エンジン
全手法×全銘柄×全パラメータを自動バックテストして
「今週の最強戦略」を発見する

毎週日曜23:00に実行
月曜8:00レポートに組み込み
"""

import os, json, requests, itertools
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
RESULTS_FILE = '/Users/mr.k/Projects/and-ai-brain/strategy_results.json'

# ==============================
# テスト対象銘柄
# ==============================
TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "TRX": "TRX-USD",
    "TON": "TON-USD",
}

# ==============================
# 8つの戦略定義
# ==============================

def strategy_momentum(prices, fast=5, slow=20, leverage=3, stop_loss=0.08):
    """① モメンタム: FASTMAがSLOW MAを上抜けでロング"""
    ma_fast = prices.rolling(fast).mean()
    ma_slow = prices.rolling(slow).mean()
    
    capital = 1000.0
    pos = 0; entry = 0; trades = 0; wins = 0
    
    for i in range(slow, len(prices)):
        p = prices.iloc[i]
        mf, ms = ma_fast.iloc[i], ma_slow.iloc[i]
        pmf, pms = ma_fast.iloc[i-1], ma_slow.iloc[i-1]
        
        if pos == 0 and mf > ms and pmf <= pms:
            pos = 1; entry = p; trades += 1
        elif pos == 1:
            pnl = (p - entry) / entry * leverage
            if pnl <= -stop_loss:
                capital *= (1 + pnl); pos = 0
            elif mf < ms and pmf >= pms:
                capital *= (1 + pnl)
                if pnl > 0: wins += 1
                pos = 0
    
    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * leverage
        capital *= (1 + pnl)
    
    return capital, trades, wins/max(trades,1)*100


def strategy_contrarian(prices, fg_data, fg_threshold=20, exit_fg=60, leverage=2, stop_loss=0.12):
    """② 逆張り: F&G低い時にロング、F&G高い時に利確"""
    capital = 1000.0
    pos = 0; entry = 0; trades = 0; wins = 0
    
    for i in range(len(prices)):
        p = prices.iloc[i]
        date = prices.index[i]
        
        try:
            fg = fg_data.loc[:date]['value'].iloc[-1]
        except:
            continue
        
        if pos == 1:
            pnl = (p - entry) / entry * leverage
            if pnl <= -stop_loss:
                capital *= (1 + pnl); pos = 0
            elif fg >= exit_fg:
                capital *= (1 + pnl)
                if pnl > 0: wins += 1
                pos = 0
        
        if pos == 0 and fg <= fg_threshold:
            pos = 1; entry = p; trades += 1
    
    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * leverage
        capital *= (1 + pnl)
    
    return capital, trades, wins/max(trades,1)*100


def strategy_bollinger(prices, window=20, std_mult=2.0, leverage=2, stop_loss=0.08):
    """③ ボリンジャーバンド: 下限タッチでロング、上限タッチで利確"""
    ma = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    upper = ma + std * std_mult
    lower = ma - std * std_mult
    
    capital = 1000.0
    pos = 0; entry = 0; trades = 0; wins = 0
    
    for i in range(window, len(prices)):
        p = prices.iloc[i]
        lo, up = lower.iloc[i], upper.iloc[i]
        
        if pos == 0 and p <= lo:
            pos = 1; entry = p; trades += 1
        elif pos == 1:
            pnl = (p - entry) / entry * leverage
            if pnl <= -stop_loss:
                capital *= (1 + pnl); pos = 0
            elif p >= up:
                capital *= (1 + pnl)
                if pnl > 0: wins += 1
                pos = 0
    
    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * leverage
        capital *= (1 + pnl)
    
    return capital, trades, wins/max(trades,1)*100


def strategy_breakout(prices, lookback=20, leverage=2, stop_loss=0.08):
    """④ ブレイクアウト: N日高値更新でロング"""
    capital = 1000.0
    pos = 0; entry = 0; trades = 0; wins = 0
    holding_days = 0; max_hold = 14
    
    for i in range(lookback, len(prices)):
        p = prices.iloc[i]
        high_n = prices.iloc[i-lookback:i].max()
        
        if pos == 0 and p > high_n:
            pos = 1; entry = p; trades += 1; holding_days = 0
        elif pos == 1:
            pnl = (p - entry) / entry * leverage
            holding_days += 1
            if pnl <= -stop_loss:
                capital *= (1 + pnl); pos = 0
            elif holding_days >= max_hold:  # N日で強制利確
                capital *= (1 + pnl)
                if pnl > 0: wins += 1
                pos = 0
    
    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * leverage
        capital *= (1 + pnl)
    
    return capital, trades, wins/max(trades,1)*100


def strategy_rsi(prices, period=14, oversold=30, overbought=70, leverage=2, stop_loss=0.08):
    """⑤ RSI: 売られすぎでロング、買われすぎで利確"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    
    capital = 1000.0
    pos = 0; entry = 0; trades = 0; wins = 0
    
    for i in range(period+1, len(prices)):
        p = prices.iloc[i]
        r = rsi.iloc[i]
        
        if pos == 0 and r <= oversold:
            pos = 1; entry = p; trades += 1
        elif pos == 1:
            pnl = (p - entry) / entry * leverage
            if pnl <= -stop_loss:
                capital *= (1 + pnl); pos = 0
            elif r >= overbought:
                capital *= (1 + pnl)
                if pnl > 0: wins += 1
                pos = 0
    
    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * leverage
        capital *= (1 + pnl)
    
    return capital, trades, wins/max(trades,1)*100


def strategy_dca(prices, interval=7, leverage=1):
    """⑥ 積立DCA: 毎週一定額を購入（最もシンプル）"""
    capital = 1000.0
    total_btc = 0
    weekly_amount = 50  # 毎週$50
    
    for i in range(0, len(prices), interval):
        p = prices.iloc[i]
        btc_bought = weekly_amount / p
        total_btc += btc_bought
        capital -= weekly_amount
    
    final_value = capital + total_btc * prices.iloc[-1]
    return final_value, len(prices)//interval, 100.0


def strategy_hold(prices, leverage=1):
    """⑦ Buy & Hold: 何もしない基準戦略"""
    ret = (prices.iloc[-1] / prices.iloc[0] - 1) * leverage
    return 1000 * (1 + ret), 1, 100.0


# ==============================
# バックテストエンジン
# ==============================

def run_all_strategies(ticker_name: str, days: int = 365*2) -> list:
    """全戦略を1銘柄でテスト"""
    yf_ticker = TICKERS.get(ticker_name)
    if not yf_ticker:
        return []
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    try:
        prices = yf.Ticker(yf_ticker).history(start=start, end=end)['Close']
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        if len(prices) < 50:
            return []
    except:
        return []
    
    # F&Gデータ（逆張り戦略用）
    fg_df = None
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1000", timeout=8)
        fg_raw = r.json()['data']
        fg_df = pd.DataFrame(fg_raw)
        fg_df['timestamp'] = pd.to_datetime(fg_df['timestamp'].astype(int), unit='s')
        fg_df['value'] = fg_df['value'].astype(int)
        fg_df = fg_df.set_index('timestamp').sort_index()
    except:
        pass
    
    results = []
    
    # 各戦略とパラメータをテスト
    test_cases = [
        # (戦略名, 関数, パラメータ)
        ("Hold", strategy_hold, {"leverage": 1}),
        ("Momentum L1 5/20", strategy_momentum, {"fast": 5, "slow": 20, "leverage": 1}),
        ("Momentum L2 5/20", strategy_momentum, {"fast": 5, "slow": 20, "leverage": 2}),
        ("Momentum L3 5/20", strategy_momentum, {"fast": 5, "slow": 20, "leverage": 3}),
        ("Momentum L2 10/30", strategy_momentum, {"fast": 10, "slow": 30, "leverage": 2}),
        ("Bollinger L2 2σ", strategy_bollinger, {"std_mult": 2.0, "leverage": 2}),
        ("Bollinger L2 2.5σ", strategy_bollinger, {"std_mult": 2.5, "leverage": 2}),
        ("Breakout L2 20d", strategy_breakout, {"lookback": 20, "leverage": 2}),
        ("Breakout L2 10d", strategy_breakout, {"lookback": 10, "leverage": 2}),
        ("RSI L2 30/70", strategy_rsi, {"oversold": 30, "overbought": 70, "leverage": 2}),
        ("RSI L2 25/75", strategy_rsi, {"oversold": 25, "overbought": 75, "leverage": 2}),
        ("DCA 週次", strategy_dca, {"interval": 7}),
    ]
    
    if fg_df is not None:
        test_cases += [
            ("Contrarian L2 F&G20", strategy_contrarian, {"fg_data": fg_df, "fg_threshold": 20, "leverage": 2}),
            ("Contrarian L2 F&G15", strategy_contrarian, {"fg_data": fg_df, "fg_threshold": 15, "leverage": 2}),
        ]
    
    for strat_name, func, params in test_cases:
        try:
            final, trades, win_rate = func(prices, **params)
            total_return = (final - 1000) / 1000 * 100
            annual_return = (final / 1000) ** (365/days) - 1
            
            results.append({
                "ticker": ticker_name,
                "strategy": strat_name,
                "final_capital": round(final, 2),
                "total_return": round(total_return, 1),
                "annual_return": round(annual_return * 100, 1),
                "monthly_return": round(annual_return * 100 / 12, 1),
                "trades": trades,
                "win_rate": round(win_rate, 1),
                "sharpe_proxy": round(total_return / max(1, trades), 2),
            })
        except Exception as e:
            pass
    
    return sorted(results, key=lambda x: x['total_return'], reverse=True)


def run_full_exploration(days: int = 365*2) -> dict:
    """全銘柄×全戦略を探索"""
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    print(f"\n⚛️ 戦略探索エンジン 開始: {now}")
    print(f"期間: 過去{days}日 / 対象: {len(TICKERS)}銘柄")
    
    all_results = {}
    global_best = []
    
    for ticker in TICKERS:
        print(f"  {ticker} テスト中...", end="", flush=True)
        results = run_all_strategies(ticker, days)
        all_results[ticker] = results
        if results:
            best = results[0]
            global_best.append(best)
            print(f" 最強: {best['strategy']} ({best['total_return']:+.1f}%)")
        else:
            print(" データなし")
    
    # 全体ランキング
    global_best.sort(key=lambda x: x['total_return'], reverse=True)
    
    # 結果を保存
    save_data = {
        "generated_at": now,
        "period_days": days,
        "all_results": all_results,
        "global_ranking": global_best[:20],
        "recommendations": {
            "fund_1": global_best[0] if global_best else {},
            "fund_2": global_best[1] if len(global_best) > 1 else {},
            "fund_3": global_best[2] if len(global_best) > 2 else {},
        }
    }
    
    with open(RESULTS_FILE, 'w') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    # Telegramレポート
    send_exploration_report(save_data)
    
    return save_data


def send_exploration_report(data: dict):
    """探索結果をTelegramに送信"""
    ranking = data.get("global_ranking", [])[:10]
    recs = data.get("recommendations", {})
    
    msg = f"""⚛️ *戦略自動探索レポート*
{data['generated_at']}
期間: 過去{data['period_days']}日

━━━━━━━━━━━━━━━
🏆 *全銘柄×全戦略 TOP10*

"""
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for i, r in enumerate(ranking[:10]):
        msg += f"{medals[i]} {r['ticker']} {r['strategy']}\n"
        msg += f"   {r['total_return']:+.1f}% (月{r['monthly_return']:+.1f}%) 勝率{r['win_rate']:.0f}%\n"
    
    msg += f"""
━━━━━━━━━━━━━━━
🎯 *3ファンド推奨戦略*

🛡️ FUND-1 → {recs.get('fund_1',{}).get('ticker','')} {recs.get('fund_1',{}).get('strategy','')}
⚡ FUND-2 → {recs.get('fund_2',{}).get('ticker','')} {recs.get('fund_2',{}).get('strategy','')}
🚀 FUND-3 → {recs.get('fund_3',{}).get('ticker','')} {recs.get('fund_3',{}).get('strategy','')}

🦴 &AI QUANTUM EDGE 戦略探索エンジン"""
    
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 730  # デフォルト2年
    data = run_full_exploration(days)
    
    print("\n" + "="*60)
    print("📊 グローバルランキング TOP10")
    print("="*60)
    for i, r in enumerate(data['global_ranking'][:10], 1):
        print(f"{i:2}. {r['ticker']:5} {r['strategy']:25} {r['total_return']:+8.1f}% (月{r['monthly_return']:+5.1f}%)")


# ==============================
# トリガー型戦略切替システム
# ==============================

def check_regime_change() -> dict:
    """
    相場の構造変化を毎時検知
    変化があった時だけ戦略を切り替える
    """
    import requests
    
    changes = []
    should_rebalance = False
    
    # 前回の状態を読み込む
    state_file = '/Users/mr.k/Projects/and-ai-brain/regime_state.json'
    import json, os
    if os.path.exists(state_file):
        with open(state_file) as f:
            prev = json.load(f)
    else:
        prev = {"fg": 50, "btc_dom": 50, "btc_price": 0}
    
    # 現在の状態を取得
    try:
        r1 = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        fg_now = int(r1.json()['data'][0]['value'])
        fg_change = abs(fg_now - prev.get('fg', 50))
        if fg_change >= 15:
            changes.append(f"F&G急変: {prev.get('fg',50)} → {fg_now} (±{fg_change})")
            should_rebalance = True
    except:
        fg_now = prev.get('fg', 50)
    
    try:
        r2 = requests.get("https://api.coingecko.com/api/v3/global", timeout=5)
        btc_dom = round(r2.json()['data']['market_cap_percentage']['btc'], 1)
        dom_change = abs(btc_dom - prev.get('btc_dom', 50))
        if dom_change >= 5:
            changes.append(f"BTC支配率急変: {prev.get('btc_dom',50)} → {btc_dom}% (±{dom_change}%)")
            should_rebalance = True
    except:
        btc_dom = prev.get('btc_dom', 50)
    
    try:
        r3 = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=5)
        btc_price = float(r3.json().get('BTC', 0))
        price_change = abs(btc_price - prev.get('btc_price', btc_price)) / max(prev.get('btc_price', btc_price), 1) * 100
        if price_change >= 10:
            changes.append(f"BTC急変動: {prev.get('btc_price',0):,.0f} → ${btc_price:,.0f} (±{price_change:.1f}%)")
            should_rebalance = True
    except:
        btc_price = prev.get('btc_price', 0)
    
    # 3ヶ月に1回の強制更新チェック
    from datetime import datetime
    last_full = prev.get('last_full_rebalance', '2020-01-01')
    days_since = (datetime.now() - datetime.strptime(last_full, '%Y-%m-%d')).days
    if days_since >= 90:
        changes.append(f"定期更新: {days_since}日経過（90日サイクル）")
        should_rebalance = True
    
    # 状態を保存
    new_state = {
        "fg": fg_now,
        "btc_dom": btc_dom,
        "btc_price": btc_price,
        "last_check": datetime.now().strftime('%Y-%m-%d %H:%M'),
        "last_full_rebalance": datetime.now().strftime('%Y-%m-%d') if should_rebalance else last_full
    }
    with open(state_file, 'w') as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    
    return {
        "should_rebalance": should_rebalance,
        "changes": changes,
        "current_state": new_state
    }

