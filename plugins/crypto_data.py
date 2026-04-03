"""
&AI BRAIN - 暗号資産データプラグイン
Fear&Greed / BTC支配率 / Coinglass OI
"""

import os
import requests
from plugins import DataPlugin


class CryptoDataPlugin(DataPlugin):
    """暗号資産メトリクスプラグイン"""

    def fetch(self) -> list[dict]:
        records = []

        fg = get_fear_greed()
        if fg:
            records.append(self._make_record(
                ticker="CRYPTO",
                value=float(fg["score"]),
                source="alternative.me",
                category="sentiment",
                metadata={"label": fg["label"], "signal": fg["signal"]},
            ))

        dom = get_btc_dominance()
        if dom:
            records.append(self._make_record(
                ticker="BTC",
                value=float(dom["btc_dominance"]),
                source="coingecko",
                category="macro",
                metadata=dom,
            ))

        cg = get_coinglass_data()
        if cg:
            if "bubble_index" in cg:
                records.append(self._make_record(
                    ticker="BTC",
                    value=float(cg["bubble_index"]),
                    source="coinglass",
                    category="sentiment",
                    metadata={"signal": cg.get("bubble_signal", "")},
                ))
            if "btc_oi_billion" in cg:
                records.append(self._make_record(
                    ticker="BTC",
                    value=float(cg["btc_oi_billion"]),
                    source="coinglass",
                    category="onchain",
                    metadata={"unit": "billion_usd", "type": "open_interest"},
                ))

        return records


# ========================================
# 個別取得関数（後方互換性のため維持）
# ========================================

def get_fear_greed() -> dict | None:
    """Fear & Greed Index（無料）"""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.status_code == 200:
            d = r.json()["data"][0]
            score = int(d["value"])
            label = d["value_classification"]
            if score <= 25:
                signal = "🟢 極端な恐怖（ロングチャンス）"
            elif score <= 45:
                signal = "🔵 恐怖（慎重に買い）"
            elif score <= 55:
                signal = "⚪ 中立"
            elif score <= 75:
                signal = "🟡 強欲（注意）"
            else:
                signal = "🔴 極端な強欲（ショートチャンス）"
            return {"score": score, "label": label, "signal": signal}
    except Exception:
        pass
    return None


def get_btc_dominance() -> dict | None:
    """BTC支配率（CoinGecko）"""
    try:
        cg_key = os.environ.get("COINGECKO_API_KEY", "")
        headers = {"x-cg-demo-api-key": cg_key} if cg_key else {}
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            g = r.json()["data"]
            btc_dom = g["market_cap_percentage"]["btc"]
            total_mc = g["total_market_cap"]["usd"] / 1e12

            if btc_dom > 55:
                season = "🟠 BTC季節"
                season_signal = "BTCに集中"
            elif btc_dom < 45:
                season = "🌈 アルトシーズン"
                season_signal = "アルトコイン有利"
            else:
                season = "⚪ 中立"
                season_signal = "分散推奨"

            return {
                "btc_dominance": round(btc_dom, 1),
                "season": season,
                "season_signal": season_signal,
                "total_market_cap_trillion": round(total_mc, 2),
            }
    except Exception:
        pass
    return None


def get_coinglass_data() -> dict:
    """Coinglass データ取得（HOBBYIST）"""
    try:
        key = os.environ.get("COINGLASS_API_KEY", "")
        headers = {"CG-API-KEY": key}
        BASE = "https://open-api-v3.coinglass.com"

        result = {}

        # Bitcoin Bubble Index
        r = requests.get(
            f"{BASE}/api/index/bitcoin-bubble-index",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("code") == "0":
            data = r.json().get("data", [])
            if data:
                latest = data[-1]
                idx = float(latest.get("index", 0))
                result["bubble_index"] = idx
                if idx > 50:
                    result["bubble_signal"] = "🔴 バブル圏（ショート注意）"
                elif idx < -20:
                    result["bubble_signal"] = "🟢 割安圏（ロングチャンス）"
                else:
                    result["bubble_signal"] = "⚪ 中立"

        # BTC OI合計
        r2 = requests.get(
            f"{BASE}/api/futures/openInterest/exchange-list",
            headers=headers,
            params={"symbol": "BTC", "currency": "USD"},
            timeout=10,
        )
        if r2.status_code == 200 and r2.json().get("code") == "0":
            data2 = r2.json().get("data", [])
            total_oi = sum(float(i.get("openInterest", 0)) for i in data2)
            result["btc_oi_billion"] = round(total_oi / 1e9, 2)

        return result
    except Exception:
        return {}
