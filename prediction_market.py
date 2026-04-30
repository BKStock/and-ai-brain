"""
&AI QE — Prediction Market Intelligence Layer
マルチソース予測市場データ: Polymarket (Gamma REST + CLOB SDK + pmxt) + Kalshi (pmxt)
歴史データ: ~/Projects/prediction-market-data (BKStock/prediction-market-analysis)

認証不要・無料API (read-only)
"""

import json
import os
import warnings
from datetime import datetime
from typing import Optional

import requests

# urllib3バージョン互換警告を抑制
warnings.filterwarnings("ignore", message=".*urllib3.*")
warnings.filterwarnings("ignore", message=".*chardet.*")

# ──────────────────────────────────────────
# 定数
# ──────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
HISTORICAL_DATA_DIR = os.path.expanduser("~/Projects/prediction-market-data/data")

MARKET_QUERIES = {
    "fed_rate": "fed rate",
    "recession": "recession",
    "tariff": "tariff",
    "bitcoin": "bitcoin price",
    "inflation": "inflation CPI",
    "sp500": "S&P 500",
    "china_trade": "china trade",
    "oil": "oil price",
    "crypto": "crypto market cap",
    "iran": "iran",
}

RISK_THRESHOLDS = {
    "fed_rate_cut_prob": 0.50,
    "recession_prob": 0.40,
    "tariff_escalation_prob": 0.70,
    "iran_conflict_prob": 0.60,
    "btc_crash_prob": 0.50,
}

# ──────────────────────────────────────────
# SDKクライアント初期化 (失敗してもフォールバック)
# ──────────────────────────────────────────
_pmxt_polymarket = None
_pmxt_kalshi = None
_clob_client = None


def _init_sdks() -> None:
    """SDK初期化。失敗しても継続。"""
    global _pmxt_polymarket, _pmxt_kalshi, _clob_client

    try:
        import pmxt
        _pmxt_polymarket = pmxt.Polymarket()
        _pmxt_kalshi = pmxt.Kalshi()
    except Exception as e:
        print(f"[PM] pmxt init failed (fallback to REST): {e}")

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from py_clob_client.client import ClobClient
            _clob_client = ClobClient("https://clob.polymarket.com", key=None, chain_id=137)
    except Exception as e:
        print(f"[PM] py-clob-client init failed (fallback to REST): {e}")


# ──────────────────────────────────────────
# Gamma REST API (既存 / フォールバック)
# ──────────────────────────────────────────
def _gamma_fetch_events(query: str, limit: int = 5) -> list:
    """Polymarket Gamma APIからイベントを検索 (フォールバック用)"""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"closed": "false", "limit": limit, "order": "volume24hr", "ascending": "false"},
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json()

        filtered = [e for e in events if any(w in (e.get("title", "") or "").lower() for w in query.lower().split())]
        return filtered if filtered else events[:limit]
    except Exception as ex:
        print(f"[PM][Gamma] Error fetching events for '{query}': {ex}")
        return []


def _parse_gamma_price(prices: object) -> Optional[float]:
    """Gamma APIの価格フィールドをfloatに変換"""
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except Exception:
            return None
    if isinstance(prices, list) and len(prices) >= 1:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    return None


# ──────────────────────────────────────────
# pmxt ユニファイドAPI
# ──────────────────────────────────────────
def _pmxt_fetch_events(exchange: object, query: str, limit: int = 5) -> list:
    """pmxt経由でイベントを取得し、クエリキーワードでフィルタ"""
    if exchange is None:
        return []
    try:
        events = exchange.fetch_events(params={"limit": limit * 3})
        keywords = query.lower().split()
        filtered = [e for e in events if any(k in (e.title or "").lower() for k in keywords)]
        return filtered[:limit] if filtered else events[:limit]
    except Exception as ex:
        print(f"[PM][pmxt] fetch_events error for '{query}': {ex}")
        return []


def _pmxt_market_yes_prob(market) -> float:
    """pmxt UnifiedMarketのYes確率を取得"""
    try:
        if market.yes and market.yes.price is not None:
            return float(market.yes.price)
    except (AttributeError, TypeError, ValueError):
        pass
    return 0.0


def _pmxt_market_change(market) -> float:
    """pmxt UnifiedMarketの24h価格変動を取得"""
    try:
        if market.yes and market.yes.price_change_24h is not None:
            return float(market.yes.price_change_24h)
    except (AttributeError, TypeError, ValueError):
        pass
    return 0.0


