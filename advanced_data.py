"""
&AI QUANTUM EDGE - 高度投資データソース
① 経済カレンダー（FX Factory）
② Deribit オプションIV
③ LunarCrush ソーシャル分析
④ Bitcoin ETFフロー
"""

import requests, os, json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")


# ========================================
# ① 経済カレンダー（無料）
# ========================================
def get_economic_calendar():
    """今週・来週の高インパクト経済イベントを取得"""
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            timeout=10
        )
        if r.status_code != 200:
            return []
        
        events = r.json()
        high_impact = []
        
        for e in events:
            if e.get('impact') != 'High':
                continue
            
            country = e.get('country', '')
            title = e.get('title', '')
            date_str = e.get('date', '')
            time_str = e.get('time', '')
            
            # 投資に直接影響するイベントのみ
            key_events = [
                'Fed', 'FOMC', 'Interest Rate', 'CPI', 'Inflation',
                'NFP', 'Non-Farm', 'GDP', 'Employment', 'Unemployment',
                'PMI', 'Retail Sales', 'Powell'
            ]
            
            if any(kw.lower() in title.lower() for kw in key_events) or country == 'USD':
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    hours_until = (dt - datetime.now().astimezone()).total_seconds() / 3600
                    
                    high_impact.append({
                        'title': title,
                        'country': country,
                        'date': date_str[:10],
                        'time': time_str,
                        'hours_until': round(hours_until, 1),
                        'is_soon': 0 <= hours_until <= 24
                    })
                except:
                    high_impact.append({
                        'title': title,
                        'country': country,
                        'date': date_str[:10],
                        'time': time_str,
                        'hours_until': 999,
                        'is_soon': False
                    })
        
        return sorted(high_impact, key=lambda x: x.get('hours_until', 999))
    
    except Exception as e:
        return []


def format_calendar_section(events):
    """経済カレンダーセクションをフォーマット"""
    if not events:
        return ""
    
    section = "\n━━━━━━━━━━━━━━━\n"
    section += "📅 *重要経済イベント*\n"
    
    soon = [e for e in events if e.get('is_soon')]
    upcoming = [e for e in events if not e.get('is_soon')][:3]
    
    if soon:
        section += "\n⚠️ *24時間以内:*\n"
        for e in soon:
            section += f"  🔴 *{e['title']}* ({e['country']})\n"
            section += f"     {e['date']} {e['time']} → {e['hours_until']:.0f}時間後\n"
            section += f"     → ポジションサイズを縮小推奨\n"
    
    if upcoming:
        section += "\n📋 *今週の注目:*\n"
        for e in upcoming:
            section += f"  • {e['title']} ({e['date']})\n"
    
    return section


# ========================================
# ② Deribit オプションIV（無料）
# ========================================
def get_deribit_iv():
    """BTCオプション市場のIV（ボラティリティ指数）を取得"""
    try:
        # 現在のBTC価格
        r = requests.get(
            "https://www.deribit.com/api/v2/public/get_index_price",
            params={"index_name": "btc_usd"},
            timeout=10
        )
        btc_price = 0
        if r.status_code == 200:
            btc_price = float(r.json().get("result", {}).get("index_price", 0))
        
        # 30日IV
        r2 = requests.get(
            "https://www.deribit.com/api/v2/public/get_historical_volatility",
            params={"currency": "BTC"},
            timeout=10
        )
        
        iv_30d = 0
        if r2.status_code == 200:
            vol_data = r2.json().get("result", [])
            if vol_data and isinstance(vol_data[-1], list):
                iv_30d = float(vol_data[-1][1])
        
        # IV解釈
        if iv_30d > 100:
            signal = "🔴 超高ボラ → 大暴落/暴騰の可能性"
            action = "ポジション縮小・様子見"
        elif iv_30d > 80:
            signal = "🟠 高ボラ → 大きな動き予兆"
            action = "ポジションサイズを50%に縮小"
        elif iv_30d > 60:
            signal = "🟡 中ボラ → 通常より変動大きい"
            action = "通常通り（注意して）"
        else:
            signal = "🟢 低ボラ → 安定相場"
            action = "通常エントリー可能"
        
        return {
            "iv_30d": round(iv_30d, 1),
            "signal": signal,
            "action": action,
            "btc_price": btc_price
        }
    
    except Exception as e:
        return None


