"""
Sloten入金予測 - TimesFM 2.5使用
使い方: python3 sloten_predictor.py --csv sloten_deposits.csv
"""
import sys, os, numpy as np, pandas as pd
import argparse, requests, json
from datetime import datetime, timedelta

# TimesFM venv を読み込む
VENV = "/Users/mr.k/remote-workspace/timesfm-env/.venv/lib"
for d in os.listdir(VENV):
    sp = os.path.join(VENV, d, "site-packages")
    if os.path.exists(sp) and sp not in sys.path:
        sys.path.insert(0, sp)

import torch, timesfm

TELEGRAM_TOKEN = "8653832308:AAFSkIDMcPoZGS5J8A9zbN8KL9o8rAJGLZ4"
CHAT_ID = "5791086501"
DAYS_TO_PREDICT = 10

def load_data(csv_path: str):
    """CSVから入金データを読み込む"""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df["total_deposit_jpy"].values.astype(np.float32), df["date"].values

def load_model():
    """TimesFM 2.5モデルをロード"""
    import warnings; warnings.filterwarnings('ignore')
    torch.set_float32_matmul_precision("high")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    model.compile(timesfm.ForecastConfig(
        max_context=1024, max_horizon=60,
        normalize_inputs=True, use_continuous_quantile_head=True,
        force_flip_invariance=True, infer_is_positive=True, fix_quantile_crossing=True,
    ))
    return model

def predict(model, prices, horizon=10):
    """入金額を予測"""
    context = prices[-min(90, len(prices)):]
    pf, qf = model.forecast(horizon=horizon, inputs=[context])
    point = pf[0][:horizon]
    q10 = qf[0][:horizon, 0]
    q50 = qf[0][:horizon, 4]
    q90 = qf[0][:horizon, -1]
    return point, q10, q50, q90

def analyze_patterns(prices, dates):
    """曜日別パターンを分析"""
    df = pd.DataFrame({"date": pd.to_datetime(dates), "amount": prices})
    df["weekday"] = df["date"].dt.day_name()
    weekday_avg = df.groupby("weekday")["amount"].mean().sort_values(ascending=False)
    trend = (prices[-7:].mean() - prices[-14:-7].mean()) / prices[-14:-7].mean() * 100
    return {"top_days": weekday_avg.head(3).to_dict(), "weekly_trend": trend}

def send_telegram(message):
    """Telegramにレポートを送信"""
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message},
        timeout=10
    )

def format_report(point, q10, q90, last_date, patterns):
    """レポートを整形"""
    weekdays_ja = {
        "Monday":"月","Tuesday":"火","Wednesday":"水","Thursday":"木",
        "Friday":"金","Saturday":"土","Sunday":"日"
    }
    lines = ["Sloten Deposit Forecast (TimesFM)", "---"]
    
    total = 0
    max_day, max_val = "", 0
    min_day, min_val = "", float("inf")
    
    for i in range(len(point)):
        date = pd.Timestamp(last_date) + timedelta(days=i+1)
        wd = weekdays_ja.get(date.day_name(), "?")
        val = int(point[i])
        low = int(q10[i])
        high = int(q90[i])
        total += val
        if val > max_val: max_val, max_day = val, f"{date.strftime('%m/%d')}({wd})"
        if val < min_val: min_val, min_day = val, f"{date.strftime('%m/%d')}({wd})"
        
        peak = " << Peak" if val == int(max(point)) else ""
        lines.append(f"{date.strftime('%m/%d')}({wd}): Y{val:,} (Y{low//1000}K-Y{high//1000}K){peak}")
    
    lines += [
        "---",
        f"10-Day Total: Y{total:,}",
        f"Highest: {max_day} Y{max_val:,}",
        f"Lowest: {min_day} Y{min_val:,}",
        "---",
    ]
    
    top = list(patterns["top_days"].items())[:3]
    trend = patterns["weekly_trend"]
    lines.append("Top Deposit Days:")
    for day, val in top:
        wd = weekdays_ja.get(day, day)
        lines.append(f"  {wd}: Y{int(val):,}")
    lines.append(f"Weekly Trend: {trend:+.1f}%")
    
    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Deposit data CSV path")
    args = parser.parse_args()
    
    print("Loading data...")
    prices, dates = load_data(args.csv)
    print(f"OK: {len(prices)} days of data")
    
    print("Loading TimesFM model...")
    model = load_model()
    print("OK: Model ready")
    
    print("Predicting...")
    point, q10, q50, q90 = predict(model, prices, DAYS_TO_PREDICT)
    patterns = analyze_patterns(prices, dates)
    
    report = format_report(point, q10, q90, dates[-1], patterns)
    print(report)
    print("\nSending to Telegram...")
    send_telegram(report)
    print("Done!")
