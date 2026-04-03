#!/usr/bin/env python3
"""&AI 決算アラートシステム"""
import os, requests, json
import pandas as pd
from datetime import datetime as dt, timedelta, date
import yfinance as yf
from dotenv import load_dotenv

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')
BOT = os.environ.get("QE_REPORT_BOT_TOKEN") or os.environ.get("QE_COMMAND_BOT_TOKEN")
CHAT_ID = "5791086501"

TARGETS = {
    # 元の14銘柄
    "AAPL": "Apple", "GOOGL": "Google", "TSM": "TSMC",
    "NVDA": "NVIDIA", "AVGO": "Broadcom", "ARM": "ARM Holdings",
    "MSFT": "Microsoft", "META": "Meta", "AMZN": "Amazon",
    "AMD": "AMD", "ASML": "ASML", "V": "Visa",
    "JPM": "JPMorgan", "LLY": "Eli Lilly",
    # 10年バックテスト追加（全19銘柄）
    "WMT": "Walmart",        # 1位 PF=10.8
    "KLAC": "KLA Corp",      # 3位 PF=5.3
    "GS": "Goldman Sachs",   # 4位 PF=5.5
    "MS": "Morgan Stanley",  # 5位 PF=5.3
    "LRCX": "Lam Research",  # 6位
    "BLK": "BlackRock",      # 7位
    "BAC": "BofA",           # 8位
    "NFLX": "Netflix",       # 9位
    "MU": "Micron",          # 10位
    "INTC": "Intel",         # 11位
}

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def run():
    today = dt.now().date()
    print(f"決算アラートチェック: {today}")
    
    alerts_tomorrow = []
    alerts_today = []
    alerts_week = []
    
    for ticker, name in TARGETS.items():
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None:
                continue
            
            # 決算日を取得
            earn_col = None
            if hasattr(cal, 'columns') and "Earnings Date" in cal.columns:
                earn_col = cal["Earnings Date"]
            elif hasattr(cal, 'index') and "Earnings Date" in cal.index:
                earn_col = cal.loc["Earnings Date"]
            
            if earn_col is None:
                continue
            
            dates_to_check = earn_col if hasattr(earn_col, '__iter__') else [earn_col]
            
            for ed in dates_to_check:
                try:
                    ed_date = pd.to_datetime(ed).date()
                    delta = (ed_date - today).days
                    if delta == 0:
                        alerts_today.append((ticker, name, ed_date))
                    elif delta == 1:
                        alerts_tomorrow.append((ticker, name, ed_date))
                    elif 2 <= delta <= 7:
                        alerts_week.append((ticker, name, ed_date, delta))
                except: pass
        except Exception as e:
            print(f"  {ticker}: {e}")
    
    messages = []
    
    if alerts_today:
        msg = "🔔 *本日 決算発表！*\n\n"
        for ticker, name, d in alerts_today:
            msg += f"• *{ticker}*（{name}）\n"
            msg += f"  → 終値確認後 +3%以上で *ME1エントリー検討！*\n"
        messages.append(msg)
    
    if alerts_tomorrow:
        msg = "📅 *明日 決算発表予定*\n\n"
        for ticker, name, d in alerts_tomorrow:
            try:
                price = yf.Ticker(ticker).info.get("currentPrice", 0)
                msg += f"• *{ticker}*（{name}）現在 ${price:.2f}\n"
            except:
                msg += f"• *{ticker}*（{name}）\n"
        msg += "\n⚡ 発表後 +3%超なら *60日保有 ME1戦略* 発動！\n"
        msg += "実績 Sharpe: AAPL=4.08 / TSM=4.51 / GOOGL=4.32"
        messages.append(msg)
    
    if alerts_week:
        msg = "📆 *今週の決算予定*\n\n"
        for item in sorted(alerts_week, key=lambda x: x[3]):
            ticker, name, d, delta = item
            msg += f"• *{ticker}*（{name}）{d}（あと{delta}日）\n"
        messages.append(msg)
    
    if messages:
        for m in messages:
            send(m)
        print(f"✅ {len(messages)}件の通知送信")
    else:
        print("本日・明日・今週の決算なし")
        # 月曜のみ週次サマリー
        if dt.now().weekday() == 0:
            send("📆 *今週の主要決算*\n\n対象銘柄の決算は今週なし\n来週以降を待機中🦴")

if __name__ == "__main__":
    run()
