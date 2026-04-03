"""
&AI BRAIN - プラグインアーキテクチャ v1.0
全データソースを統一インターフェースで管理
"""

from abc import ABC, abstractmethod
from typing import Any


# 標準スキーマ定義
# {
#   "ticker": "BTC",
#   "timestamp": "2026-03-29T22:00:00",
#   "value": 66750.0,
#   "source": "hyperliquid",
#   "confidence": 1.0,
#   "category": "price",  # price/sentiment/macro/onchain/fundamental
#   "metadata": {}
# }


class DataPlugin(ABC):
    """全プラグインの基底クラス"""

    @abstractmethod
    def fetch(self) -> list[dict]:
        """データ取得 → 標準スキーマのリストを返す"""
        ...

    def get_schema(self) -> dict:
        """標準スキーマのサンプルを返す"""
        return {
            "ticker": str,
            "timestamp": str,
            "value": float,
            "source": str,
            "confidence": float,
            "category": str,  # price/sentiment/macro/onchain/fundamental
            "metadata": dict,
        }

    def _make_record(
        self,
        ticker: str,
        value: float,
        source: str,
        category: str,
        confidence: float = 1.0,
        metadata: dict | None = None,
    ) -> dict:
        """標準スキーマレコードを生成するヘルパー"""
        from datetime import datetime
        return {
            "ticker": ticker,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "value": value,
            "source": source,
            "confidence": confidence,
            "category": category,
            "metadata": metadata or {},
        }


# 利用可能プラグイン一覧
__all__ = ["DataPlugin"]