# ──────────────────────────────────────────
# py-clob-client SDK
# ──────────────────────────────────────────
def _clob_search(query: str, limit: int = 10) -> list:
    """CLOB SDKでマーケットを検索。cursor paginationを使用。"""
    if _clob_client is None:
        return []
    try:
        result = _clob_client.get_markets()
        markets = result.get("data", [])
        keywords = query.lower().split()
        filtered = [
            m for m in markets
            if isinstance(m, dict) and any(k in (m.get("question", "") or "").lower() for k in keywords)
        ]
        return filtered[:limit]
    except Exception as ex:
        print(f"[PM][CLOB] search error for '{query}': {ex}")
        return []


# ──────────────────────────────────────────
# 歴史データベースライン
# ──────────────────────────────────────────
def load_historical_baseline(topic: str) -> Optional[dict]:
    """
    ~/Projects/prediction-market-data/data/ からParquetの歴史データを読み込む。
    データが未ダウンロードの場合はNoneを返す。
    `make setup` in prediction-market-data で36GiBデータセットを取得可能。
    """
    data_dir = HISTORICAL_DATA_DIR
    if not os.path.isdir(data_dir):
        return None

    try:
        import glob as glob_module
        parquet_files = glob_module.glob(os.path.join(data_dir, "**", "*.parquet"), recursive=True)
        if not parquet_files:
            return None

        try:
            import pandas as pd
        except ImportError:
            return None

        keywords = topic.lower().split()
        matched_rows = []
        for pf in parquet_files[:5]:  # 最初の5ファイルをサンプル
            try:
                df = pd.read_parquet(pf, columns=["question", "outcome_prices"] if "polymarket" in pf else None)
                if "question" in df.columns:
                    mask = df["question"].str.lower().str.contains("|".join(keywords), na=False)
                    matched_rows.append(df[mask].head(10))
            except Exception:
                continue

        if not matched_rows:
            return None

        import pandas as pd
        combined = pd.concat(matched_rows, ignore_index=True)
        return {
            "source": "historical",
            "topic": topic,
            "sample_count": len(combined),
            "avg_yes_price": float(combined["outcome_prices"].apply(
                lambda x: json.loads(x)[0] if isinstance(x, str) else 0
            ).mean()) if "outcome_prices" in combined.columns else None,
        }
    except Exception as ex:
        print(f"[PM][Historical] load error for '{topic}': {ex}")
        return None


# ──────────────────────────────────────────
# ドメイン別データ取得
# ──────────────────────────────────────────
def get_fed_rate_outlook() -> dict:
    """FRBの金利見通しを複数ソースから取得"""
    result = {
        "sources": [],
        "timestamp": datetime.utcnow().isoformat(),
        "rate_cut_prob": 0.0,
        "no_change_prob": 0.0,
        "rate_hike_prob": 0.0,
        "details": [],
    }

    # pmxt Polymarket
    pmxt_events = _pmxt_fetch_events(_pmxt_polymarket, "fed rate", limit=5)
    for event in pmxt_events:
        if "fed" not in (event.title or "").lower():
            continue
        result["sources"].append("pmxt_polymarket")
        for market in (event.markets or []):
            q = (market.question or "").lower()
            prob = _pmxt_market_yes_prob(market)
            if "decrease" in q or "cut" in q:
                result["rate_cut_prob"] = max(result["rate_cut_prob"], prob)
            elif "no change" in q:
                result["no_change_prob"] = max(result["no_change_prob"], prob)
            elif "increase" in q or "hike" in q:
                result["rate_hike_prob"] = max(result["rate_hike_prob"], prob)
            result["details"].append({"question": market.question, "yes_prob": prob, "source": "polymarket"})

    # pmxt Kalshi
    kalshi_events = _pmxt_fetch_events(_pmxt_kalshi, "fed rate", limit=5)
    for event in kalshi_events:
        if "fed" not in (event.title or "").lower() and "rate" not in (event.title or "").lower():
            continue
        result["sources"].append("pmxt_kalshi")
        for market in (event.markets or []):
            q = (market.question or "").lower()
            prob = _pmxt_market_yes_prob(market)
            if "decrease" in q or "cut" in q or "lower" in q:
                result["rate_cut_prob"] = max(result["rate_cut_prob"], prob)
            result["details"].append({"question": market.question, "yes_prob": prob, "source": "kalshi"})

    # フォールバック: Gamma REST
    if not result["details"]:
        events = _gamma_fetch_events("fed rate", limit=5)
        for event in events:
            if "fed" not in (event.get("title", "") or "").lower():
                continue
            result["sources"].append("gamma_rest")
            for market in event.get("markets", []):
                q = (market.get("question", "") or "").lower()
                prob = _parse_gamma_price(market.get("outcomePrices", "")) or 0.0
                if "decrease" in q or "cut" in q:
                    result["rate_cut_prob"] = max(result["rate_cut_prob"], prob)
                elif "no change" in q:
                    result["no_change_prob"] = max(result["no_change_prob"], prob)
                elif "increase" in q or "hike" in q:
                    result["rate_hike_prob"] = max(result["rate_hike_prob"], prob)
                result["details"].append({"question": market.get("question"), "yes_prob": prob, "source": "gamma"})

    result["sources"] = list(set(result["sources"])) or ["none"]
    return result


