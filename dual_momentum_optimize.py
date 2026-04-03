#!/usr/bin/env python3
"""
デュアルモメンタム パラメータ最適化バックテスト
対象: SPY / EFA / AGG
期間: 2006-01-31 〜 2024-12-31
"""
import yfinance as yf
import pandas as pd
import numpy as np
import json
from itertools import product

# データ取得
print("📥 データ取得中...")
raw = yf.download(["SPY","EFA","AGG"], start="2005-01-01", end="2025-01-31",
                  auto_adjust=True, progress=False)
monthly = raw["Close"].resample("ME").last()
print(f"✅ データ取得完了: {monthly.index[0].date()} 〜 {monthly.index[-1].date()}")

results = []

# パラメータグリッドサーチ
lookback_months = [6, 9, 12, 18, 24]  # モメンタム計測期間

print("\n🔍 グリッドサーチ開始...")

# hold=1（毎月リバランス）のみ実装
for lb in lookback_months:
    ret_nm = monthly.pct_change(lb)

    sig = ret_nm.shift(1).loc["2006-01-31":"2024-12-31"]
    mret = monthly.pct_change().loc["2006-01-31":"2024-12-31"]

    holdings = []
    for _, r in sig.iterrows():
        if pd.isna(r["SPY"]):
            holdings.append("AGG")
        elif r["SPY"] > 0:
            holdings.append("SPY" if r["SPY"] >= r["EFA"] else "EFA")
        else:
            holdings.append("AGG")

    strat = pd.Series(
        [float(mret.loc[d, h]) for d, h in zip(sig.index, holdings)],
        index=sig.index
    )
    cum = (1 + strat).cumprod()
    years = len(strat) / 12
    cagr = cum.iloc[-1] ** (1 / years) - 1
    maxdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = (strat.mean() - 0.02 / 12) / strat.std() * np.sqrt(12)

    result = {
        "lookback": lb,
        "hold": 1,
        "cagr": round(cagr * 100, 2),
        "maxdd": round(maxdd * 100, 2),
        "sharpe": round(sharpe, 3),
        "mult": round(cum.iloc[-1], 2)
    }
    results.append(result)
    print(f"  LB={lb:2d}M: CAGR={cagr*100:.1f}% DD={maxdd*100:.1f}% Sharpe={sharpe:.2f} {cum.iloc[-1]:.1f}倍")

# スコアリング: DDが-25%以内でCAGRが最大のものを選ぶ
valid = [r for r in results if r["maxdd"] > -25]
best = None
if valid:
    best = max(valid, key=lambda x: x["cagr"])
    print(f"\n🏆 最適パラメータ (DD≤25%制約): lookback={best['lookback']}M")
    print(f"   CAGR: {best['cagr']}% | DD: {best['maxdd']}% | Sharpe: {best['sharpe']}")
else:
    # 制約緩和: DDが-35%以内
    valid2 = [r for r in results if r["maxdd"] > -35]
    if valid2:
        best = max(valid2, key=lambda x: x["cagr"])
        print(f"\n🏆 最適パラメータ (DD≤35%制約): lookback={best['lookback']}M")
        print(f"   CAGR: {best['cagr']}% | DD: {best['maxdd']}% | Sharpe: {best['sharpe']}")

# 全結果を表示
print("\n📊 全結果ランキング (CAGR順):")
results.sort(key=lambda x: x["cagr"], reverse=True)
for i, r in enumerate(results):
    mark = "★" if best and r["lookback"] == best["lookback"] else " "
    print(f"  {mark} [{i+1}] LB={r['lookback']:2d}M: CAGR={r['cagr']:.1f}% DD={r['maxdd']:.1f}% Sharpe={r['sharpe']:.2f} {r['mult']:.1f}倍")

# 結果をJSONで保存
output = {
    "best": best,
    "all_results": results
}
out_path = "/Users/mr.k/Projects/and-ai-brain/dual_momentum_optimize_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n💾 結果保存: {out_path}")

if best:
    print(f"\n✅ 推奨: LOOKBACK_MONTHS = {best['lookback']}")
