"""
&AI BRAIN - オンチェーンデータプラグイン
Whale Alert: クジラ取引監視
"""

import os
import time
import requests
from plugins import DataPlugin


class OnchainPlugin(DataPlugin):
    """オンチェーンデータプラグイン"""

    def fetch(self) -> list[dict]:
        records = []
        whale_data = get_whale_alerts()

        if isinstance(whale_data, dict) and whale_data:
            net = whale_data.get("net_flow", 0)
            records.append(self._make_record(
                ticker="CRYPTO",
                value=float(net),
                source="whale_alert",
                category="onchain",
                confidence=0.9,
                metadata={
                    "exchange_inflow": whale_data.get("exchange_inflow", 0),
                    "exchange_outflow": whale_data.get("exchange_outflow", 0),
                    "signal": whale_data.get("signal", ""),
                    "large_tx_count": len(whale_data.get("alerts", [])),
                },
            ))

        return records


# ========================================
# 個別取得関数（後方互換性のため維持）
# ========================================

def get_whale_alerts() -> dict:
    """Whale Alert: $1M以上のクジラ取引を監視"""
    key = os.environ.get("WHALE_ALERT_KEY", "")
    if not key:
        return {}

    try:
        r = requests.get(
            "https://api.whale-alert.io/v1/transactions",
            params={
                "api_key": key,
                "min_value": 1000000,       # $1M以上
                "start": int(time.time()) - 3600 * 4,  # 過去4時間
            },
            timeout=10,
        )

        if r.status_code != 200:
            return {}

        txs = r.json().get("transactions", [])

        alerts = []
        exchange_inflow = 0   # 取引所入金（売り圧）
        exchange_outflow = 0  # 取引所出金（HODL）

        for tx in txs:
            amount_usd = tx.get("amount_usd", 0)
            symbol = tx.get("symbol", "").upper()
            from_type = tx.get("from", {}).get("owner_type", "unknown")
            to_type = tx.get("to", {}).get("owner_type", "unknown")

            if symbol not in ["BTC", "ETH", "USDT", "USDC", "TRX", "XRP"]:
                continue

            if to_type == "exchange":
                exchange_inflow += amount_usd
            elif from_type == "exchange":
                exchange_outflow += amount_usd

            if amount_usd >= 10_000_000:  # $10M以上は個別通知
                alerts.append({
                    "symbol": symbol,
                    "amount_usd": amount_usd,
                    "direction": (
                        "sell" if to_type == "exchange"
                        else "buy" if from_type == "exchange"
                        else "transfer"
                    ),
                    "from": from_type,
                    "to": to_type,
                })

        return {
            "alerts": alerts,
            "exchange_inflow": exchange_inflow,
            "exchange_outflow": exchange_outflow,
            "net_flow": exchange_outflow - exchange_inflow,
            "signal": (
                "🟢 出金多（HODL傾向）" if exchange_outflow > exchange_inflow * 1.5
                else "🔴 入金多（売り圧力）" if exchange_inflow > exchange_outflow * 1.5
                else "⚪ 中立"
            ),
        }
    except Exception:
        return {}


def format_whale_section(whale_data: dict) -> str:
    """クジラセクションをフォーマット"""
    if not whale_data:
        return ""

    net = whale_data.get("net_flow", 0)
    signal = whale_data.get("signal", "⚪ 中立")
    inflow = whale_data.get("exchange_inflow", 0)
    outflow = whale_data.get("exchange_outflow", 0)

    section = "\n━━━━━━━━━━━━━━━\n"
    section += "🐋 *クジラ動向（過去4h）*\n"
    section += f"取引所入金: ${inflow / 1e6:.1f}M {signal}\n"
    section += f"取引所出金: ${outflow / 1e6:.1f}M\n"

    alerts = whale_data.get("alerts", [])
    if alerts:
        section += "\n⚠️ 大口取引（$10M+）:\n"
        for a in alerts[:3]:
            icon = (
                "📥" if a["direction"] == "sell"
                else "📤" if a["direction"] == "buy"
                else "🔄"
            )
            section += f"  {icon} {a['symbol']} ${a['amount_usd'] / 1e6:.1f}M\n"

    return section
