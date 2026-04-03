"""
&AI BRAIN - ファンダメンタルデータプラグイン
EDINET DB / 量子ポートフォリオ最適化
"""

import os
import requests
from plugins import DataPlugin


class FundamentalPlugin(DataPlugin):
    """ファンダメンタル分析プラグイン"""

    def fetch(self) -> list[dict]:
        records = []
        # EDINET DBから企業データ取得（利用可能な場合）
        edinet = get_edinet_summary()
        for item in edinet:
            records.append(self._make_record(
                ticker=item.get("ticker", "JP"),
                value=float(item.get("value", 0)),
                source="edinet",
                category="fundamental",
                confidence=0.9,
                metadata=item,
            ))
        return records


# ========================================
# 量子ポートフォリオ最適化（後方互換性のため維持）
# ========================================

def quantum_portfolio_optimize(
    market_data: dict,
    risk_tolerance: float = 0.5,
    sentiment: dict | None = None,
) -> dict:
    """量子的ポートフォリオ最適化（リアルデータ版）"""

    categories = {
        "BTC":     "crypto",
        "ETH":     "crypto",
        "NVDA":    "stock",
        "AAPL":    "stock",
        "Gold":    "commodity",
        "USDT":    "stable",
        "日経225": "index",
        "S&P500":  "index",
    }

    def get_adjusted_return(name: str, data: dict) -> float:
        base_return = data["return"]
        if sentiment and "sentiment_by_asset" in sentiment:
            s = sentiment["sentiment_by_asset"].get(name, {})
            sentiment_score = s.get("score", 5) / 10
            adjustment = (sentiment_score - 0.5) * 0.10
            return base_return + adjustment
        return base_return

    # カテゴリ別配分（リスク許容度による）
    if risk_tolerance < 0.35:
        alloc = {"crypto": 0.40, "stock": 0.35, "commodity": 0.15, "stable": 0.05, "index": 0.05}
    elif risk_tolerance < 0.65:
        alloc = {"crypto": 0.25, "stock": 0.30, "commodity": 0.20, "stable": 0.15, "index": 0.10}
    else:
        alloc = {"crypto": 0.10, "stock": 0.25, "commodity": 0.30, "stable": 0.25, "index": 0.10}

    portfolio = {}
    for category, cat_alloc in alloc.items():
        cat_assets = {
            k: v for k, v in market_data.items()
            if categories.get(k) == category
        }
        if not cat_assets:
            continue

        best = max(
            cat_assets.keys(),
            key=lambda k: (
                get_adjusted_return(k, cat_assets[k]) / cat_assets[k]["risk"]
                if cat_assets[k]["risk"] > 0 else 0
            ),
        )
        portfolio[best] = round(cat_alloc * 100, 1)

    return portfolio


# ========================================
# EDINET DB連携（日本株ファンダメンタル）
# ========================================

def get_edinet_summary() -> list[dict]:
    """EDINET DBから注目銘柄のサマリーを取得"""
    api_key = os.environ.get("EDINETDB_API_KEY", "")
    if not api_key:
        return []

    try:
        r = requests.get(
            "https://api.edinetdb.com/v1/documents",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"type": "2", "limit": 5},  # 有価証券報告書
            timeout=10,
        )
        if r.status_code == 200:
            docs = r.json().get("results", [])
            return [
                {
                    "ticker": d.get("edinetCode", ""),
                    "value": 0.0,
                    "name": d.get("filerName", ""),
                    "doc_type": d.get("docTypeCode", ""),
                    "period_end": d.get("periodEnd", ""),
                }
                for d in docs[:5]
            ]
    except Exception:
        pass
    return []
