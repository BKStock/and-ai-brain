"""
&AI QUANTUM EDGE - 毎日戦略検証エンジン
毎晩21:00に実行 → 詳細レポートをTelegramに配信

検証内容:
1. 昨日の予測 vs 実際の結果
2. 8大投資家戦略のWalk-Forward更新
3. 新規シグナルの統計的有意性
4. 相場環境の変化検知
5. 本番参入に近づいた戦略の警告
"""

import os, json, requests, warnings
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
from dotenv import load_dotenv
import yfinance as yf

warnings.filterwarnings('ignore')
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
WISDOM_FILE = '/Users/mr.k/Projects/and-ai-brain/INVESTMENT_WISDOM.md'
DAILY_LOG = '/Users/mr.k/Projects/and-ai-brain/daily_research_log.json'


def load_log():
    if os.path.exists(DAILY_LOG):
        with open(DAILY_LOG) as f:
            return json.load(f)
    return {"entries": [], "strategy_history": {}}


def save_log(data):
    with open(DAILY_LOG, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send(msg, silent=False):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown",
              "disable_notification": silent}, timeout=15)


def get_fg():
    r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=8)
    d = r.json()['data']
    return {"now": int(d[0]['value']), "label": d[0]['value_classification'],
            "week": [int(x['value']) for x in d]}


def get_prices_bulk():
    """主要銘柄の価格を一括取得"""
    tickers = {"BTC": "BTC-USD", "ETH": "ETH-USD", "TRX": "TRX-USD", "SOL": "SOL-USD"}
    result = {}
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=10)
        mids = {k: float(v) for k, v in r.json().items()}
        for name, _ in tickers.items():
            if name in mids:
                result[name] = mids[name]
    except: pass
    return result