def format_iv_section(iv_data):
    """IVセクションをフォーマット"""
    if not iv_data:
        return ""
    
    iv = iv_data.get("iv_30d", 0)
    section = "\n━━━━━━━━━━━━━━━\n"
    section += "📊 *Deribit オプション IV*\n\n"
    section += f"BTC 30日IV: *{iv:.1f}%*\n"
    section += f"{iv_data['signal']}\n"
    section += f"推奨: _{iv_data['action']}_\n"
    
    return section


# ========================================
# ③ ETFフロー（代替ソース）
# ========================================
def get_etf_flow():
    """Bitcoin ETFフロー（CoinGlassから取得）"""
    try:
        cg_key = os.environ.get("COINGLASS_API_KEY", "")
        
        # CoinglassのETF流入データ
        r = requests.get(
            "https://open-api-v3.coinglass.com/api/bitcoin/etf/flow",
            headers={"CG-API-KEY": cg_key},
            timeout=10
        )
        
        if r.status_code == 200 and r.json().get('code') == '0':
            data = r.json().get('data', {})
            return {
                'total_flow': data.get('totalFlow', 0),
                'signal': '✅ ETFデータ取得成功'
            }
        
        # 代替: CoinGeckoからBTC ETF関連データ
        cg_key2 = os.environ.get("COINGECKO_API_KEY", "")
        r2 = requests.get(
            "https://api.coingecko.com/api/v3/coins/bitcoin",
            headers={"x-cg-demo-api-key": cg_key2},
            params={"localization": "false", "tickers": "false",
                   "market_data": "true", "community_data": "false"},
            timeout=10
        )
        
        if r2.status_code == 200:
            d = r2.json()
            md = d.get("market_data", {})
            return {
                "price_change_7d": md.get("price_change_percentage_7d", 0),
                "price_change_30d": md.get("price_change_percentage_30d", 0),
                "ath_change": md.get("ath_change_percentage", {}).get("usd", 0),
                "total_volume": md.get("total_volume", {}).get("usd", 0),
            }
    except:
        return None


def get_all_advanced_data():
    """全高度データを取得"""
    print("  📅 経済カレンダー取得中...")
    calendar = get_economic_calendar()
    
    print("  📊 Deribit IV取得中...")
    iv_data = get_deribit_iv()
    
    print("  💰 ETFフロー取得中...")
    etf_data = get_etf_flow()
    
    return {
        'calendar': calendar,
        'iv_data': iv_data,
        'etf_data': etf_data
    }


def format_advanced_section(data):
    """全高度データをフォーマット"""
    section = ""
    
    # IV（ボラティリティ）
    if data.get('iv_data'):
        section += format_iv_section(data['iv_data'])
    
    # 経済カレンダー
    if data.get('calendar'):
        section += format_calendar_section(data['calendar'])
    
    return section


if __name__ == "__main__":
    print("⚛️ 高度投資データ取得テスト\n")
    
    # 経済カレンダー
    print("① 経済カレンダー:")
    events = get_economic_calendar()
    print(f"  重要イベント: {len(events)}件")
    for e in events[:5]:
        soon = "⚠️ 24時間以内！" if e.get('is_soon') else ""
        print(f"  {e['date']} {e['title']} ({e['country']}) {soon}")
    
    # Deribit IV
    print(f"\n② Deribit BTC IV:")
    iv = get_deribit_iv()
    if iv:
        print(f"  30日IV: {iv['iv_30d']}%")
        print(f"  {iv['signal']}")
        print(f"  推奨: {iv['action']}")
    
    # レポートセクション
    data = {'calendar': events, 'iv_data': iv, 'etf_data': None}
    print("\n=== レポートプレビュー ===")
    print(format_advanced_section(data))
