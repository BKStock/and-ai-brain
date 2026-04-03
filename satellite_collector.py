"""
&AI QUANTUM EDGE - 衛星・気象データ収集エンジン
NASA POWER API 無料版
"""

import requests, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

# 世界の主要農業・エネルギー地点
LOCATIONS = {
    "🌽 シカゴ（コーン/大豆）":    {"lat": 41.85,  "lon": -87.65,  "type": "agriculture"},
    "🍬 ブラジル（砂糖/大豆）":    {"lat": -23.55, "lon": -46.63,  "type": "agriculture"},
    "🇵🇭 フィリピン（砂糖/コプラ）": {"lat": 14.5,   "lon": 121.0,   "type": "agriculture"},
    "🛢️ サウジ（原油）":           {"lat": 24.68,  "lon": 46.72,   "type": "energy"},
    "☀️ カリフォルニア（太陽光）":  {"lat": 36.7,   "lon": -119.7,  "type": "solar"},
    "💨 北欧（風力）":             {"lat": 55.6,   "lon": 12.6,    "type": "wind"},
}

def get_nasa_power_data(lat, lon, days=30):
    """NASA POWER APIからデータ取得"""
    end = datetime.now()
    start = end - timedelta(days=days)
    
    r = requests.get(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        params={
            "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN,WS2M,RH2M",
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON"
        },
        timeout=20
    )
    
    if r.status_code == 200:
        return r.json().get("properties", {}).get("parameter", {})
    return {}


def calculate_anomaly_score(current_values, historical_avg):
    """現在値 vs 過去平均の異常スコアを計算（-100〜+100）"""
    if not historical_avg or historical_avg == 0:
        return 0
    deviation = (current_values - historical_avg) / abs(historical_avg) * 100
    return round(max(-100, min(100, deviation)), 1)


def get_climate_signals():
    """全地点の気候シグナルを取得・分析"""
    signals = {}
    
    for location, info in LOCATIONS.items():
        try:
            data = get_nasa_power_data(info["lat"], info["lon"], days=60)
            if not data:
                continue
            
            # 気温データ
            temp_data = data.get("T2M", {})
            rain_data = data.get("PRECTOTCORR", {})
            solar_data = data.get("ALLSKY_SFC_SW_DWN", {})
            wind_data = data.get("WS2M", {})
            
            if not temp_data:
                continue
            
            # NASAの欠損値(-999)を除外
            def clean(v_list):
                return [v for v in v_list if v is not None and v > -990]
            
            values = clean(list(temp_data.values()))
            rain_values = clean(list(rain_data.values())) if rain_data else []
            solar_values = clean(list(solar_data.values())) if solar_data else []
            wind_values = clean(list(wind_data.values())) if wind_data else []
            
            if not values:
                continue
            
            # 直近7日 vs 過去30日平均
            recent_temp = sum(values[-7:]) / 7 if len(values) >= 7 else values[-1]
            avg_temp = sum(values[:30]) / min(30, len(values))
            
            recent_rain = sum(rain_values[-7:]) / 7 if len(rain_values) >= 7 else 0
            avg_rain = sum(rain_values[:30]) / min(30, len(rain_values)) if rain_values else 0
            
            # 異常スコア計算
            temp_anomaly = calculate_anomaly_score(recent_temp, avg_temp)
            rain_anomaly = calculate_anomaly_score(recent_rain, avg_rain) if avg_rain > 0 else 0
            
            # 種別ごとの投資シグナル
            location_type = info["type"]
            investment_signal = ""
            signal_score = 0
            
            if location_type == "agriculture":
                if rain_anomaly < -30:  # 干ばつ
                    investment_signal = "⚠️ 干ばつリスク → コモディティ↑"
                    signal_score = 70
                elif rain_anomaly > 50:  # 洪水リスク
                    investment_signal = "⚠️ 洪水リスク → 農業株↓"
                    signal_score = -50
                elif temp_anomaly > 20:  # 異常高温
                    investment_signal = "🌡️ 異常高温 → 冷房需要↑"
                    signal_score = 40
                else:
                    investment_signal = "✅ 正常範囲"
                    signal_score = 0
                    
            elif location_type == "solar":
                solar_recent = sum(solar_values[-7:]) / 7 if len(solar_values) >= 7 else 0
                solar_avg = sum(solar_values[:30]) / min(30, len(solar_values)) if solar_values else 0
                solar_anomaly = calculate_anomaly_score(solar_recent, solar_avg)
                if solar_anomaly > 15:
                    investment_signal = "☀️ 日射量↑ → 太陽光株↑"
                    signal_score = 50
                else:
                    investment_signal = "→ 日射量 正常範囲"
                    signal_score = 0
                    
            elif location_type == "wind":
                wind_recent = sum(wind_values[-7:]) / 7 if len(wind_values) >= 7 else 0
                wind_avg = sum(wind_values[:30]) / min(30, len(wind_values)) if wind_values else 0
                wind_anomaly = calculate_anomaly_score(wind_recent, wind_avg)
                if wind_anomaly > 20:
                    investment_signal = "💨 強風↑ → 風力発電↑"
                    signal_score = 45
                else:
                    investment_signal = "→ 風速 正常範囲"
                    signal_score = 0
                    
            elif location_type == "energy":
                if temp_anomaly > 15:
                    investment_signal = "🌡️ 高温 → 冷房需要↑ → エネルギー↑"
                    signal_score = 35
                else:
                    investment_signal = "→ 気温 正常範囲"
                    signal_score = 0
            
            signals[location] = {
                "temp_c": round(recent_temp, 1),
                "temp_anomaly": temp_anomaly,
                "rain_mm": round(recent_rain, 1),
                "rain_anomaly": rain_anomaly,
                "signal": investment_signal,
                "signal_score": signal_score,
                "type": location_type
            }
            
        except Exception as e:
            pass
    
    return signals


