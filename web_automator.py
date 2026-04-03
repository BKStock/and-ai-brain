"""
&AI QUANTUM EDGE - 汎用Web自動化ライブラリ
任意のサービスへの登録・ログイン・データ取得を自動化

使い方:
    from web_automator import WebAutomator
    
    bot = WebAutomator()
    result = bot.register("edinetdb", email="xxx@gmail.com")
    result = bot.login("edinetdb", email="xxx", password="xxx")
    key = bot.extract_api_key("edinetdb")

他のBotから使う場合:
    import sys
    sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
    from web_automator import WebAutomator
"""

import os, json, re, time, requests
from typing import Optional, Dict, Any, Callable
from dotenv import load_dotenv

load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")


# ==============================
# サービス定義（追加可能）
# ==============================
SERVICES = {
    "edinetdb": {
        "name": "EDINET DB",
        "register_url": "https://edinetdb.jp/developers",
        "login_url": "https://edinetdb.jp/login",
        "dashboard_url": "https://edinetdb.jp/dashboard",
        "api_endpoint": "https://edinetdb.jp/developers/register",
        "env_key": "EDINETDB_API_KEY",
        "key_pattern": r"edb_[a-zA-Z0-9_-]{20,}",
        "auth_type": "google_sso",  # google_sso / email_password / api_key
        "free": True,
        "form_fields": {
            "email": "#email-input",
            "name": "#user-name-input",
            "company": "#company-input",
            "purpose": "#use-purpose-input",
        },
        "submit": "#register-btn",
        "direct_api": {
            "url": "https://edinetdb.jp/developers/register",
            "method": "POST",
            "payload": lambda email, name="BK", company="BK AI Factory": {
                "email": email,
                "email_opt_in": True,
                "user_name": name,
                "company_name": company,
                "use_purpose": "AIエージェント連携",
                "comment": ""
            }
        }
    },
    "jquants": {
        "name": "J-Quants",
        "register_url": "https://jpx-jquants.com/ja/register",
        "login_url": "https://jpx-jquants.com/ja/login",
        "dashboard_url": "https://jpx-jquants.com/ja/dashboard",
        "env_key": "JQUANTS_API_KEY",
        "key_pattern": r"[A-Za-z0-9_-]{40,}",
        "auth_type": "email_password",
        "free": True,
        "form_fields": {
            "email": "input[name='email']",
            "password": "input[name='password']",
            "confirm_password": "input[name='confirmPassword']",
            "terms": "input[name='terms']",
        },
        "submit": "button[type='submit']:has-text('サインアップ')",
    },
    "tavily": {
        "name": "Tavily",
        "register_url": "https://app.tavily.com/sign-up",
        "login_url": "https://app.tavily.com/sign-in",
        "dashboard_url": "https://app.tavily.com/home",
        "env_key": "TAVILY_API_KEY",
        "key_pattern": r"tvly-[a-zA-Z0-9]{20,}",
        "auth_type": "email_password",
        "free": True,
    },
    "financial_datasets": {
        "name": "Financial Datasets",
        "register_url": "https://financialdatasets.ai/register",
        "login_url": "https://financialdatasets.ai/login",
        "dashboard_url": "https://financialdatasets.ai/dashboard",
        "env_key": "FINANCIAL_DATASETS_API_KEY",
        "key_pattern": r"[a-zA-Z0-9]{32,}",
        "auth_type": "email_password",
        "free": False,
        "price": "$50/月〜",
    },
    "coinglass": {
        "name": "Coinglass",
        "register_url": "https://www.coinglass.com/register",
        "login_url": "https://www.coinglass.com/login",
        "dashboard_url": "https://www.coinglass.com/account",
        "env_key": "COINGLASS_API_KEY",
        "key_pattern": r"[a-f0-9]{32,}",
        "auth_type": "email_password",
        "free": False,
        "price": "$29/月〜",
    },
    "glassnode": {
        "name": "Glassnode",
        "register_url": "https://studio.glassnode.com/register",
        "login_url": "https://studio.glassnode.com/login",
        "dashboard_url": "https://studio.glassnode.com/settings/api",
        "env_key": "GLASSNODE_API_KEY",
        "key_pattern": r"[a-zA-Z0-9]{40,}",
        "auth_type": "email_password",
        "free": False,
        "price": "$29/月〜",
    },
}


