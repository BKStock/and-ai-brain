"""
&AI QUANTUM EDGE - バックテストエンジン
=========================================
過去30日のYahoo Financeデータで各戦略を検証
- 勝率・期待値・最大ドローダウンを計算
- 最も良い戦略をファンドに自動適用
"""

import json, os
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from demo_fund import FUNDS

BACKTEST_RESULTS_FILE = '/Users/mr.k/Projects/and-ai-brain/backtest_results.json'

# ファンド別対象銘柄 → Yahoo Financeティッカー変換
TICKER_MAP = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "XRP": "XRP-USD", "Gold": "GC=F",
    "NVDA": "NVDA", "ARM": "ARM", "AMD": "AMD",
    "TRX": "TRX-USD", "TON": "TON-USD",
    "DKNG": "DKNG", "SEA": "SE",
}

STRATEGIES = ["MOMENTUM", "CONTRARIAN", "TREND_FOLLOW", "GRID", "LONG_SHORT"]


# ----------------------------------------
# 戦略シミュレーター（過去データ）
# ----------------------------------------

def simulate_momentum(prices: list, score_threshold: int = 70) -> list:
    """モメンタム戦略バックテスト: 20日リターン > 5% → ロングエントリー"""
    trades = []
    for i in range(20, len(prices) - 5):
        mom_20 = (prices[i] / prices[i - 20] - 1) * 100
        if mom_20 >= 5:
            entry = prices[i]
            exit_price = prices[i + 5]
            pnl_pct = (exit_price - entry) / entry * 100
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "LONG"})
    return trades


def simulate_contrarian(prices: list, fg_values: list) -> list:
    """逆張り戦略バックテスト: F&G <= 25 → ロング5日保有"""
    trades = []
    n = min(len(prices), len(fg_values))
    for i in range(1, n - 5):
        if fg_values[i] <= 25:
            entry = prices[i]
            exit_price = prices[i + 5]
            pnl_pct = (exit_price - entry) / entry * 100
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "LONG"})
    return trades


def simulate_trend_follow(prices: list, btc_prices: list = None) -> list:
    """トレンドフォロー: 20日MA上 + 5日後決済"""
    trades = []
    for i in range(20, len(prices) - 5):
        ma20 = np.mean(prices[i - 20:i])
        if prices[i] > ma20:
            entry = prices[i]
            exit_price = prices[i + 5]
            pnl_pct = (exit_price - entry) / entry * 100
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "LONG"})
        elif prices[i] < ma20 * 0.98:  # 2%以上MA下
            entry = prices[i]
            exit_price = prices[i + 5]
            pnl_pct = (entry - exit_price) / entry * 100  # ショート
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "SHORT"})
    return trades


def simulate_grid(prices: list, grid_spacing: float = 0.02) -> list:
    """グリッド戦略: 2%下落ごとに買い、反発で利確"""
    trades = []
    if not prices:
        return trades
    base = prices[0]
    levels_bought = {}

    for i in range(1, len(prices) - 3):
        p = prices[i]
        for level in range(1, 6):
            level_price = base * (1 - grid_spacing * level)
            if p <= level_price and level not in levels_bought:
                levels_bought[level] = {"price": p, "idx": i}
            elif level in levels_bought:
                entry = levels_bought[level]["price"]
                if p >= entry * 1.02:  # +2%で利確
                    pnl_pct = (p - entry) / entry * 100
                    trades.append({"entry": entry, "exit": p, "pnl_pct": pnl_pct, "direction": "LONG"})
                    del levels_bought[level]
                    base = p  # グリッドリセット
                    levels_bought = {}
                    break
    return trades


