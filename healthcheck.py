"""
&AI QUANTUM EDGE - システム全体ヘルスチェック
全機能の稼働状況を定期確認して Telegram + グループに報告

実行: 毎日9:00 JST（デイリーレポートの前）
"""

import os, json, subprocess, requests, time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
GROUP_ID = "-1003799035163"
GROUP_THREAD_TASKS = 14  # 🦴ボンズタスク管理トピック


def send_telegram(msg: str, thread_id: int = None):
    params = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=params, timeout=10)
    if thread_id:
        params2 = {"chat_id": GROUP_ID, "text": msg, "parse_mode": "Markdown",
                   "message_thread_id": thread_id}
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=params2, timeout=10)


def check(name: str, fn) -> tuple[str, str]:
    """チェック実行 → (status_emoji, detail)"""
    try:
        result = fn()
        return "✅", str(result)[:60]
    except Exception as e:
        return "❌", str(e)[:60]


def run_healthcheck():
    now = datetime.now().strftime("%Y/%m/%d %H:%M JST")
    results = []

    # ========== 1. LaunchAgents ==========
    agents = {
        "auto-trader（毎時）": "com.bk.auto-trader",
        "daily-report（3回/日）": "com.bk.ai-brain-daily",
        "vip-watcher（毎時）": "com.bk.vip-watcher",
        "research-agent（毎晩2:00）": "com.bk.research-agent",
        "fund-research（毎晩2:30）": "com.bk.fund-research-agent",
    }
    agent_results = []
    for name, label in agents.items():
        r = subprocess.run(['launchctl', 'list', label], capture_output=True, text=True)
        import re
        exit_match = re.search(r'"LastExitStatus" = (\d+)', r.stdout)
        exit_code = int(exit_match.group(1)) if exit_match else -1
        ok = r.returncode == 0
        status = "✅" if ok else "❌"
        err = f" (ExitCode:{exit_code})" if ok and exit_code != 0 else ""
        agent_results.append(f"  {status} {name}{err}")
    results.append(("⏰ LaunchAgents", "\n".join(agent_results)))

    # ========== 2. データソース ==========
    def check_fg():
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        v = int(r.json()['data'][0]['value'])
        return f"F&G={v}/100"

    def check_hl():
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState",
                  "user": "0xe5941eeF19C30A09f05b23b4D512301b3388c9Ed"}, timeout=8)
        bals = {b['coin']: float(b['total']) for b in r.json().get("balances", [])}
        return f"USDH=${bals.get('USDH',0):,.2f}"

    def check_dydx():
        r = requests.get("https://indexer.dydx.trade/v4/addresses/dydx182rjzngn7qzsjunszne4srkr2r2tpplgvc4ct0", timeout=8)
        eq = float(r.json()["subaccounts"][0]["equity"])
        return f"USDC=${eq:,.2f}"

    def check_coingecko():
        cg_key = os.environ.get("COINGECKO_API_KEY","")
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            headers={"x-cg-demo-api-key": cg_key}, timeout=8)
        btc = r.json()['bitcoin']['usd']
        return f"BTC=${btc:,.0f}"

    def check_whale():
        key = os.environ.get("WHALE_ALERT_KEY","")
        r = requests.get(f"https://api.whale-alert.io/v1/status?api_key={key}", timeout=8)
        return f"status={r.json().get('result','ok')}"

    def check_coinglass():
        key = os.environ.get("COINGLASS_API_KEY","")
        r = requests.get("https://open-api.coinglass.com/public/v2/indicator/fear_greed_history",
            headers={"coinglassSecret": key}, timeout=8)
        return f"status={r.status_code}"

    def check_twitter():
        key = os.environ.get("TWITTERAPI_IO_KEY","")
        r = requests.get("https://api.twitterapi.io/twitter/user/info?userName=elonmusk",
            headers={"X-API-Key": key}, timeout=8)
        return f"status={r.status_code}"

    def check_nasa():
        r = requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=RE&longitude=121.0&latitude=14.0&start=20260101&end=20260101&format=JSON",
            timeout=8)
        return f"status={r.status_code}"

    def check_momentum():
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
        from momentum_engine import get_all_momentum_scores
        s = get_all_momentum_scores()
        return f"{len(s)}銘柄スコア取得"

    def check_braket():
        import boto3
        session = boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name="us-east-1"
        )
        braket = session.client('braket')
        devices = braket.search_devices(filters=[])
        active = len([d for d in devices['devices'] if d['deviceStatus'] == 'ONLINE'])
        return f"{active}台オンライン"

    def check_ibm():
        from qiskit_ibm_runtime import QiskitRuntimeService
        token = os.environ.get("IBM_QUANTUM_TOKEN","")
        service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
        backends = service.backends()
        return f"{len(backends)}バックエンド"

    datasources = [
        ("Fear&Greed", check_fg),
        ("CoinGecko", check_coingecko),
        ("Hyperliquid", check_hl),
        ("dYdX", check_dydx),
        ("Whale Alert", check_whale),
        ("Coinglass", check_coinglass),
        ("Twitter API", check_twitter),
        ("NASA POWER", check_nasa),
        ("モメンタムEngine", check_momentum),
    ]

    src_results = []
    for name, fn in datasources:
        st, detail = check(name, fn)
        src_results.append(f"  {st} {name}: {detail}")
    results.append(("📡 データソース", "\n".join(src_results)))

    # ========== 3. 量子コンピューター ==========
    quantum_results = []

    # Amazon Braket
    st, detail = check("Amazon Braket", check_braket)
    quantum_results.append(f"  {st} Amazon Braket: {detail}")

    # IBM Quantum
    st, detail = check("IBM Quantum", check_ibm)
    quantum_results.append(f"  {st} IBM Quantum: {detail}")

    # 量子アルゴリズムの実装状況
    quantum_results.append("  📋 実装済み量子アルゴリズム:")
    quantum_results.append("    • quantum_portfolio_optimize() — ポートフォリオ最適化")
    quantum_results.append("    • quantum_simulate_fund_params() — ファンドパラメータ最適化")
    quantum_results.append("    • バックテスト(backtest.py) — 量子インスパイアード探索")
    quantum_results.append("  ⚠️ 注: 現在は量子インスパイアード古典実装")
    quantum_results.append("    → Amazon BraketのIonQへの接続は設定済み")
    quantum_results.append("    → 実量子回路実行は次フェーズで有効化予定")

    results.append(("⚛️ 量子コンピューター", "\n".join(quantum_results)))

    # ========== 4. 取引システム ==========
    def check_auto_trader():
        with open('/tmp/auto-trader.log', 'r') as f:
            lines = f.readlines()
        last = [l.strip() for l in lines[-5:] if l.strip()]
        last_run = last[-1] if last else "ログなし"
        return f"最終: {last_run[:40]}"

    def check_fund_status():
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
        from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
        total = 0
        for fid in FUNDS:
            fd = load_fund(fid)
            total += fd.get("portfolio_value", INITIAL_CAPITAL)
        return f"合計¥{total:,.0f}"

    def check_backtest():
        with open('/Users/mr.k/Projects/and-ai-brain/backtest_results.json') as f:
            d = json.load(f)
        return f"更新:{d.get('generated_at','')[:10]}"

    trade_checks = [
        ("auto_trader.py", check_auto_trader),
        ("デモファンド3本", check_fund_status),
        ("バックテスト", check_backtest),
    ]
    trade_results = []
    for name, fn in trade_checks:
        st, detail = check(name, fn)
        trade_results.append(f"  {st} {name}: {detail}")
    results.append(("🤖 取引システム", "\n".join(trade_results)))

    # ========== 集計 ==========
    total_ok = sum(1 for _, lines in results for l in lines.split('\n') if '✅' in l)
    total_ng = sum(1 for _, lines in results for l in lines.split('\n') if '❌' in l)
    health_score = int(total_ok / max(total_ok + total_ng, 1) * 100)

    health_emoji = "🟢" if health_score >= 90 else "🟡" if health_score >= 70 else "🔴"

    # レポート生成
    msg = f"""⚛️ *システムヘルスチェック*
{now}

{health_emoji} *総合スコア: {health_score}%* ({total_ok}✅ / {total_ng}❌)
━━━━━━━━━━━━━━━
"""
    for section, content in results:
        msg += f"\n*{section}*\n{content}\n"

    msg += "━━━━━━━━━━━━━━━"

    # 送信
    send_telegram(msg, thread_id=GROUP_THREAD_TASKS)

    # ヘルスログ保存
    log_path = '/Users/mr.k/Projects/and-ai-brain/health_log.json'
    log = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            log = json.load(f)
    log.append({
        "time": now,
        "score": health_score,
        "ok": total_ok,
        "ng": total_ng
    })
    log = log[-30:]  # 30件保持
    with open(log_path, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"✅ ヘルスチェック完了: {health_score}% ({total_ok}✅/{total_ng}❌)")
    return health_score


if __name__ == "__main__":
    run_healthcheck()