def calculate_climate_economy_score(signals):
    """気候シグナルを世界経済スコアに変換（-30〜+30の補正値）"""
    if not signals:
        return 0, []
    
    total_score = 0
    key_signals = []
    
    for location, data in signals.items():
        score = data.get("signal_score", 0)
        total_score += score
        signal = data.get("signal", "")
        if abs(score) >= 35:
            key_signals.append(f"{location}: {signal}")
    
    # -30〜+30に正規化
    normalized = max(-30, min(30, total_score / len(signals) * 0.5))
    return round(normalized, 1), key_signals


def format_climate_section(signals):
    """気候セクションをレポート用にフォーマット"""
    if not signals:
        return ""
    
    section = "\n━━━━━━━━━━━━━━━\n"
    section += "🛰️ *衛星気候データ*\n\n"
    
    alerts = [(loc, data) for loc, data in signals.items() 
              if abs(data.get("signal_score", 0)) >= 35]
    normal = [(loc, data) for loc, data in signals.items() 
              if abs(data.get("signal_score", 0)) < 35]
    
    if alerts:
        section += "⚠️ *注意シグナル:*\n"
        for loc, data in alerts:
            section += f"  {data['signal']}\n"
            section += f"  {loc}: 気温{data['temp_c']}℃ ({data['temp_anomaly']:+.0f}%) 降水{data['rain_mm']}mm ({data['rain_anomaly']:+.0f}%)\n"
    
    if normal:
        section += "✅ *正常範囲:*\n"
        for loc, data in normal[:3]:
            section += f"  {loc}: {data['temp_c']}℃\n"
    
    return section


if __name__ == "__main__":
    print("🛰️ NASA POWER 気候データ収集中...")
    print("（世界6地点 × 60日分 = 約30秒かかります）\n")
    
    signals = get_climate_signals()
    climate_score, key_signals = calculate_climate_economy_score(signals)
    
    print(f"🌍 気候経済スコア補正: {climate_score:+.1f}")
    print(f"\n📊 地点別シグナル:")
    for loc, data in signals.items():
        print(f"  {loc}")
        print(f"    気温: {data['temp_c']}℃ ({data['temp_anomaly']:+.0f}%異常) 降水: {data['rain_mm']}mm")
        print(f"    → {data['signal']}")
    
    if key_signals:
        print(f"\n⚠️ 重要シグナル:")
        for s in key_signals:
            print(f"  {s}")
    
    print(f"\n✅ 完了！世界経済スコアに{climate_score:+.1f}ポイント補正")