def simulate_long_short(prices: list) -> list:
    """ロング/ショート: RSI 30以下でロング、70以上でショート"""
    trades = []
    if len(prices) < 14:
        return trades

    for i in range(14, len(prices) - 3):
        window = prices[i - 14:i]
        gains = [max(window[j] - window[j - 1], 0) for j in range(1, len(window))]
        losses = [max(window[j - 1] - window[j], 0) for j in range(1, len(window))]
        avg_gain = np.mean(gains) if gains else 0.001
        avg_loss = np.mean(losses) if losses else 0.001
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - 100 / (1 + rs)

        entry = prices[i]
        exit_price = prices[min(i + 3, len(prices) - 1)]

        if rsi <= 30:
            pnl_pct = (exit_price - entry) / entry * 100
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "LONG"})
        elif rsi >= 70:
            pnl_pct = (entry - exit_price) / entry * 100
            trades.append({"entry": entry, "exit": exit_price, "pnl_pct": pnl_pct, "direction": "SHORT"})
    return trades


# ----------------------------------------
# 統計計算
# ----------------------------------------

def calc_stats(trades: list, leverage: float = 1.0) -> dict:
    """トレード統計を計算"""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expected_value": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
        }

    pnls = [t["pnl_pct"] * leverage for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls) * 100
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    expected_value = win_rate / 100 * avg_win + (1 - win_rate / 100) * avg_loss

    # 最大ドローダウン計算
    cumulative = 100.0
    peak = 100.0
    max_dd = 0.0
    for p in pnls:
        cumulative *= (1 + p / 100)
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak * 100
        if dd > max_dd:
            max_dd = dd

    total_return = cumulative - 100.0

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expected_value": round(expected_value, 2),
        "max_drawdown": round(max_dd, 2),
        "total_return": round(total_return, 2),
    }


# ----------------------------------------
# メインバックテスト関数
# ----------------------------------------