def get_recession_outlook() -> dict:
    """景気後退リスクを複数ソースから取得"""
    result = {
        "sources": [],
        "timestamp": datetime.utcnow().isoformat(),
        "recession_prob": 0.0,
        "details": [],
    }

    for exchange, label in [(_pmxt_polymarket, "polymarket"), (_pmxt_kalshi, "kalshi")]:
        for event in _pmxt_fetch_events(exchange, "recession", limit=5):
            for market in (event.markets or []):
                if "recession" not in (market.question or "").lower():
                    continue
                prob = _pmxt_market_yes_prob(market)
                result["recession_prob"] = max(result["recession_prob"], prob)
                result["sources"].append(f"pmxt_{label}")
                result["details"].append({"question": market.question, "yes_prob": prob, "source": label})

    if not result["details"]:
        for event in _gamma_fetch_events("recession", limit=5):
            for market in event.get("markets", []):
                if "recession" not in (market.get("question", "") or "").lower():
                    continue
                prob = _parse_gamma_price(market.get("outcomePrices", "")) or 0.0
                result["recession_prob"] = max(result["recession_prob"], prob)
                result["sources"].append("gamma_rest")
                result["details"].append({"question": market.get("question"), "yes_prob": prob, "source": "gamma"})

    # 歴史ベースライン比較
    baseline = load_historical_baseline("recession")
    if baseline:
        result["historical_baseline"] = baseline

    result["sources"] = list(set(result["sources"])) or ["none"]
    return result


def get_btc_outlook() -> dict:
    """BTC価格予測を複数ソースから取得"""
    result = {
        "sources": [],
        "timestamp": datetime.utcnow().isoformat(),
        "price_levels": [],
    }

    for exchange, label in [(_pmxt_polymarket, "polymarket"), (_pmxt_kalshi, "kalshi")]:
        for event in _pmxt_fetch_events(exchange, "bitcoin price", limit=5):
            if "bitcoin" not in (event.title or "").lower():
                continue
            for market in (event.markets or []):
                prob = _pmxt_market_yes_prob(market)
                result["sources"].append(f"pmxt_{label}")
                result["price_levels"].append({"question": market.question, "prob": prob, "source": label})

    if not result["price_levels"]:
        for event in _gamma_fetch_events("bitcoin price", limit=5):
            if "bitcoin" not in (event.get("title", "") or "").lower():
                continue
            for market in event.get("markets", []):
                prob = _parse_gamma_price(market.get("outcomePrices", "")) or 0.0
                result["sources"].append("gamma_rest")
                result["price_levels"].append({"question": market.get("question"), "prob": prob, "source": "gamma"})

    result["price_levels"].sort(key=lambda x: x["prob"], reverse=True)
    result["sources"] = list(set(result["sources"])) or ["none"]
    return result


def get_geopolitical_risk() -> dict:
    """地政学リスクを複数ソースから取得"""
    result = {
        "sources": [],
        "timestamp": datetime.utcnow().isoformat(),
        "conflict_prob": 0.0,
        "tariff_prob": 0.0,
        "details": [],
    }

    for exchange, label in [(_pmxt_polymarket, "polymarket"), (_pmxt_kalshi, "kalshi")]:
        for event in _pmxt_fetch_events(exchange, "iran tariff", limit=5):
            for market in (event.markets or []):
                q = (market.question or "").lower()
                prob = _pmxt_market_yes_prob(market)
                if "iran" in q or "war" in q or "forces" in q or "conflict" in q:
                    result["conflict_prob"] = max(result["conflict_prob"], prob)
                    result["sources"].append(f"pmxt_{label}")
                if "tariff" in q:
                    result["tariff_prob"] = max(result["tariff_prob"], prob)
                    result["sources"].append(f"pmxt_{label}")
                result["details"].append({"question": market.question, "yes_prob": prob, "source": label})

    if not result["details"]:
        for event in _gamma_fetch_events("iran", limit=5):
            for market in event.get("markets", []):
                q = (market.get("question", "") or "").lower()
                prob = _parse_gamma_price(market.get("outcomePrices", "")) or 0.0
                if "iran" in q or "war" in q or "forces" in q:
                    result["conflict_prob"] = max(result["conflict_prob"], prob)
                if "tariff" in q:
                    result["tariff_prob"] = max(result["tariff_prob"], prob)
                result["sources"].append("gamma_rest")
                result["details"].append({"question": market.get("question"), "yes_prob": prob, "source": "gamma"})

    result["sources"] = list(set(result["sources"])) or ["none"]
    return result


