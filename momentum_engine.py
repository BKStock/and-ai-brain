"""
&AI QUANTUM EDGE - モメンタムエンジン
各銘柄のモメンタムスコア（0〜100）を計算
"""

import yfinance as yf
import numpy as np
from datetime import datetime


def calculate_momentum_score(ticker: str, name: str) -> dict:
    """
    モメンタムスコアを計算
    
    指標:
    ① 価格モメンタム（20日/60日）: 40点
    ② 出来高モメンタム（急増度）: 30点
    ③ トレンド一貫性（ボラ調整後）: 30点
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='90d')
        
        if len(hist) < 20:
            return {"name": name, "score": 0, "signal": "データ不足", "trend": "unknown"}
        
        close = hist['Close']
        volume = hist['Volume']
        
        # ① 価格モメンタム（40点）
        # 20日モメンタム
        mom_20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100
        # 60日モメンタム
        mom_60 = (close.iloc[-1] / close.iloc[min(-60, -len(close))] - 1) * 100 if len(close) >= 60 else mom_20
        
        # スコア化: +20%以上で満点、-20%以下で0点
        score_20 = min(max((mom_20 + 20) / 40 * 20, 0), 20)
        score_60 = min(max((mom_60 + 20) / 40 * 20, 0), 20)
        price_score = score_20 + score_60
        
        # ② 出来高モメンタム（30点）
        # 直近5日の出来高 vs 過去30日平均
        if len(volume) >= 30 and volume.mean() > 0:
            recent_vol = volume.iloc[-5:].mean()
            avg_vol = volume.iloc[-30:].mean()
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
            # 2倍以上で満点
            vol_score = min((vol_ratio - 0.5) / 1.5 * 30, 30)
            vol_score = max(vol_score, 0)
        else:
            vol_score = 15  # データなしの場合は中間値
        
        # ③ トレンド一貫性（30点）
        # 直近20日で上昇した日数の割合
        daily_returns = close.pct_change().iloc[-20:]
        up_days = (daily_returns > 0).sum()
        consistency = up_days / len(daily_returns)
        trend_score = consistency * 30
        
        # 合計スコア
        total_score = price_score + vol_score + trend_score
        total_score = min(max(int(total_score), 0), 100)
        
        # シグナル判定
        if total_score >= 75:
            signal = "🔥 急上昇中"
            trend = "up"
            arrows = "▲▲▲"
        elif total_score >= 60:
            signal = "📈 上昇トレンド"
            trend = "up"
            arrows = "▲▲"
        elif total_score >= 45:
            signal = "→ 横ばい"
            trend = "neutral"
            arrows = "→"
        elif total_score >= 30:
            signal = "📉 下降気味"
            trend = "down"
            arrows = "▼"
        else:
            signal = "⚠️ 下降トレンド"
            trend = "down"
            arrows = "▼▼"
        
        # 24時間変化
        change_24h = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
        
        return {
            "name": name,
            "ticker": ticker,
            "score": total_score,
            "signal": signal,
            "trend": trend,
            "arrows": arrows,
            "change_24h": round(change_24h, 2),
            "mom_20d": round(mom_20, 1),
            "mom_60d": round(mom_60, 1),
        }
        
    except Exception as e:
        return {
            "name": name,
            "ticker": ticker,
            "score": 0,
            "signal": "取得エラー",
            "trend": "unknown",
            "arrows": "?",
            "change_24h": 0,
        }


def get_all_momentum_scores():
    """全16銘柄のモメンタムスコアを取得"""
    
    tickers = {
        # ⚡ 仮想通貨（HL + dYdX）
        'BTC-USD': 'BTC', 'ETH-USD': 'ETH', 'TRX-USD': 'TRX',
        'SOL-USD': 'SOL', 'XRP-USD': 'XRP', 'TON-USD': 'TON',
        # 🤖 AI×テック株（Hyperliquid perp）
        'NVDA': 'NVDA', 'MSFT': 'MSFT', 'ARM': 'ARM', 'AMD': 'AMD',
        # 🎰 iGaming（Hyperliquid perp）
        'LVS': 'LVS', 'MLCO': 'MLCO', 'DKNG': 'DKNG',
        # 🌏 ASEAN
        'SE': 'SEA', 'GRAB': 'GRAB',
        # 🛡️ 安全資産
        'GC=F': 'Gold',
        # 📊 SPY代替（dYdX SPX / S&P500連動）
        '^GSPC': 'SPX',   # S&P500指数（Yahoo Finance）
        # 🌍 EFA代替（先進国株代替 = MSFT+ARM+AMD でカバー済み）
        # 💵 AGG代替（債券代替 = Gold + USDT保有でカバー）
    }
    
    scores = []
    for ticker, name in tickers.items():
        result = calculate_momentum_score(ticker, name)
        scores.append(result)
    
    # スコア順にソート
    scores.sort(key=lambda x: x['score'], reverse=True)
    return scores


def format_momentum_section(scores):
    """モメンタムセクションをフォーマット"""
    
    top3 = scores[:3]  # スコア上位3銘柄
    bottom3 = [s for s in scores if s['score'] < 35][:2]  # スコア低下注意
    
    section = "━━━━━━━━━━━━━━━\n"
    section += "🔥 *モメンタムランキング*\n\n"
    
    section += "📈 上昇勢いTop3:\n"
    for i, s in enumerate(top3, 1):
        medal = ["🥇", "🥈", "🥉"][i-1]
        section += f"  {medal} {s['name']:5s} {s['score']}点 {s['arrows']} ({s['change_24h']:+.1f}%)\n"
    
    if bottom3:
        section += "\n⚠️ 下降注意:\n"
        for s in bottom3:
            section += f"  ▼ {s['name']:5s} {s['score']}点 {s['arrows']} ({s['change_24h']:+.1f}%)\n"
    
    return section


if __name__ == "__main__":
    print("モメンタムスコア計算中...")
    scores = get_all_momentum_scores()
    
    print("\n🔥 &AI QUANTUM EDGE モメンタムランキング\n")
    for s in scores:
        bar = "█" * (s['score'] // 10)
        print(f"  {s['name']:6s}: {s['score']:3d}点 {bar:10s} {s['arrows']} {s['signal']}")