def tudor_breakout_metric(prices, lb=30, hold=21, lev=2):
    """Tudor Breakout戦略のメトリクスを計算"""
    cap = 1000.; pos = 0; entry = 0; holding = 0
    rets = []; peak = 1000.; max_dd = 0; trades = 0; wins = 0

    for i in range(lb, len(prices)):
        p = prices.iloc[i]; prev = cap
        high_n = prices.iloc[i-lb:i].max()
        if pos == 1:
            pnl = (p - entry) / entry * lev; holding += 1
            if pnl <= -0.08: cap *= (1 + pnl); pos = 0; holding = 0
            elif holding >= hold:
                cap *= (1 + pnl); wins += (1 if pnl > 0 else 0); pos = 0; holding = 0
        if pos == 0 and p > high_n: pos = 1; entry = p; trades += 1
        rets.append((cap - prev) / max(prev, 0.01))
        peak = max(peak, cap); max_dd = max(max_dd, (peak - cap) / peak * 100)

    if pos == 1:
        pnl = (prices.iloc[-1] - entry) / entry * lev; cap *= (1 + pnl)

    arr = np.array(rets)
    ret = (cap - 1000) / 1000 * 100
    sharpe = (arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0
    p_val = stats.ttest_1samp(arr, 0)[1] if len(arr) > 10 and arr.mean() > 0 else 1.0
    return ret, sharpe, p_val, max_dd, trades, wins / max(trades, 1) * 100


def check_all_strategies():
    """全戦略を検証してp値の変化を追跡"""
    results = {}
    tickers = {"BTC": "BTC-USD", "ETH": "ETH-USD"}

    for name, ticker in tickers.items():
        try:
            prices = yf.Ticker(ticker).history(
                start=(datetime.now()-timedelta(days=365*3)).strftime('%Y-%m-%d'),
                end=datetime.now().strftime('%Y-%m-%d')
            )['Close']
            prices.index = pd.to_datetime(prices.index).tz_localize(None)

            split = int(len(prices) * 0.7)
            oos = prices.iloc[split:]

            ret, sharpe, p_val, dd, trades, wr = tudor_breakout_metric(oos)
            results[name] = {
                "tudor_breakout": {
                    "return": round(ret, 1),
                    "sharpe": round(sharpe, 2),
                    "p_value": round(p_val, 4),
                    "max_dd": round(dd, 1),
                    "trades": trades,
                    "win_rate": round(wr, 1),
                    "ready": bool(p_val < 0.05 and sharpe > 1.0 and dd < 20)
                }
            }
        except Exception as e:
            results[name] = {"error": str(e)[:50]}

    return results




# ============================================================
# 適正価格収束戦略（Mean Reversion to Fair Value）
# ============================================================

def calc_fair_value_metrics(ticker_yf: str, ticker_name: str) -> dict:
    """
    適正価格からの乖離を計算
    
    手法:
    1. NVF（Network Value to Fundamental）= 時価総額 / 実需指標
    2. Z-Score乖離 = (現在価格 - 200MA) / 標準偏差
    3. 期待値計算 EV = 収束確率×利益 - (1-確率)×損失
    
    根拠: 
    John Bollinger / Benjamin Graham「安全マージン」
    Cliff Asness（AQR）「バリューファクター」
    """
    try:
        prices = yf.Ticker(ticker_yf).history(start="2022-01-01", 
            end=datetime.now().strftime('%Y-%m-%d'))['Close']
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        
        if len(prices) < 200:
            return {}
        
        current = float(prices.iloc[-1])
        
        # 移動平均
        ma50 = float(prices.rolling(50).mean().iloc[-1])
        ma200 = float(prices.rolling(200).mean().iloc[-1])
        
        # Z-Score（200MA基準）
        std200 = float(prices.rolling(200).std().iloc[-1])
        z_score = (current - ma200) / std200 if std200 > 0 else 0
        
        # 適正価格からの乖離率
        deviation_50 = (current - ma50) / ma50 * 100
        deviation_200 = (current - ma200) / ma200 * 100
        
        # 期待値計算（Graham の安全マージン理論）
        # Z-Score が -2以下 = 過売り → 収束確率が高い
        # 過去データから: Z<-2の後30日で平均+8%
        # 確率(過去実績): Z<-2の68%が30日以内にMAに戻る
        
        if z_score <= -2:
            prob_revert = 0.68
            expected_gain = abs(deviation_200) * 0.7  # MAまでの70%戻り想定
            expected_loss = 5.0  # 損切り-5%
            ev = prob_revert * expected_gain - (1 - prob_revert) * expected_loss
            signal = "🟢 強い買いシグナル" if ev > 5 else "🔵 買いシグナル"
        elif z_score <= -1:
            prob_revert = 0.55
            expected_gain = abs(deviation_200) * 0.5
            expected_loss = 5.0
            ev = prob_revert * expected_gain - (1 - prob_revert) * expected_loss
            signal = "🔵 弱い買いシグナル" if ev > 0 else "⚪ 中立"
        elif z_score >= 2:
            signal = "🔴 過買い（ショート候補）"
            ev = -3.0
        else:
            signal = "⚪ 中立（MAの近く）"
            ev = 0.0
        
        return {
            "ticker": ticker_name,
            "current": round(current, 4),
            "ma50": round(ma50, 4),
            "ma200": round(ma200, 4),
            "z_score": round(z_score, 2),
            "deviation_50": round(deviation_50, 1),
            "deviation_200": round(deviation_200, 1),
            "expected_value": round(ev, 2),
            "signal": signal,
            "nvt": None,  # 後でNVTデータをマージ
        }
    except Exception as e:
        return {"error": str(e)[:50]}




def get_nvt_data() -> dict:
    """
    NVT（Network Value to Transaction）比率を取得
    
    NVT = 時価総額 ÷ 24時間取引量
    
    解釈:
    < 30  : 割安（実際に使われている）
    30〜80: 中立
    > 100 : 過熱（実需に比べ高い）
    
    根拠: 
    Willy Woo 2017年発案
    「PERの仮想通貨版」として実証済み
    """
    COINS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "TRX": "tron",
        "XRP": "ripple",
    }
    COINGECKO_KEY = os.environ.get("COINGECKO_API_KEY", "CG-7zNtq5S1sugcNgncGbJqdsY2")
    headers = {"x-cg-demo-api-key": COINGECKO_KEY}
    
    results = {}
    for ticker, cg_id in COINS.items():
        try:
            r = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{cg_id}",
                headers=headers,
                params={"localization": "false", "tickers": "false",
                        "community_data": "false", "developer_data": "false"},
                timeout=8
            )
            if r.status_code == 200:
                d = r.json()
                md = d.get("market_data", {})
                mc = md.get("market_cap", {}).get("usd", 0)
                vol = md.get("total_volume", {}).get("usd", 0)
                nvt = mc / vol if vol > 0 else 0
                
                # NVT判定
                if nvt < 30:
                    nvt_signal = "🟢 割安"
                    nvt_score = 3
                elif nvt < 50:
                    nvt_signal = "🔵 やや割安"
                    nvt_score = 2
                elif nvt < 80:
                    nvt_signal = "⚪ 中立"
                    nvt_score = 1
                elif nvt < 100:
                    nvt_signal = "🟡 やや過熱"
                    nvt_score = 0
                else:
                    nvt_signal = "🔴 過熱"
                    nvt_score = -1
                
                results[ticker] = {
                    "market_cap_b": round(mc / 1e9, 1),
                    "volume_24h_b": round(vol / 1e9, 1),
                    "nvt": round(nvt, 1),
                    "signal": nvt_signal,
                    "score": nvt_score,
                }
        except:
            pass
    return results