# ──────────────────────────────────────────
# マーケットムーバー
# ──────────────────────────────────────────
def get_market_movers(threshold: float = 0.10, limit: int = 20) -> dict:
    """
    過去24hで最も価格が変動したマーケットを返す。
    threshold: アラート閾値 (デフォルト10%)
    """
    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "threshold": threshold,
        "movers": [],
        "alerts": [],
        "sources": [],
    }

    candidate_markets = []

    # pmxt Polymarket — 全体から上位を取得
    if _pmxt_polymarket is not None:
        try:
            events = _pmxt_polymarket.fetch_events(params={"limit": 50})
            for event in events:
                for market in (event.markets or []):
                    change = _pmxt_market_change(market)
                    prob = _pmxt_market_yes_prob(market)
                    candidate_markets.append({
                        "exchange": "polymarket",
                        "question": market.question or "",
                        "yes_prob": prob,
                        "change_24h": change,
                        "abs_change": abs(change),
                        "volume_24h": getattr(market, "volume_24h", 0) or 0,
                    })
            result["sources"].append("pmxt_polymarket")
        except Exception as ex:
            print(f"[PM][Movers] Polymarket fetch error: {ex}")

    # pmxt Kalshi
    if _pmxt_kalshi is not None:
        try:
            events = _pmxt_kalshi.fetch_events(params={"limit": 50})
            for event in events:
                for market in (event.markets or []):
                    change = _pmxt_market_change(market)
                    prob = _pmxt_market_yes_prob(market)
                    candidate_markets.append({
                        "exchange": "kalshi",
                        "question": market.question or "",
                        "yes_prob": prob,
                        "change_24h": change,
                        "abs_change": abs(change),
                        "volume_24h": getattr(market, "volume_24h", 0) or 0,
                    })
            result["sources"].append("pmxt_kalshi")
        except Exception as ex:
            print(f"[PM][Movers] Kalshi fetch error: {ex}")

    # フォールバック: Gamma REST + change計算不可 (24h変動データなし)
    if not candidate_markets:
        result["sources"].append("gamma_rest_no_change")

    # 変動順にソート
    candidate_markets.sort(key=lambda x: x["abs_change"], reverse=True)
    result["movers"] = candidate_markets[:limit]

    # 閾値超アラート
    for m in result["movers"]:
        if m["abs_change"] >= threshold:
            direction = "UP" if m["change_24h"] > 0 else "DOWN"
            result["alerts"].append(
                f"[{m['exchange'].upper()}] {m['question'][:60]} "
                f"{direction} {m['change_24h']*100:+.1f}% → {m['yes_prob']*100:.1f}%"
            )

    return result


