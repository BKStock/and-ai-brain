"""
&AI BRAIN - マクロ経済データプラグイン
FRED API: FF金利 / CPI / 失業率 / 10年債利回り / VIX
"""

import os
import requests
from plugins import DataPlugin


# FREDシリーズID定義
FRED_SERIES = {
    "FEDFUNDS": {"name": "FF金利",        "unit": "%",   "ticker": "FEDFUNDS"},
    "CPIAUCSL": {"name": "CPI（インフレ）", "unit": "index","ticker": "CPI"},
    "UNRATE":   {"name": "失業率",         "unit": "%",   "ticker": "UNRATE"},
    "DGS10":    {"name": "10年債利回り",   "unit": "%",   "ticker": "DGS10"},
    "VIXCLS":   {"name": "VIX",           "unit": "index","ticker": "VIX"},
}


class MacroDataPlugin(DataPlugin):
    """マクロ経済データプラグイン（FRED）"""

    def fetch(self) -> list[dict]:
        records = []
        macro = get_fred_macro()
        for series_id, data in macro.items():
            if data.get("value") is not None:
                meta = FRED_SERIES.get(series_id, {})
                records.append(self._make_record(
                    ticker=meta.get("ticker", series_id),
                    value=float(data["value"]),
                    source="fred",
                    category="macro",
                    confidence=1.0,
                    metadata={
                        "series_id": series_id,
                        "name": meta.get("name", series_id),
                        "unit": meta.get("unit", ""),
                        "date": data.get("date", ""),
                        "signal": data.get("signal", ""),
                    },
                ))
        return records


# ========================================
# 個別取得関数
# ========================================

def get_fred_data(series_id: str, limit: int = 1) -> dict | None:
    """FREDから指定シリーズの最新値を取得"""
    api_key = os.environ.get("FRED_API_KEY", "")
    params: dict = {
        "series_id": series_id,
        "limit": limit,
        "sort_order": "desc",
        "file_type": "json",
    }
    if api_key:
        params["api_key"] = api_key

    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params=params,
            timeout=10,
        )
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs:
                # 欠損値（"."）をスキップして最新有効値を返す
                for o in obs:
                    if o["value"] != ".":
                        return {"value": float(o["value"]), "date": o["date"]}
    except Exception:
        pass
    return None


def get_fred_macro() -> dict:
    """FREDからマクロ指標を一括取得して解釈シグナルを付与"""
    result = {}

    for series_id, meta in FRED_SERIES.items():
        data = get_fred_data(series_id)
        if data is None:
            result[series_id] = {"value": None, "date": "", "signal": "データ取得失敗"}
            continue

        value = data["value"]
        date = data["date"]
        signal = _interpret_macro(series_id, value)
        result[series_id] = {"value": value, "date": date, "signal": signal}

    return result


def _interpret_macro(series_id: str, value: float) -> str:
    """マクロ指標の値を解釈してシグナルを返す"""
    if series_id == "FEDFUNDS":
        if value >= 5.0:
            return "🔴 高金利（リスクオフ）"
        elif value >= 3.0:
            return "🟡 中程度"
        else:
            return "🟢 低金利（リスクオン）"

    elif series_id == "CPIAUCSL":
        # 前月比ではなく水準値のため参考表示
        return f"📊 水準: {value:.1f}"

    elif series_id == "UNRATE":
        if value >= 6.0:
            return "🔴 高失業（景気悪化）"
        elif value >= 4.0:
            return "🟡 普通"
        else:
            return "🟢 完全雇用に近い"

    elif series_id == "DGS10":
        if value >= 4.5:
            return "🔴 利回り高（株式割高感）"
        elif value >= 3.0:
            return "🟡 中程度"
        else:
            return "🟢 低利回り（株式有利）"

    elif series_id == "VIXCLS":
        if value >= 30:
            return "🔴 高ボラ（恐怖圏）"
        elif value >= 20:
            return "🟡 警戒"
        else:
            return "🟢 低ボラ（安定）"

    return ""


def format_macro_section(macro_data: dict) -> str:
    """マクロデータをTelegram用にフォーマット"""
    if not macro_data:
        return ""

    section = "\n━━━━━━━━━━━━━━━\n"
    section += "📉 *マクロ経済指標（FRED）*\n"

    labels = {
        "FEDFUNDS": "FF金利",
        "UNRATE":   "失業率",
        "DGS10":    "10年債",
        "VIXCLS":   "VIX",
        "CPIAUCSL": "CPI",
    }

    for series_id, label in labels.items():
        d = macro_data.get(series_id)
        if d and d.get("value") is not None:
            val = d["value"]
            sig = d.get("signal", "")
            unit = "%" if series_id in ("FEDFUNDS", "UNRATE", "DGS10") else ""
            section += f"  {label}: {val}{unit} {sig}\n"

    return section