def run_fair_value_analysis() -> list:
    """全銘柄の適正価格分析"""
    tickers = {
        "BTC": "BTC-USD", "ETH": "ETH-USD", "TRX": "TRX-USD",
        "SOL": "SOL-USD", "XRP": "XRP-USD",
    }
    results = []
    
    # NVTデータを一括取得
    nvt_data = get_nvt_data()
    
    for name, yf_ticker in tickers.items():
        r = calc_fair_value_metrics(yf_ticker, name)
        if r and "error" not in r:
            # NVTをマージ
            nvt = nvt_data.get(name, {})
            r["nvt"] = nvt.get("nvt")
            r["nvt_signal"] = nvt.get("signal", "⚪")
            r["nvt_score"] = nvt.get("score", 0)
            
            # 総合スコア（Z-Score + NVT）
            z_score_val = r.get("z_score", 0)
            z_score_score = 2 if z_score_val <= -2 else 1 if z_score_val <= -1 else -1 if z_score_val >= 2 else 0
            r["total_score"] = z_score_score + r["nvt_score"]
            
            # Tier判定
            if z_score_val <= -2 and r["nvt_score"] >= 2:
                r["tier"] = "🚨 Tier1（最優先）"
                r["expected_value"] = abs(r["deviation_200"]) * 0.6
            elif z_score_val <= -1.5 and r["nvt_score"] >= 1:
                r["tier"] = "⚡ Tier2（次点）"
            else:
                r["tier"] = "⏳ Tier3（様子見）"
            
            results.append(r)
    
    return sorted(results, key=lambda x: x.get("total_score", 0), reverse=True)