# ──────────────────────────────────────────
# 統合リスク評価
# ──────────────────────────────────────────
def generate_risk_assessment() -> dict:
    """
    全ソースのデータを統合してリスク評価を生成。
    Polymarket (Gamma + pmxt) + Kalshi (pmxt) + 歴史ベースライン。
    """
    fed = get_fed_rate_outlook()
    recession = get_recession_outlook()
    btc = get_btc_outlook()
    geo = get_geopolitical_risk()
    movers = get_market_movers(threshold=0.10, limit=10)

    risk_score = 0
    alerts = list(movers.get("alerts", []))  # マーケットムーバーアラートを先に追加

    if fed["rate_cut_prob"] > RISK_THRESHOLDS["fed_rate_cut_prob"]:
        risk_score += 20
        alerts.append(f"FRB利下げ確率 {fed['rate_cut_prob']*100:.0f}% → リスクオフ警告")

    if recession["recession_prob"] > RISK_THRESHOLDS["recession_prob"]:
        risk_score += 30
        alerts.append(f"景気後退確率 {recession['recession_prob']*100:.0f}% → リスクオフ強制")

    if geo["conflict_prob"] > RISK_THRESHOLDS["iran_conflict_prob"]:
        risk_score += 25
        alerts.append(f"紛争リスク {geo['conflict_prob']*100:.0f}% → GLD比率UP推奨")

    if geo["tariff_prob"] > RISK_THRESHOLDS["tariff_escalation_prob"]:
        risk_score += 15
        alerts.append(f"関税エスカレーション {geo['tariff_prob']*100:.0f}% → 警戒")

    if risk_score >= 50:
        action, action_detail = "RISK_OFF", "予測市場がリスクオフを示唆。BIL推奨。"
    elif risk_score >= 30:
        action, action_detail = "CAUTIOUS", "予測市場が警戒を示唆。ポジションサイズ50%推奨。"
    elif risk_score >= 15:
        action, action_detail = "HEDGE", "予測市場が中程度のリスクを検知。GLD比率UPを検討。"
    else:
        action, action_detail = "CLEAR", "予測市場はクリア。モメンタムシグナル通りに実行OK。"

    # 全ソースを収集
    all_sources = set(fed.get("sources", []) + recession.get("sources", []) + geo.get("sources", []))

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "risk_score": risk_score,
        "action": action,
        "action_detail": action_detail,
        "alerts": alerts,
        "data_sources": sorted(all_sources),
        "data": {
            "fed": fed,
            "recession": recession,
            "btc": btc,
            "geopolitical": geo,
            "market_movers": movers,
        },
    }


# ──────────────────────────────────────────
# レポートフォーマット
# ──────────────────────────────────────────
def format_telegram_report(assessment: dict) -> str:
    """Telegram用フォーマット"""
    score = assessment["risk_score"]

    if score >= 50:
        level = "RISK OFF"
    elif score >= 30:
        level = "CAUTIOUS"
    elif score >= 15:
        level = "HEDGE"
    else:
        level = "ALL CLEAR"

    sources = ", ".join(assessment.get("data_sources", ["unknown"]))
    lines = [
        "Prediction Market Intelligence",
        f"Risk Score: {score}/100 [{level}]",
        f"Action: {assessment['action_detail']}",
        f"Sources: {sources}",
        "",
    ]

    fed = assessment["data"]["fed"]
    if fed["details"]:
        lines.append("FRB Outlook:")
        lines.append(f"  Rate Cut: {fed['rate_cut_prob']*100:.1f}%")
        lines.append(f"  No Change: {fed['no_change_prob']*100:.1f}%")
        lines.append("")

    btc = assessment["data"]["btc"]
    if btc["price_levels"]:
        lines.append("BTC Price Levels:")
        for pl in btc["price_levels"][:5]:
            lines.append(f"  {(pl['question'] or '')[:50]}: {pl['prob']*100:.1f}%")
        lines.append("")

    geo = assessment["data"]["geopolitical"]
    if geo["conflict_prob"] > 0:
        lines.append(f"Geopolitical: Conflict {geo['conflict_prob']*100:.0f}%")
        lines.append("")

    movers = assessment["data"]["market_movers"]
    if movers.get("movers"):
        lines.append("Top Market Movers (24h):")
        for m in movers["movers"][:5]:
            direction = "+" if m["change_24h"] >= 0 else ""
            lines.append(f"  [{m['exchange']}] {(m['question'] or '')[:45]}: {direction}{m['change_24h']*100:.1f}%")
        lines.append("")

    if assessment["alerts"]:
        lines.append("ALERTS:")
        for a in assessment["alerts"]:
            lines.append(f"  {a}")

    return "\n".join(lines)


# ──────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────
if __name__ == "__main__":
    print("=== QE Prediction Market Intelligence ===\n")
    print("Initializing SDKs...")
    _init_sdks()

    sdk_status = []
    if _pmxt_polymarket:
        sdk_status.append("pmxt:Polymarket")
    if _pmxt_kalshi:
        sdk_status.append("pmxt:Kalshi")
    if _clob_client:
        sdk_status.append("py-clob-client")
    sdk_status.append("Gamma-REST (fallback)")
    print(f"Active: {', '.join(sdk_status)}\n")

    assessment = generate_risk_assessment()
    report = format_telegram_report(assessment)
    print(report)

    out_path = "/Users/mr.k/Projects/and-ai-brain/prediction_market_data.json"
    with open(out_path, "w") as f:
        json.dump(assessment, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {out_path}")
