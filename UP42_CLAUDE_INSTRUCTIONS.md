# UP42 衛星API - Claude指示書

## 概要
UP42 APIを使って衛星写真を取得するPythonコードを実装してください。

---

## 認証方法（重要）

UP42はOAuth2のパスワードグラントを使います。

### Step 1: アクセストークン取得
```
POST https://auth.up42.com/realms/public/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

username=<メールアドレス>&password=<パスワード>&grant_type=password&client_id=up42-api
```

### Step 2: 取得したaccess_tokenをBearerトークンとして使用
```
Authorization: Bearer <access_token>
```

---

## 実装してほしいこと

### ファイル名: `up42_satellite.py`
### 場所: `/Users/mr.k/Projects/and-ai-brain/`

```python
"""
&AI QUANTUM EDGE - UP42衛星画像取得
"""

import requests, os, json
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

UP42_EMAIL = os.environ.get("UP42_EMAIL")
UP42_PASSWORD = os.environ.get("UP42_PASSWORD")
UP42_PROJECT_ID = os.environ.get("UP42_PROJECT_ID")

def get_access_token():
    """UP42のアクセストークンを取得（5分間有効）"""
    r = requests.post(
        "https://auth.up42.com/realms/public/protocol/openid-connect/token",
        data={
            "username": UP42_EMAIL,
            "password": UP42_PASSWORD,
            "grant_type": "password",
            "client_id": "up42-api"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if r.status_code == 200:
        return r.json()["access_token"]
    raise Exception(f"認証失敗: {r.status_code} {r.text[:100]}")


def search_satellite_images(lat, lon, radius_km=5, token=None):
    """
    指定座標の衛星画像を検索
    
    使用コレクション（解像度が高い順）:
    - "PHR" = Pleiades HR (0.5m解像度)
    - "SPOT" = SPOT 6/7 (1.5m解像度)
    - "PHR-1A", "PHR-1B" = Pleiades 1A/1B
    """
    if not token:
        token = get_access_token()
    
    # 座標からBoundingBoxを計算（約radius_km四方）
    deg_per_km = 0.009  # 約1km
    bbox = [
        lon - deg_per_km * radius_km,
        lat - deg_per_km * radius_km,
        lon + deg_per_km * radius_km,
        lat + deg_per_km * radius_km,
    ]
    
    # カタログ検索
    r = requests.post(
        "https://api.up42.com/catalog/hosts/oneatlas/stac/search",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={
            "bbox": bbox,
            "datetime": "2025-01-01T00:00:00Z/2026-03-27T23:59:59Z",
            "limit": 10,
            "collections": ["PHR", "SPOT", "phr", "spot"],
            "query": {
                "cloudCoverage": {"lte": 20}  # 雲量20%以下
            }
        }
    )
    
    return r.json() if r.status_code == 200 else None


def get_preview_image(item_id, token):
    """画像のプレビュー（サムネイル）を取得"""
    r = requests.get(
        f"https://api.up42.com/catalog/hosts/oneatlas/stac/collections/PHR/items/{item_id}/thumbnail",
        headers={"Authorization": f"Bearer {token}"}
    )
    return r.content if r.status_code == 200 else None


def main():
    """デモ: ジョホールバルの衛星写真を検索"""
    print("🛰️ UP42 衛星画像検索...")
    
    # ジョホールバル・マレーシアの座標
    lat, lon = 1.518637, 103.784210
    
    token = get_access_token()
    print(f"✅ 認証成功")
    
    results = search_satellite_images(lat, lon, radius_km=3, token=token)
    
    if results and results.get("features"):
        items = results["features"]
        print(f"✅ {len(items)}件の衛星画像が見つかりました！")
        
        for i, item in enumerate(items[:3]):
            props = item.get("properties", {})
            date = props.get("datetime", "")[:10]
            cloud = props.get("cloudCoverage", "?")
            collection = item.get("collection", "?")
            item_id = item.get("id", "")
            
            print(f"\n  📸 画像{i+1}:")
            print(f"     日付: {date}")
            print(f"     コレクション: {collection}")
            print(f"     雲量: {cloud}%")
            print(f"     ID: {item_id[:30]}...")
    else:
        print(f"結果: {results}")


if __name__ == "__main__":
    main()
```

---

## .envに追加が必要な変数

```
# UP42 衛星API
UP42_EMAIL=<UP42に登録したメールアドレス>
UP42_PASSWORD=<UP42のパスワード>
UP42_PROJECT_ID=<コンソールのProject ID>
```

---

## 実装の優先順位

1. **まず認証テスト** → get_access_token()が動くか確認
2. **カタログ検索** → 指定座標の画像一覧を取得
3. **プレビュー取得** → サムネイル画像をTelegramに送信
4. **本番購入** → 実際の高解像度画像を購入（クレジット使用）

---

## 参考: UP42 APIエンドポイント

- 認証: `https://auth.up42.com/realms/public/protocol/openid-connect/token`
- カタログ検索: `https://api.up42.com/catalog/hosts/oneatlas/stac/search`
- タスク作成: `https://api.up42.com/projects/{project_id}/jobs`
- ダウンロード: `https://api.up42.com/projects/{project_id}/jobs/{job_id}/downloads/results`

---

## 注意事項

- アクセストークンは5分間のみ有効 → 毎回取得する
- 画像購入はクレジット消費（1km² = $0.5〜$2）
- まず無料プレビュー/サムネイルで確認してから購入
- 雲量(cloudCoverage) 20%以下を推奨

作成: 2026-03-27 / &AI QUANTUM EDGE
