"""
&AI BRAIN - 予測追跡エンジン
前日の予測 vs 実際の結果を記録・検証・精度計算
"""

import json
import os
from datetime import datetime, timedelta

PREDICTIONS_FILE = '/Users/mr.k/Projects/and-ai-brain/prediction_history.json'


def load_history():
    """予測履歴を読み込む"""
    if os.path.exists(PREDICTIONS_FILE):
        with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"predictions": [], "accuracy_stats": {"total": 0, "correct": 0}}


def save_prediction(date_str, predictions_48h, current_prices):
    """今日の予測を保存（明日検証用）"""
    history = load_history()
    
    entry = {
        "date": date_str,
        "predictions": predictions_48h,
        "prices_at_prediction": current_prices,
        "verified": False,
        "results": {}
    }
    
    history["predictions"].append(entry)
    
    # 最新50件だけ保持
    history["predictions"] = history["predictions"][-50:]
    
    with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def verify_predictions(current_prices):
    """未検証の予測を現在価格で検証"""
    history = load_history()
    verified_results = []
    
    for entry in history["predictions"]:
        if entry.get("verified"):
            continue
        
        # 予測から約48時間以上経過しているか確認
        pred_date = datetime.strptime(entry["date"], "%Y/%m/%d %H:%M")
        hours_elapsed = (datetime.now() - pred_date).total_seconds() / 3600
        
        if hours_elapsed < 20:  # 20時間未満はスキップ
            continue
        
        # 各銘柄の予測を検証
        results = {}
        for asset, pred in entry.get("predictions", {}).items():
            if asset not in current_prices or asset not in entry.get("prices_at_prediction", {}):
                continue
            
            old_price = entry["prices_at_prediction"][asset]
            new_price = current_prices[asset]
            actual_change = (new_price - old_price) / old_price * 100
            
            # 予測レンジをパース（例: "+4〜+7%" → min=4, max=7）
            pred_range = pred.get("range", "0〜0%")
            try:
                # パターン: "-5〜+2%" や "+4〜+7%"
                nums = [float(x.replace('%','').replace('+','')) 
                        for x in pred_range.replace('〜', '~').split('~')]
                pred_min, pred_max = min(nums), max(nums)
                
                # 方向性の一致チェック
                pred_direction = "up" if (pred_min + pred_max) / 2 > 0 else "down"
                actual_direction = "up" if actual_change > 0 else "down"
                direction_correct = pred_direction == actual_direction
                
                # レンジ内かチェック
                in_range = pred_min <= actual_change <= pred_max
                
                results[asset] = {
                    "predicted_range": pred_range,
                    "predicted_probability": pred.get("probability", 0),
                    "actual_change": round(actual_change, 2),
                    "direction_correct": direction_correct,
                    "in_range": in_range,
                    "old_price": old_price,
                    "new_price": new_price,
                }
            except:
                results[asset] = {
                    "predicted_range": pred_range,
                    "actual_change": round(actual_change, 2),
                    "direction_correct": False,
                    "in_range": False,
                }
        
        entry["verified"] = True
        entry["verified_at"] = datetime.now().strftime("%Y/%m/%d %H:%M")
        entry["results"] = results
        entry["hours_elapsed"] = round(hours_elapsed, 1)
        
        verified_results.append(entry)
        
        # 統計更新
        for asset, res in results.items():
            history["accuracy_stats"]["total"] += 1
            if res.get("direction_correct"):
                history["accuracy_stats"]["correct"] += 1
    
    # 保存
    with open(PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    return verified_results


def format_verification_report(verified_results, accuracy_stats):
    """検証結果をレポート形式に整形"""
    if not verified_results:
        return ""
    
    total = accuracy_stats.get("total", 0)
    correct = accuracy_stats.get("correct", 0)
    accuracy = (correct / total * 100) if total > 0 else 0
    
    report = f"""
━━━━━━━━━━━━━━━
🎯 *前回予測の結果検証*
累計精度: {accuracy:.0f}% ({correct}/{total}回)
"""
    
    for entry in verified_results[-2:]:  # 最新2件
        pred_date = entry["date"]
        hours = entry.get("hours_elapsed", 0)
        report += f"\n📅 {pred_date} の予測（{hours:.0f}時間後）\n"
        
        for asset, res in entry.get("results", {}).items():
            actual = res["actual_change"]
            predicted = res["predicted_range"]
            direction_ok = res.get("direction_correct", False)
            in_range = res.get("in_range", False)
            
            if in_range:
                icon = "✅"
                judge = "的中！"
            elif direction_ok:
                icon = "🔶"
                judge = "方向性◎"
            else:
                icon = "❌"
                judge = "外れ"
            
            report += f"  {icon} {asset}: 予測{predicted} → 実際{actual:+.1f}% ({judge})\n"
    
    return report


def get_accuracy_summary():
    """精度サマリーを取得"""
    history = load_history()
    stats = history.get("accuracy_stats", {"total": 0, "correct": 0})
    total = stats.get("total", 0)
    correct = stats.get("correct", 0)
    
    if total == 0:
        return {"accuracy": 0, "total": 0, "correct": 0, "message": "まだデータなし"}
    
    accuracy = correct / total * 100
    return {
        "accuracy": round(accuracy, 1),
        "total": total,
        "correct": correct,
        "message": f"{accuracy:.0f}%（{correct}/{total}回的中）"
    }
