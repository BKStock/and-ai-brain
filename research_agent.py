"""
&AI QUANTUM EDGE - 自律型投資研究エージェント
毎晩2:00に自動実行 → 月利5%以上を目指す
"""

import os, json, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
RESEARCH_LOG = '/Users/mr.k/Projects/and-ai-brain/research_log.json'
PROMPT_FILE = '/Users/mr.k/Projects/and-ai-brain/RESEARCH_AGENT_PROMPT.md'


def load_research_log():
    if os.path.exists(RESEARCH_LOG):
        with open(RESEARCH_LOG) as f:
            return json.load(f)
    return {
        "hypotheses": [],
        "monthly_win_rates": [],
        "score_weights": {
            "momentum": 40, "sentiment": 30,
            "macro": 20, "technical": 10
        },
        "total_trades": 0,
        "winning_trades": 0,
        "last_research": None
    }


def save_research_log(data):
    with open(RESEARCH_LOG, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_current_market_snapshot():
    """今の市場データを全部取得"""
    snapshot = {}
    
    # Fear & Greed
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
        fg = r.json()['data']
        snapshot['fear_greed'] = {
            'current': int(fg[0]['value']),
            'label': fg[0]['value_classification'],
            '7day_values': [int(d['value']) for d in fg]
        }
    except: pass
    
    # CoinGecko
    try:
        cg_key = os.environ.get("COINGECKO_API_KEY","")
        r2 = requests.get("https://api.coingecko.com/api/v3/global",
            headers={"x-cg-demo-api-key": cg_key}, timeout=10)
        g = r2.json()['data']
        snapshot['market'] = {
            'btc_dominance': round(g['market_cap_percentage']['btc'], 1),
            'total_mc_trillion': round(g['total_market_cap']['usd']/1e12, 2),
            'mc_change_24h': round(g['market_cap_change_percentage_24h_usd'], 2)
        }
    except: pass
    
    # Coinglass Bubble Index
    try:
        cg_gl = os.environ.get("COINGLASS_API_KEY","")
        r3 = requests.get("https://open-api-v3.coinglass.com/api/index/bitcoin-bubble-index",
            headers={"CG-API-KEY": cg_gl}, timeout=10)
        bubble = r3.json().get('data', [])
        if bubble:
            snapshot['bubble_index'] = round(float(bubble[-1].get('index', 0)), 2)
    except: pass
    
    # Hyperliquid FR
    try:
        r4 = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"}, timeout=10)
        hl = r4.json()
        meta = hl[0]['universe']
        ctxs = hl[1]
        snapshot['funding_rates'] = {}
        for i, asset in enumerate(meta):
            if asset['name'] in ["BTC","ETH","SOL"] and i < len(ctxs):
                snapshot['funding_rates'][asset['name']] = round(float(ctxs[i].get('funding', 0))*100, 4)
    except: pass
    
    return snapshot


def run_research_cycle():
    """メイン研究サイクル"""
    print(f"🔬 研究エージェント起動: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    log = load_research_log()
    snapshot = get_current_market_snapshot()
    
    # 予測履歴を読み込む
    pred_file = '/Users/mr.k/Projects/and-ai-brain/prediction_history.json'
    predictions = []
    if os.path.exists(pred_file):
        with open(pred_file) as f:
            pred_data = json.load(f)
            predictions = pred_data.get('predictions', [])
    
    verified = [p for p in predictions if p.get('verified')]
    
    # 現在の勝率計算
    total = sum(len(p.get('results', {})) for p in verified)
    wins = sum(
        1 for p in verified
        for r in p.get('results', {}).values()
        if r.get('direction_correct')
    )
    current_win_rate = round(wins/total*100, 1) if total > 0 else 0
    
    # Claudeに研究させる
    with open(PROMPT_FILE) as f:
        research_prompt = f.read()
    
    client = Anthropic()
    
    context = f"""
現在の市場データ:
{json.dumps(snapshot, indent=2, default=str)}

現在の勝率: {current_win_rate}% ({wins}/{total}回)
目標: 月利+5%

過去の予測データ（直近5件）:
{json.dumps(verified[-5:] if verified else [], indent=2, default=str)}

現在のスコアリング重み:
{json.dumps(log['score_weights'], indent=2)}

以下の研究プロンプトに従って分析し、
改善提案を日本語で出力してください:

{research_prompt[:3000]}
"""
    
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": context}]
    )
    
    research_result = response.content[0].text
    
    # ログに記録
    log['last_research'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    log['current_win_rate'] = current_win_rate
    log['total_trades'] = total
    log['winning_trades'] = wins
    
    if not log.get('monthly_win_rates'):
        log['monthly_win_rates'] = []
    log['monthly_win_rates'].append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'win_rate': current_win_rate
    })
    
    save_research_log(log)
    
    # Telegramに結果を送信
    msg = f"""🔬 *研究エージェント レポート*
{datetime.now().strftime('%m/%d %H:%M')} JST

📊 *現在の勝率: {current_win_rate}%*（目標: 月利+5%）
取引数: {total}回 / 的中: {wins}回

📈 *市場状況*
F&G: {snapshot.get('fear_greed',{}).get('current','?')}/100
BTC支配率: {snapshot.get('market',{}).get('btc_dominance','?')}%
Bubble: {snapshot.get('bubble_index','?')}

🔍 *AI分析結果*
{research_result[:500]}

🦴 _&AI QUANTUM EDGE 研究エージェント_"""
    
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )
    
    print(f"✅ 研究完了 / 勝率: {current_win_rate}% / Telegram送信済み")
    return research_result


if __name__ == "__main__":
    run_research_cycle()