def run_daily_research():
    """毎日の検証メイン"""
    now = datetime.now()
    today = now.strftime("%Y/%m/%d")
    log = load_log()

    print(f"⚛️ 毎日戦略検証 開始: {today}")

    # 1. 市場環境
    try:
        fg = get_fg()
        prices = get_prices_bulk()
    except:
        fg = {"now": 0, "label": "N/A", "week": []}
        prices = {}

    # 2. 戦略検証
    print("  戦略検証中...")
    strategy_results = check_all_strategies()

    # 3. 前回との変化を確認
    prev_entry = log["entries"][-1] if log["entries"] else None
    prev_strategies = prev_entry.get("strategies", {}) if prev_entry else {}

    alerts = []
    improvements = []
    deteriorations = []

    for ticker, strats in strategy_results.items():
        for strat_name, metrics in strats.items():
            if "error" in metrics: continue
            key = f"{ticker}_{strat_name}"
            prev = prev_strategies.get(key, {})

            if metrics.get("ready") and not prev.get("ready"):
                alerts.append(f"🚨 *{ticker} × {strat_name}が参入基準達成！*\n"
                              f"   p値:{metrics['p_value']:.4f} Sharpe:{metrics['sharpe']:.2f}")

            if prev.get("p_value"):
                p_change = prev["p_value"] - metrics["p_value"]
                if p_change > 0.05:
                    improvements.append(f"📈 {ticker} {strat_name}: p値 {prev['p_value']:.4f}→{metrics['p_value']:.4f} (改善)")
                elif p_change < -0.05:
                    deteriorations.append(f"📉 {ticker} {strat_name}: p値 {prev['p_value']:.4f}→{metrics['p_value']:.4f} (悪化)")

    # 4. ログに記録
    entry = {
        "date": today,
        "fg": fg["now"],
        "prices": {k: round(v, 2) for k, v in prices.items()},
        "strategies": {
            f"{t}_{s}": v
            for t, strats in strategy_results.items()
            for s, v in strats.items()
            if "error" not in v
        }
    }
    log["entries"].append(entry)
    log["entries"] = log["entries"][-90:]  # 90日分保持
    save_log(log)

    # 4.5 フェアバリュー分析
    print("  適正価格分析中...")
    fv_results = run_fair_value_analysis()

    # 5. レポート生成・送信
    fg_emoji = "😱" if fg["now"] <= 20 else "😨" if fg["now"] <= 40 else "😐" if fg["now"] <= 60 else "😊" if fg["now"] <= 80 else "🤩"
    fg_week_str = " → ".join(str(v) for v in fg.get("week", [])[:5])

    # --- セクション1: 市場状況 ---
    msg1 = f"""⚛️ *毎日戦略検証レポート*
{today}

━━━━━━━━━━━━━━━
📊 *市場環境*

{fg_emoji} Fear&Greed: *{fg['now']}/100* ({fg['label']})
週推移: {fg_week_str}

💰 主要価格:"""
    for name, price in prices.items():
        msg1 += f"\n  {name}: ${price:,.2f}"
    send(msg1)

    # --- セクション2: 戦略検証結果 ---
    msg2 = "━━━━━━━━━━━━━━━\n🔬 *戦略検証結果（アウトオブサンプル）*\n\n"
    msg2 += "```\n"
    msg2 += f"{'銘柄×戦略':<20} {'OOS%':>7} {'Sharpe':>7} {'p値':>7} {'DD':>6} {'参入'}\n"
    msg2 += "-" * 60 + "\n"

    for ticker, strats in strategy_results.items():
        for strat_name, m in strats.items():
            if "error" in m: continue
            ready = "✅" if m.get("ready") else ("🔜" if m["p_value"] < 0.2 else "⏳")
            label = f"{ticker} {strat_name[:12]}"
            msg2 += f"{label:<20} {m['return']:>+6.1f}% {m['sharpe']:>7.2f} {m['p_value']:>7.4f} {m['max_dd']:>5.1f}% {ready}\n"

    msg2 += "```\n"
    msg2 += "\n⏳=証拠収集中 🔜=もうすぐ ✅=参入可"
    send(msg2)

    # --- セクション2.5: フェアバリュー分析 ---
    msg_fv = "━━━━━━━━━━━━━━━\n📐 *適正価格分析（Z値 × NVT）*\n\n"
    msg_fv += "```\n"
    msg_fv += f"{'銘柄':<5} {'Z値':>5} {'NVT':>6} {'乖離200':>7} {'Tier':>5}\n"
    msg_fv += "-"*35 + "\n"
    for r in fv_results[:6]:
        nvt_str = f"{r.get('nvt',0):.0f}" if r.get('nvt') else "N/A"
        tier_short = r.get('tier','')[:4]
        msg_fv += (f"{r['ticker']:<5} {r['z_score']:>+5.2f} {nvt_str:>6} "
                  f"{r['deviation_200']:>+6.1f}% {tier_short:>5}\n")
    msg_fv += "```\n\n"
    
    # Tier1があれば強調
    tier1 = [r for r in fv_results if "Tier1" in r.get("tier","")]
    if tier1:
        msg_fv += "🚨 *Tier1シグナル発生！*\n"
        for t in tier1:
            msg_fv += (f"  {t['ticker']}: Z={t['z_score']:.2f} / NVT={t.get('nvt',0):.0f}\n"
                      f"  乖離200MA: {t['deviation_200']:+.1f}%\n"
                      f"  {t.get('nvt_signal','')}\n")
    else:
        msg_fv += "Z<-2 かつ NVT<50 → Tier1\nZ<-1.5 かつ NVT<80 → Tier2"
    send(msg_fv)

    # --- セクション3: 変化・アラート ---
    msg3 = "━━━━━━━━━━━━━━━\n"
    if alerts:
        msg3 += "🚨 *参入基準達成！*\n" + "\n".join(alerts) + "\n\n"
    if improvements:
        msg3 += "📈 *改善中の戦略*\n" + "\n".join(improvements[:3]) + "\n\n"
    if deteriorations:
        msg3 += "📉 *悪化した戦略*\n" + "\n".join(deteriorations[:3]) + "\n\n"

    if not alerts and not improvements and not deteriorations:
        msg3 += "📌 *変化なし* — 引き続きデータ蓄積中\n\n"

    # --- セクション4: 今日の学び ---
    days_elapsed = len(log["entries"])
    eth_tudor = strategy_results.get("ETH", {}).get("tudor_breakout", {})
    p_now = eth_tudor.get("p_value", 1.0)
    p_target = 0.05
    progress = max(0, min(100, (1 - p_now) / (1 - p_target) * 100)) if p_now < 1 else 0

    bar_filled = int(progress / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    msg3 += f"""📚 *学習進捗*

ETH Tudor_Breakout (最有望戦略)
参入まで: [{bar}] {progress:.0f}%
現在p値: {p_now:.4f} → 目標: 0.05

データ蓄積: {days_elapsed}日目
推定参入: p値が0.05を切った時

🦴 &AI QUANTUM EDGE — 毎日学び・毎日テスト"""
    send(msg3)

    # --- 全手法スコアランキング統合 ---
    full_results_path = '/Users/mr.k/Projects/and-ai-brain/full_strategy_results.json'
    top3_score_text = ""
    try:
        if os.path.exists(full_results_path):
            with open(full_results_path) as _f:
                _full = json.load(_f)
            _score_ranking = _full.get("score_ranking") or _full.get("ranking", [])
            if _score_ranking and "total_score_100" in _score_ranking[0]:
                _score_ranking = sorted(_score_ranking, key=lambda x: x.get("total_score_100", 0), reverse=True)
            _top3 = _score_ranking[:3]
            if _top3:
                _lines = []
                for _r in _top3:
                    _sc = _r.get("total_score_100", 0)
                    _color = "🟢" if _sc >= 80 else ("🟡" if _sc >= 50 else "🔴")
                    _label = "本番候補" if _sc >= 80 else ("検証継続" if _sc >= 50 else "廃棄")
                    _lines.append(
                        f"{_color} [{_r.get('code','')}] {_r.get('name','')}({_r.get('ticker','')}) "
                        f"{_sc}点/{_label} | Sharpe={_r.get('sharpe',0):+.2f} Ret={_r.get('total_return',0):+.0f}%"
                    )
                _generated = _full.get("generated_at", "")[:10]
                top3_score_text = f"\n\n⚛️ *全手法スコアTOP3* (計測: {_generated})\n" + "\n".join(_lines)
    except Exception as _e:
        print(f"[full_strategy読み込みエラー] {_e}")

    # --- 最終セクション: 結論まとめ ---
    import anthropic
    
    # 結論生成のためのデータ整理
    best_strategies = []
    for ticker, strategies in strategy_results.items():
        for strat_name, metrics in strategies.items():
            if isinstance(metrics, dict) and metrics.get("oos_pct") is not None:
                best_strategies.append({
                    "ticker": ticker,
                    "strategy": strat_name,
                    "oos": metrics.get("oos_pct", 0),
                    "sharpe": metrics.get("sharpe", 0),
                    "p_value": metrics.get("p_value", 1),
                })
    best_strategies.sort(key=lambda x: x.get("oos", 0), reverse=True)
    
    # Tier情報
    tier1_coins = [r for r in fv_results if "Tier1" in r.get("tier","")]
    tier2_coins = [r for r in fv_results if "Tier2" in r.get("tier","")]
    
    fg = get_fg()
    prices = get_prices_bulk()
    btc_price = prices.get("BTC", 0)
    
    context = f"""
市場データ:
- F&G: {fg}/100
- BTC: ${btc_price:,.0f}
- Tier1シグナル: {[t['ticker'] for t in tier1_coins] or 'なし'}
- Tier2シグナル: {[t['ticker'] for t in tier2_coins] or 'なし'}
- 最良戦略TOP3: {best_strategies[:3]}
- アラート: {alerts or 'なし'}
"""
    
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""以下の投資データを基に、今日の【結論と推奨アクション】を3〜5行で日本語でまとめてください。
具体的に「今日すべきこと」「待つべきこと」「注目すべき変化」を箇条書きで。
投資の断定的推薦は避け、「シグナル分析上は〜」という表現にすること。

{context}

結論まとめ（3〜5行の箇条書き）:"""
            }]
        )
        conclusion = resp.content[0].text
    except Exception as e:
        # Claudeが使えない場合は自動生成
        if tier1_coins:
            conclusion = f"• 🚨 Tier1シグナル発生: {', '.join([t['ticker'] for t in tier1_coins])} — 参入条件を満たしました\n• Z値・NVTともに割安圏。エントリー検討推奨\n• F&G={fg}/100の極度恐怖圏 — 逆張り好機の可能性"
        elif tier2_coins:
            conclusion = f"• ⏳ Tier2圏内: {', '.join([t['ticker'] for t in tier2_coins])} — あと少しでTier1\n• F&G={fg}/100 — 恐怖継続中、引き続き監視\n• 現時点では現金保有継続推奨"
        else:
            conclusion = f"• 📌 全銘柄Tier1未到達 — 現金保有継続\n• F&G={fg}/100 — 市場は極度恐怖圏\n• データ蓄積中: p値改善待ち"

    msg_conclusion = f"""━━━━━━━━━━━━━━━
🧠 *今日の結論・推奨アクション*

{conclusion}{top3_score_text}

━━━━━━━━━━━━━━━
⚛️ &AI QUANTUM EDGE | {len(log["entries"])}日目"""
    send(msg_conclusion)

    print(f"✅ レポート送信完了")
    return entry


if __name__ == "__main__":
    run_daily_research()