class WebAutomator:
    """
    汎用Web自動化クラス
    任意のサービスに対して登録・ログイン・APIキー取得を自動化
    """

    def __init__(self, email: str = "tik.betrnk@gmail.com",
                 password_base: str = "BKai2026!Q#",
                 notify: bool = True):
        self.email = email
        self.password_base = password_base
        self.notify = notify
        self._playwright = None
        self._browser = None

    def _get_password(self, service_id: str) -> str:
        """サービスごとのパスワードを生成"""
        suffix = {
            "edinetdb": "ED",
            "jquants": "JQ",
            "tavily": "TV",
            "financial_datasets": "FD",
            "coinglass": "CG",
            "glassnode": "GN",
        }.get(service_id, service_id[:2].upper())
        return f"{self.password_base}{suffix}"

    def _send_telegram(self, msg: str):
        """Telegram通知"""
        if self.notify and BOT_TOKEN:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=10
            )

    def _start_browser(self, headless: bool = True):
        """ブラウザを起動"""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        return self._browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            locale='ja-JP',
            viewport={'width': 1280, 'height': 800},
        )

    def _stop_browser(self):
        """ブラウザを終了"""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None

    def save_api_key(self, service_id: str, api_key: str,
                     extra_env_files: list = None) -> bool:
        """
        APIキーを.envファイルに保存
        
        Args:
            service_id: サービスID
            api_key: APIキー値
            extra_env_files: 追加で保存するパス一覧
        """
        if service_id not in SERVICES:
            return False

        env_key = SERVICES[service_id]["env_key"]

        default_envs = [
            '/Users/mr.k/Projects/and-ai-brain/.env',
            '/Users/mr.k/Projects/bk-dexter-jp/.env',
        ]
        all_envs = default_envs + (extra_env_files or [])

        saved = []
        for env_path in all_envs:
            if not os.path.exists(env_path):
                continue
            with open(env_path, 'r') as f:
                content = f.read()
            if env_key in content:
                content = re.sub(rf'{env_key}=.*', f'{env_key}={api_key}', content)
            else:
                content += f'\n{env_key}={api_key}\n'
            with open(env_path, 'w') as f:
                f.write(content)
            saved.append(env_path)

        # Notionに記録
        try:
            config = json.load(open('/Users/mr.k/.openclaw/workspace-bonds/.notion-config.json'))
            requests.post(
                "https://api.notion.com/v1/pages",
                headers={"Authorization": f"Bearer {config['api_key']}",
                         "Notion-Version": "2022-06-28",
                         "Content-Type": "application/json"},
                json={
                    "parent": {"database_id": config["tasks_db_id"]},
                    "properties": {
                        "タスク名": {"title": [{"text": {"content": f"{SERVICES[service_id]['name']} APIキー取得完了"}}]},
                        "ステータス": {"status": {"name": "完了"}},
                        "優先度": {"select": {"name": "高"}},
                    }
                }, timeout=10
            )
        except:
            pass

        self._send_telegram(
            f"✅ *{SERVICES[service_id]['name']} APIキー保存完了！*\n\n"
            f"`{env_key}={api_key[:12]}...`\n\n"
            + "\n".join(f"✅ {p.split('/')[-2]}/{p.split('/')[-1]}" for p in saved)
        )
        return True

    def register_direct_api(self, service_id: str, **kwargs) -> Dict[str, Any]:
        """
        直接APIエンドポイントに登録リクエストを送信
        Playwrightなしで完結するサービス向け
        """
        if service_id not in SERVICES:
            return {"success": False, "error": "Unknown service"}

        svc = SERVICES[service_id]
        direct = svc.get("direct_api")
        if not direct:
            return {"success": False, "error": "No direct API configured"}

        payload = direct["payload"](
            email=kwargs.get("email", self.email),
            name=kwargs.get("name", "BK"),
            company=kwargs.get("company", "BK AI Factory"),
        )

        headers = {
            "Content-Type": "application/json",
            "Referer": svc["register_url"],
            "User-Agent": "Mozilla/5.0",
            "Origin": f"https://{svc['register_url'].split('/')[2]}",
        }

        r = requests.request(
            direct["method"],
            direct["url"],
            json=payload,
            headers=headers,
            timeout=15
        )

        result = {"status_code": r.status_code, "response": r.text[:500]}

        # APIキーを探す
        key_pattern = svc.get("key_pattern", "")
        if key_pattern:
            keys = re.findall(key_pattern, r.text)
            if keys:
                result["api_key"] = keys[0]
                self.save_api_key(service_id, keys[0])

        result["success"] = r.status_code in [200, 201]
        return result

    def register_with_browser(self, service_id: str, **kwargs) -> Dict[str, Any]:
        """
        Playwrightブラウザで登録を実行
        フォームが複雑なサービス向け
        """
        if service_id not in SERVICES:
            return {"success": False, "error": "Unknown service"}

        svc = SERVICES[service_id]
        email = kwargs.get("email", self.email)
        password = kwargs.get("password", self._get_password(service_id))

        try:
            context = self._start_browser()
            page = context.new_page()

            # ネットワーク傍受
            api_calls = []
            def on_request(req):
                if req.method == "POST" and "google" not in req.url and "analytics" not in req.url:
                    api_calls.append({"url": req.url, "body": req.post_data})
            page.on("request", on_request)

            page.goto(svc["register_url"], timeout=15000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # フォーム入力
            fields = svc.get("form_fields", {})
            for field_name, selector in fields.items():
                el = page.locator(selector)
                if el.count() == 0:
                    continue
                if field_name == "email":
                    el.type(email, delay=80)
                elif field_name in ["password", "confirm_password"]:
                    el.type(password, delay=60)
                elif field_name == "terms":
                    if not el.is_checked():
                        el.click()
                elif field_name == "purpose":
                    try:
                        page.select_option(selector, value="AIエージェント連携")
                    except:
                        pass
                elif field_name == "name":
                    el.type(kwargs.get("name", "BK"), delay=50)
                elif field_name == "company":
                    el.type(kwargs.get("company", "BK AI Factory"), delay=50)
                time.sleep(0.3)

            time.sleep(2)

            # 送信
            submit = page.locator(svc.get("submit", "button[type='submit']"))
            if submit.count() > 0:
                submit.first.click()
                time.sleep(6)
                page.wait_for_load_state("networkidle")

            result_text = page.inner_text("body")
            result = {
                "success": page.url != svc["register_url"],
                "url": page.url,
                "api_calls": api_calls,
            }

            # APIキーを探す
            key_pattern = svc.get("key_pattern", "")
            if key_pattern:
                keys = re.findall(key_pattern, result_text)
                if keys:
                    result["api_key"] = keys[0]
                    self.save_api_key(service_id, keys[0])

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._stop_browser()

    def login_and_get_api_key(self, service_id: str, **kwargs) -> Optional[str]:
        """
        ログインしてAPIキーを取得
        """
        if service_id not in SERVICES:
            return None

        svc = SERVICES[service_id]
        email = kwargs.get("email", self.email)
        password = kwargs.get("password", self._get_password(service_id))

        try:
            context = self._start_browser()
            page = context.new_page()

            page.goto(svc["login_url"], timeout=15000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # ログインフォーム
            email_el = page.locator('input[name="email"], input[type="email"]')
            if email_el.count() > 0:
                email_el.first.type(email, delay=80)
                time.sleep(0.5)

            pass_el = page.locator('input[name="password"], input[type="password"]')
            if pass_el.count() > 0:
                pass_el.first.type(password, delay=60)
                time.sleep(0.5)

            submit = page.locator('button[type="submit"]')
            if submit.count() > 0:
                submit.first.click()
                time.sleep(5)
                page.wait_for_load_state("networkidle")

            # APIキーページへ
            if "dashboard_url" in svc:
                page.goto(svc["dashboard_url"], timeout=10000)
                page.wait_for_load_state("networkidle")
                time.sleep(2)

            result_text = page.inner_text("body")
            key_pattern = svc.get("key_pattern", "")
            if key_pattern:
                keys = re.findall(key_pattern, result_text)
                if keys:
                    self.save_api_key(service_id, keys[0])
                    return keys[0]

            return None

        except Exception as e:
            print(f"ログインエラー: {e}")
            return None
        finally:
            self._stop_browser()

    def process_pasted_key(self, service_id: str, api_key: str) -> bool:
        """
        KKがコピーして貼り付けたAPIキーを処理
        /savekey コマンドの内部処理
        """
        if service_id not in SERVICES:
            return False
        return self.save_api_key(service_id, api_key)

    def list_services(self) -> str:
        """設定済みサービス一覧"""
        lines = ["📋 *対応サービス一覧*\n"]
        for sid, svc in SERVICES.items():
            tier = "✅ 無料" if svc.get("free") else f"💰 {svc.get('price', '有料')}"
            lines.append(f"`{sid}` — {svc['name']} ({tier})")
        return "\n".join(lines)


# ==============================
# 他のBotから使うためのシンプルAPI
# ==============================

def quick_register(service_id: str, email: str = "tik.betrnk@gmail.com") -> dict:
    """ワンライナーで登録"""
    bot = WebAutomator(email=email)
    return bot.register_direct_api(service_id)


def quick_save(service_id: str, api_key: str) -> bool:
    """ワンライナーでAPIキー保存"""
    bot = WebAutomator()
    return bot.process_pasted_key(service_id, api_key)


def get_service_list() -> str:
    """対応サービス一覧を取得"""
    bot = WebAutomator()
    return bot.list_services()


if __name__ == "__main__":
    print("⚛️ Web自動化ライブラリ テスト\n")
    bot = WebAutomator()

    print(bot.list_services())

    print("\n=== EDINET DBへの直接API登録テスト ===")
    result = bot.register_direct_api("edinetdb")
    print(f"結果: {result}")