def run_backtest(days: int = 30, verbose: bool = True) -> dict:
    """
    全ファンド × 全戦略のバックテストを実行
    Returns: dict with results per fund per strategy
    """
    print(f"📊 バックテスト開始（過去{days}日）...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Fear&Greed履歴取得（Contrarian用）
    fg_values = []
    try:
        import requests
        r = requests.get(f"https://api.alternative.me/fng/?limit={days}", timeout=8)
        fg_data = r.json()['data']
        fg_values = [int(d['value']) for d in reversed(fg_data)]
    except:
        fg_values = [50] * days

    results = {
        "generated_at": now,
        "backtest_days": days,
        "funds": {},
        "best_strategies": {},
    }

    for fund_id, config in FUNDS.items():
        leverage = config.get("leverage", 1)
        preferred = config.get("preferred_tickers", [])
        fund_results = {}

        strategy_scores = {}  # 戦略 → expected_value の集計

        for ticker in preferred[:5]:  # 上位5銘柄でテスト
            yf_ticker = TICKER_MAP.get(ticker)
            if not yf_ticker:
                continue

            try:
                hist = yf.Ticker(yf_ticker).history(period=f"{days + 30}d")
                if len(hist) < days:
                    continue
                prices = list(hist['Close'].iloc[-days - 10:])
            except Exception as e:
                if verbose:
                    print(f"  ⚠️ {ticker} データ取得失敗: {e}")
                continue

            if ticker not in fund_results:
                fund_results[ticker] = {}

            # 各戦略をバックテスト
            for strategy in STRATEGIES:
                if strategy == "MOMENTUM":
                    trades = simulate_momentum(prices, config.get("score_threshold", 70))
                elif strategy == "CONTRARIAN":
                    trades = simulate_contrarian(prices, fg_values[-len(prices):] if len(fg_values) >= len(prices) else fg_values + [50] * len(prices))
                elif strategy == "TREND_FOLLOW":
                    trades = simulate_trend_follow(prices)
                elif strategy == "GRID":
                    trades = simulate_grid(prices)
                elif strategy == "LONG_SHORT":
                    trades = simulate_long_short(prices)
                else:
                    trades = []

                stats = calc_stats(trades, leverage)
                fund_results[ticker][strategy] = stats

                ev = stats["expected_value"]
                if strategy not in strategy_scores:
                    strategy_scores[strategy] = []
                strategy_scores[strategy].append(ev)

        # 戦略別平均スコアで最良戦略を選定
        strategy_avg = {
            strat: round(np.mean(evs), 3) if evs else -99
            for strat, evs in strategy_scores.items()
        }
        best_strategy = max(strategy_avg, key=strategy_avg.get) if strategy_avg else "MOMENTUM"

        results["funds"][fund_id] = {
            "tickers": fund_results,
            "strategy_avg_ev": strategy_avg,
            "best_strategy": best_strategy,
        }
        results["best_strategies"][fund_id] = best_strategy

        if verbose:
            print(f"  {config['emoji']} {config['name']}: 最良戦略 = {best_strategy} "
                  f"(EV={strategy_avg.get(best_strategy, 0):.2f}%)")

    # 結果を保存
    with open(BACKTEST_RESULTS_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ バックテスト完了 → {BACKTEST_RESULTS_FILE}")
    return results


def get_best_strategy_for_fund(fund_id: str) -> str:
    """保存されたバックテスト結果から最良戦略を返す"""
    if not os.path.exists(BACKTEST_RESULTS_FILE):
        return "MOMENTUM"
    try:
        with open(BACKTEST_RESULTS_FILE) as f:
            results = json.load(f)
        return results.get("best_strategies", {}).get(fund_id, "MOMENTUM")
    except:
        return "MOMENTUM"


def format_backtest_summary() -> str:
    """バックテスト結果サマリー文字列を返す（Telegram表示用）"""
    if not os.path.exists(BACKTEST_RESULTS_FILE):
        return "⚠️ バックテスト未実行"

    try:
        with open(BACKTEST_RESULTS_FILE) as f:
            results = json.load(f)
    except:
        return "⚠️ バックテスト結果読み込みエラー"

    days = results.get("backtest_days", 30)
    gen_at = results.get("generated_at", "不明")

    lines = [f"📊 *バックテスト結果* （過去{days}日）", f"更新: {gen_at}\n"]

    for fund_id, config in FUNDS.items():
        fund_res = results.get("funds", {}).get(fund_id, {})
        best = fund_res.get("best_strategy", "N/A")
        strategy_avg = fund_res.get("strategy_avg_ev", {})

        lines.append(f"{config['emoji']} *{config['name']}* → 最良: `{best}`")
        for strat, ev in sorted(strategy_avg.items(), key=lambda x: -x[1]):
            mark = "🏆" if strat == best else "  "
            lines.append(f"  {mark} {strat}: EV={ev:+.2f}%")
        lines.append("")

    return "\n".join(lines)


def format_strategy_winrates() -> dict:
    """ファンド別・戦略別勝率を返す（ダッシュボード用）"""
    if not os.path.exists(BACKTEST_RESULTS_FILE):
        return {}

    try:
        with open(BACKTEST_RESULTS_FILE) as f:
            results = json.load(f)
    except:
        return {}

    output = {}
    for fund_id in FUNDS:
        fund_res = results.get("funds", {}).get(fund_id, {})
        tickers_data = fund_res.get("tickers", {})

        strategy_winrates = {}
        for ticker, strat_data in tickers_data.items():
            for strat, stats in strat_data.items():
                if strat not in strategy_winrates:
                    strategy_winrates[strat] = []
                strategy_winrates[strat].append(stats.get("win_rate", 0))

        output[fund_id] = {
            strat: round(np.mean(wrs), 1) if wrs else 0.0
            for strat, wrs in strategy_winrates.items()
        }
    return output


if __name__ == "__main__":
    print("⚛️ &AI QUANTUM EDGE バックテストエンジン\n")
    results = run_backtest(days=30, verbose=True)

    print("\n" + "=" * 50)
    print(format_backtest_summary())

    print("\n📋 戦略別勝率サマリー:")
    winrates = format_strategy_winrates()
    for fund_id, strats in winrates.items():
        config = FUNDS[fund_id]
        print(f"\n{config['emoji']} {config['name']}:")
        for strat, wr in sorted(strats.items(), key=lambda x: -x[1]):
            print(f"  {strat}: {wr:.1f}%")
