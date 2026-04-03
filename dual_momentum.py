#!/usr/bin/env python3
"""
&AI デュアルモメンタム 月次判定システム
目標: CAGR 8〜15% / DD -20%以内
対象: SPY / EFA / AGG
最適パラメータ: lookback=12M (バックテスト: CAGR=8.15%, DD=-19.7%)
"""
import os, json, requests
from datetime import datetime, date
import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN") or os.environ.get("QE_COMMAND_BOT_TOKEN")
CHAT_ID = "5791086501"
STATE_FILE = "/Users/mr.k/Projects/and-ai-brain/dual_momentum_state.json"

# 最適パラメータ（バックテスト結果: LB=12M, CAGR=8.15%, DD=-19.7%）
LOOKBACK_MONTHS = 12


def send(msg):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ Telegram送信エラー: {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "current_holding": None,
        "entry_date": None,
        "entry_price": {},
        "history": [],
        "total_return": 1.0,
        "peak": 1.0
    }


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def get_signal(lookback=12):
    """デュアルモメンタム判定"""
    raw = yf.download(
        ["SPY", "EFA", "AGG"],
        period=f"{lookback + 3}mo",
        auto_adjust=True,
        progress=False
    )
    monthly = raw["Close"].resample("ME").last()
    ret_nm = monthly.pct_change(lookback)

    latest = ret_nm.iloc[-1]
    spy_ret = float(latest["SPY"]) if not pd.isna(latest["SPY"]) else 0
    efa_ret = float(latest["EFA"]) if not pd.isna(latest["EFA"]) else 0

    # 現在価格
    prices = {t: float(monthly[t].iloc[-1]) for t in ["SPY", "EFA", "AGG"]}

    # 判定ロジック
    if spy_ret > 0:
        signal = "SPY" if spy_ret >= efa_ret else "EFA"
        reason = f"SPY {spy_ret*100:+.1f}% vs EFA {efa_ret*100:+.1f}%（強気相場）"
    else:
        signal = "AGG"
        reason = f"SPY {spy_ret*100:+.1f}%（弱気相場 → 債券待避）"

    return signal, reason, spy_ret, efa_ret, prices


def run_monthly_check():
    state = load_state()
    signal, reason, spy_ret, efa_ret, prices = get_signal(LOOKBACK_MONTHS)

    prev = state.get("current_holding")

    if signal == prev:
        action = "継続"
        trade_needed = False
    else:
        action = f"{prev or 'なし'} → {signal} 切替"
        trade_needed = True

    now = datetime.now().strftime("%Y/%m/%d")
    history = state.get("history", [])

    # 操作手順セクション
    if trade_needed:
        ops_section = f"""━━━━━━━━━━━━━━━
🔄 *操作手順*
1\\. {prev or 'なし'} を全売り
2\\. {signal} を購入（全資金）"""
    else:
        ops_section = ""

    msg = f"""⚛️ *デュアルモメンタム 月次判定*
{now}

━━━━━━━━━━━━━━━
📊 {LOOKBACK_MONTHS}ヶ月リターン:
  SPY: {spy_ret*100:+.1f}%
  EFA: {efa_ret*100:+.1f}%

━━━━━━━━━━━━━━━
📌 今月の判定: *{signal}*
理由: {reason}

アクション: {action}
{"🔄 売買必要！" if trade_needed else "✅ 取引不要"}

━━━━━━━━━━━━━━━
💰 現在価格:
  SPY: ${prices['SPY']:.2f}
  EFA: ${prices['EFA']:.2f}
  AGG: ${prices['AGG']:.2f}
{ops_section}
━━━━━━━━━━━━━━━
📈 バックテスト実績 (LB={LOOKBACK_MONTHS}M):
  CAGR: 8.15% | 最大DD: \\-19.7%

🦴 &AI QUANTUM EDGE | デュアルモメンタム"""

    send(msg)

    # 状態更新
    state["current_holding"] = signal
    state["last_check"] = now
    history.append({
        "date": now,
        "signal": signal,
        "spy_ret": round(spy_ret, 4),
        "efa_ret": round(efa_ret, 4)
    })
    state["history"] = history[-24:]  # 直近24ヶ月
    save_state(state)

    print(f"✅ 判定完了: {signal} ({reason})")
    if trade_needed:
        print(f"🔄 売買アクション必要: {action}")
    return signal


if __name__ == "__main__":
    run_monthly_check()
