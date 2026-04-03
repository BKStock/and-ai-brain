# Slotenデータ TimesFM予測プロンプト

## 使い方
このプロンプトをClaude/GPT等のAIに投げると、TimesFMを使った入金予測コードを生成できます。
またはそのまま ~/Projects/and-ai-brain/ で実行可能なPythonスクリプトとして使えます。

---

## AIへの指示プロンプト

```
あなたはPythonの時系列予測エキスパートです。
以下の条件でSlotenオンラインカジノの入金額予測スクリプトを作成してください。

## 使用ライブラリ
- timesfm（Google TimesFM 2.5）
- numpy, pandas

## 入力データ形式
CSVファイル（sloten_deposits.csv）:
```
date,total_deposit_jpy
2026-01-01,1250000
2026-01-02,980000
...
```

## 実行環境
- Python: ~/remote-workspace/timesfm-env/.venv/bin/python3
- TimesFMパス追加: /Users/mr.k/remote-workspace/timesfm-env/.venv/lib/
- スクリプト配置先: ~/Projects/and-ai-brain/sloten_predictor.py

## 予測内容
1. 過去データを読み込む
2. TimesFM 2.5で次の10日間を予測
3. 以下を出力:
   - 日付ごとの予測入金額（中央値）
   - 楽観シナリオ（90%ile）
   - 悲観シナリオ（10%ile）
   - 前週比変化率
   - 入金が最も多い曜日の特定
4. Telegramに予測レポートを送信
   Bot Token: 8653832308:AAFSkIDMcPoZGS5J8A9zbN8KL9o8rAJGLZ4
   Chat ID: 5791086501

## 出力フォーマット（Telegram）
```
📊 Sloten 入金予測レポート
━━━━━━━━━━━━━━━
04/04 (土): ¥1,250,000 (¥1,100K〜¥1,450K)
04/05 (日): ¥1,480,000 (¥1,200K〜¥1,720K) ← 最高
04/06 (月): ¥890,000  (¥780K〜¥1,020K)
...
━━━━━━━━━━━━━━━
10日合計予測: ¥XX,XXX,XXX
最高入金日: 04/05 (日)
最低入金日: 04/08 (水)
━━━━━━━━━━━━━━━
```

## 追加分析
- 過去パターンから「入金が多い曜日TOP3」を抽出
- 前月比の入金トレンド（増加/減少/横ばい）
- 異常値アラート（予測が±30%以上乖離する場合）

コードを生成してください。
```

---

## 直接実行用Pythonテンプレート

```python
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

def load_data(csv_path: str) -> np.ndarray:
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

def predict(model, prices: np.ndarray, horizon: int = 10):
    """入金額を予測"""
    context = prices[-min(90, len(prices)):]
    pf, qf = model.forecast(horizon=horizon, inputs=[context])
    point  = pf[0][:horizon]
    q10    = qf[0][:horizon, 0]
    q50    = qf[0][:horizon, 4]
    q90    = qf[0][:horizon, -1]
    return point, q10, q50, q90

def analyze_patterns(prices: np.ndarray, dates) -> dict:
    """曜日別パターンを分析"""
    df = pd.DataFrame({"date": pd.to_datetime(dates), "amount": prices})
    df["weekday"] = df["date"].dt.day_name()
    weekday_avg = df.groupby("weekday")["amount"].mean().sort_values(ascending=False)
    trend = (prices[-7:].mean() - prices[-14:-7].mean()) / prices[-14:-7].mean() * 100
    return {"top_days": weekday_avg.head(3).to_dict(), "weekly_trend": trend}

def send_telegram(message: str):
    """Telegramにレポートを送信"""
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message},
        timeout=10
    )

def format_report(point, q10, q90, last_date, patterns) -> str:
    """レポートを整形"""
    weekdays_ja = {
        "Monday":"月","Tuesday":"火","Wednesday":"水","Thursday":"木",
        "Friday":"金","Saturday":"土","Sunday":"日"
    }
    lines = ["📊 Sloten 入金予測レポート（TimesFM）", "━━━━━━━━━━━━━━━"]
    
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
        
        peak = " ← 最高" if val == int(max(point)) else ""
        lines.append(f"{date.strftime('%m/%d')}({wd}): ¥{val:,}  (¥{low//1000}K〜¥{high//1000}K){peak}")
    
    lines += [
        "━━━━━━━━━━━━━━━",
        f"10日合計予測: ¥{total:,}",
        f"最高入金日: {max_day} ¥{max_val:,}",
        f"最低入金日: {min_day} ¥{min_val:,}",
        "━━━━━━━━━━━━━━━",
    ]
    
    # 曜日パターン
    top = list(patterns["top_days"].items())[:3]
    trend = patterns["weekly_trend"]
    lines.append("📅 入金多い曜日TOP3:")
    for day, val in top:
        wd = weekdays_ja.get(day, day)
        lines.append(f"  {wd}曜日: ¥{int(val):,}")
    lines.append(f"前週比トレンド: {trend:+.1f}%")
    
    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="入金データCSVのパス")
    args = parser.parse_args()
    
    print("データ読み込み中...")
    prices, dates = load_data(args.csv)
    print(f"✅ {len(prices)}日分のデータ")
    
    print("TimesFMモデルロード中...")
    model = load_model()
    print("✅ モデル準備完了")
    
    print("予測中...")
    point, q10, q50, q90 = predict(model, prices, DAYS_TO_PREDICT)
    patterns = analyze_patterns(prices, dates)
    
    report = format_report(point, q10, q90, dates[-1], patterns)
    print(report)
    print("\nTelegramに送信中...")
    send_telegram(report)
    print("✅ 完了！")
```

---

## 使い方まとめ

1. Slotenの管理画面から入金データをCSVでダウンロード
2. ファイル名を `sloten_deposits.csv` に変更
3. 実行:
```bash
cd ~/Projects/and-ai-brain
python3 sloten_predictor.py --csv sloten_deposits.csv
```
4. Telegramに予測レポートが届く

---

**作成**: ボンズ 2026-04-03
