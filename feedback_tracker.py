"""
&AI QUANTUM EDGE - フィードバック追跡エンジン
👍/👎 ボタン + 月次精度レポート
"""

import json
import os
import requests
from datetime import datetime, date
from calendar import monthrange

from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

FEEDBACK_FILE = '/Users/mr.k/Projects/and-ai-brain/feedback_history.json'
BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")


def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "daily_feedback": [],
        "monthly_stats": {},
        "total_helpful": 0,
        "total_not_helpful": 0
    }


def save_feedback(data):
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_feedback_buttons(report_date: str):
    """レポートの末尾に👍/👎ボタンを送信"""
    
    msg = f"""━━━━━━━━━━━━━━━
💬 *今日のシグナルは役立ちましたか？*
{report_date} のレポート

あなたのフィードバックが
&AI QUANTUM EDGEを進化させます 🔥"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "👍 役立った！",
                    "callback_data": f"feedback:helpful:{report_date}"
                },
                {
                    "text": "👎 イマイチ",
                    "callback_data": f"feedback:not_helpful:{report_date}"
                }
            ]]
        }
    })
    return resp.status_code == 200


def record_feedback(date_str: str, is_helpful: bool):
    """フィードバックを記録"""
    data = load_feedback()
    
    # 既存のエントリを確認
    existing = next(
        (f for f in data["daily_feedback"] if f["date"] == date_str),
        None
    )
    
    if existing:
        existing["helpful"] = is_helpful
        existing["updated_at"] = datetime.now().strftime("%Y/%m/%d %H:%M")
    else:
        data["daily_feedback"].append({
            "date": date_str,
            "helpful": is_helpful,
            "recorded_at": datetime.now().strftime("%Y/%m/%d %H:%M")
        })
    
    # 集計更新
    data["total_helpful"] = sum(1 for f in data["daily_feedback"] if f.get("helpful"))
    data["total_not_helpful"] = sum(1 for f in data["daily_feedback"] if not f.get("helpful"))
    
    save_feedback(data)
    return True


def get_monthly_stats(year: int, month: int):
    """月次統計を計算"""
    data = load_feedback()
    month_str = f"{year}-{month:02d}"
    
    monthly = [
        f for f in data["daily_feedback"]
        if f["date"].startswith(month_str)
    ]
    
    if not monthly:
        return None
    
    helpful = sum(1 for f in monthly if f.get("helpful"))
    total = len(monthly)
    feedback_rate = helpful / total * 100 if total > 0 else 0
    
    # 予測精度（prediction_trackerから）
    from prediction_tracker import load_history, get_accuracy_summary
    accuracy = get_accuracy_summary()
    
    return {
        "year": year,
        "month": month,
        "total_reports": total,
        "helpful_count": helpful,
        "not_helpful_count": total - helpful,
        "feedback_rate": round(feedback_rate, 1),
        "accuracy": accuracy
    }


def get_win_rate():
    """勝率を計算（予測が的中した方向性の割合）"""
    from prediction_tracker import load_history
    history = load_history()
    
    verified = [
        p for p in history.get("predictions", [])
        if p.get("verified") and p.get("results")
    ]
    
    if not verified:
        return {"win_rate": 0, "total": 0, "wins": 0, "message": "データ蓄積中"}
    
    total = 0
    wins = 0
    in_range_count = 0
    
    for pred in verified:
        for asset, result in pred["results"].items():
            total += 1
            if result.get("direction_correct"):
                wins += 1
            if result.get("in_range"):
                in_range_count += 1
    
    win_rate = wins / total * 100 if total > 0 else 0
    range_rate = in_range_count / total * 100 if total > 0 else 0
    
    return {
        "win_rate": round(win_rate, 1),
        "range_rate": round(range_rate, 1),
        "total": total,
        "wins": wins,
        "in_range": in_range_count,
        "message": f"{win_rate:.0f}%（{wins}/{total}回的中）"
    }


def send_monthly_report(year: int = None, month: int = None):
    """月次精度レポートをTelegramに送信"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    stats = get_monthly_stats(year, month)
    win_rate = get_win_rate()
    feedback_data = load_feedback()
    
    total_helpful = feedback_data.get("total_helpful", 0)
    total_not_helpful = feedback_data.get("total_not_helpful", 0)
    total_feedback = total_helpful + total_not_helpful
    overall_feedback_rate = total_helpful / total_feedback * 100 if total_feedback > 0 else 0
    
    # 前月比計算
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_stats = get_monthly_stats(prev_year, prev_month)
    
    accuracy = win_rate
    prev_accuracy = prev_stats["accuracy"]["accuracy"] if prev_stats else 0
    accuracy_diff = accuracy["win_rate"] - prev_accuracy if prev_stats else 0
    diff_str = f"({'↑' if accuracy_diff >= 0 else '↓'}{abs(accuracy_diff):.1f}%)" if prev_stats else "(初月)"
    
    msg = f"""⚛️ *&AI QUANTUM EDGE 月次レポート*
{year}年{month}月

━━━━━━━━━━━━━━━
🎯 *予測精度レポート*

方向性的中率: *{accuracy['win_rate']}%* {diff_str}
レンジ内的中率: *{accuracy['range_rate']}%*
累計的中回数: *{accuracy['wins']}/{accuracy['total']}回*

先月比: {diff_str}

━━━━━━━━━━━━━━━
📊 *勝率内訳*

✅ 方向性◎（上下が合った）: {accuracy['wins']}回
🎯 レンジ内（完全的中）: {accuracy['in_range']}回
❌ 外れ: {accuracy['total'] - accuracy['wins']}回

勝率: *{accuracy['win_rate']}%*
完全的中率: *{accuracy['range_rate']}%*

━━━━━━━━━━━━━━━
💬 *ユーザーフィードバック*

👍 役立った: {total_helpful}回
👎 イマイチ: {total_not_helpful}回
満足度スコア: *{overall_feedback_rate:.0f}%*

━━━━━━━━━━━━━━━
💰 *精度連動価格（現在）*"""

    # 精度に基づく現在価格を計算
    wr = accuracy['win_rate']
    if wr < 60:
        price = "無料（精度向上中）"
        price_reason = "60%未満: 無料フェーズ"
    elif wr < 65:
        price = "$29/月"
        price_reason = "61〜65%"
    elif wr < 70:
        price = "$59/月"
        price_reason = "66〜70%"
    elif wr < 75:
        price = "$99/月"
        price_reason = "71〜75%"
    else:
        price = "$149/月"
        price_reason = "76%以上"

    msg += f"""
現在の精度: {wr}%（{price_reason}）
→ 適正価格: *{price}*

━━━━━━━━━━━━━━━
🔥 来月の目標

精度目標: {min(wr + 3, 80):.0f}%以上
→ 達成で価格: {'$' + str(int(min(wr + 3, 80) * 1.5)) + '/月'}

🦴 *&AI QUANTUM EDGE* | Powered by Quantum AI
※本サービスは情報提供のみです。投資判断はご自身の責任で。"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    })
    return resp.status_code == 200


if __name__ == "__main__":
    # テスト: 今日分のフィードバックボタンを送信
    today = datetime.now().strftime("%Y-%m-%d")
    print("フィードバックボタン送信テスト...")
    result = send_feedback_buttons(today)
    print(f"{'✅ 送信成功' if result else '❌ 送信失敗'}")
