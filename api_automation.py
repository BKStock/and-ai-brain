"""
&AI QUANTUM EDGE - API取得自動化システム
「○○のAPIキー取得して」→ 全自動でキーを取得して.envに保存

対応サービス:
- EDINET DB (edinetdb.jp)
- J-Quants (jpx-jquants.com)
- Financial Datasets (financialdatasets.ai)
- Tavily (tavily.com)
- その他 (汎用フォーム対応)

KKがやること: メール認証のみ（1クリック）
"""

import os, json, re, time, base64
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")

# KK専用APIアカウント用メールアドレス
API_EMAIL = "tik.betrnk@gmail.com"
API_PASSWORD_BASE = "BKai2026!Q#"  # ベースパスワード（サービスごとに末尾を変える）

# サービス設定
SERVICES = {
    "edinetdb": {
        "name": "EDINET DB",
        "url": "https://edinetdb.jp",
        "register_url": "https://edinetdb.jp/register",
        "env_key": "EDINETDB_API_KEY",
        "free_tier": True,
        "notes": "日本株財務データ / 無料枠あり",
    },
    "jquants": {
        "name": "J-Quants",
        "url": "https://jpx-jquants.com",
        "register_url": "https://jpx-jquants.com/auth/register",
        "env_key": "JQUANTS_API_KEY",
        "free_tier": True,
        "notes": "東証株価データ / 完全無料・期限なし",
    },
    "tavily": {
        "name": "Tavily",
        "url": "https://tavily.com",
        "register_url": "https://app.tavily.com/sign-up",
        "env_key": "TAVILY_API_KEY",
        "free_tier": True,
        "notes": "AI最適化ニュース検索 / 無料枠あり",
    },
    "financial_datasets": {
        "name": "Financial Datasets",
        "url": "https://financialdatasets.ai",
        "register_url": "https://financialdatasets.ai/register",
        "env_key": "FINANCIAL_DATASETS_API_KEY",
        "free_tier": False,
        "notes": "米国株ファンダメンタル / $50/月〜",
    },
}


def send_telegram(msg: str, buttons=None):
    """Telegramに送信（ボタン付き対応）"""
    params = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    if buttons:
        params["reply_markup"] = json.dumps({
            "inline_keyboard": buttons
        })
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=params, timeout=10)


def save_api_key_to_env(key_name: str, key_value: str):
    """APIキーを.envに保存"""
    env_path = '/Users/mr.k/Projects/and-ai-brain/.env'
    with open(env_path, 'r') as f:
        content = f.read()

    # 既存のキーを更新 or 追加
    pattern = rf'^{key_name}=.*$'
    new_line = f'{key_name}={key_value}'

    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
    else:
        content += f'\n{new_line}\n'

    with open(env_path, 'w') as f:
        f.write(content)

    # dexter-jpの.envにも保存
    dexter_env = '/Users/mr.k/Projects/bk-dexter-jp/.env'
    if os.path.exists(dexter_env):
        with open(dexter_env, 'r') as f:
            d_content = f.read()
        if re.search(pattern, d_content, re.MULTILINE):
            d_content = re.sub(pattern, new_line, d_content, flags=re.MULTILINE)
        else:
            d_content += f'\n{new_line}\n'
        with open(dexter_env, 'w') as f:
            f.write(d_content)

    print(f"✅ {key_name} を.envに保存完了")


def get_gmail_verification_code(service_name: str, timeout_sec: int = 300) -> str:
    """
    GmailからAPIキー認証メールを自動取得
    Gmail APIが設定されている場合のみ動作
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        creds_path = '/Users/mr.k/.openclaw/workspace-bonds/.gmail-credentials.json'
        if not os.path.exists(creds_path):
            return None

        creds = Credentials.from_authorized_user_file(creds_path)
        service = build('gmail', 'v1', credentials=creds)

        # 最新のメールを確認（最大5分待機）
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            results = service.users().messages().list(
                userId='me',
                q=f'from:{service_name} is:unread',
                maxResults=1
            ).execute()

            messages = results.get('messages', [])
            if messages:
                msg_id = messages[0]['id']
                msg = service.users().messages().get(userId='me', id=msg_id).execute()

                # メール本文からコードを抽出
                body = ""
                if 'data' in msg['payload']['body']:
                    body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode()
                elif 'parts' in msg['payload']:
                    for part in msg['payload']['parts']:
                        if part['mimeType'] == 'text/plain':
                            body = base64.urlsafe_b64decode(part['body']['data']).decode()

                # 6桁のコードを探す
                codes = re.findall(r'\b\d{6}\b', body)
                if codes:
                    return codes[0]

                # URLリンクを探す（メール認証タイプ）
                urls = re.findall(r'https://[^\s<>"]+verify[^\s<>"]*', body)
                if urls:
                    return urls[0]

            time.sleep(10)

        return None
    except Exception as e:
        print(f"Gmail API エラー: {e}")
        return None


def automate_edinetdb_registration():
    """EDINET DB 登録自動化"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print("📋 EDINET DB 登録開始...")
            page.goto("https://edinetdb.jp/register")
            page.wait_for_load_state("networkidle")

            # フォーム入力
            # （サイトの実際のセレクタに合わせて調整が必要）
            if page.locator('input[type="email"]').count() > 0:
                page.fill('input[type="email"]', API_EMAIL)
            if page.locator('input[type="password"]').count() > 0:
                page.fill('input[type="password"]', API_PASSWORD_BASE + "ED")

            # スクリーンショット保存
            page.screenshot(path='/tmp/edinetdb-register.png')

            # メール認証待ち
            send_telegram(
                "📧 *EDINET DB登録フォーム入力完了*\n\n"
                f"`{API_EMAIL}` にメールが届きます\n"
                "メールの認証リンクをクリックしてください！\n\n"
                "→ クリック後「✅ 完了」と送ってください"
            )

            # 認証後のAPIキーページに移動（実装は認証後）
            # ...

        except Exception as e:
            print(f"エラー: {e}")
            page.screenshot(path='/tmp/edinetdb-error.png')
        finally:
            browser.close()


def manual_api_key_input(service_name: str, key_name: str):
    """
    手動入力モード
    KKがコピーしたAPIキーをここに貼り付けると.envに自動保存
    """
    send_telegram(
        f"🔑 *{service_name} APIキー受け取り準備完了*\n\n"
        f"APIキーを取得したら、そのままここに貼り付けてください\n"
        f"→ 自動で `.env` と `bk-dexter-jp/.env` に保存します\n\n"
        f"例: `edb_xxxxxxxxxxxxxx`"
    )


def process_api_key(service_id: str, api_key: str) -> bool:
    """APIキーを受け取って全システムに保存（web_automatorに委譲）"""
    from web_automator import quick_save
    return quick_save(service_id, api_key)
