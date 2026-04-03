"""
&AI QUANTUM EDGE - LightRAG 金融データ検索エンジン
dexter-jpの財務データ・バフェットナレッジ・市場レポートを
ローカルでRAG検索できるシステム

使い方:
    from lightrag_finance import FinanceRAG
    rag = FinanceRAG()
    result = rag.query("トヨタの財務状況は？")
"""

import os, asyncio
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

LIGHTRAG_DIR = "/Users/mr.k/Projects/and-ai-brain/lightrag_data"
os.makedirs(LIGHTRAG_DIR, exist_ok=True)


async def init_rag():
    """LightRAGを初期化"""
    from lightrag import LightRAG, QueryParam
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc
    import numpy as np

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    async def claude_complete(prompt, system_prompt=None, **kwargs):
        """Claude APIでテキスト生成"""
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        messages = [{"role": "user", "content": prompt}]
        response = client.messages.create(
            model="claude-haiku-4-5",  # コスト最小
            max_tokens=1000,
            system=system_prompt or "You are a financial analysis assistant.",
            messages=messages
        )
        return response.content[0].text

    async def embed_text(texts):
        """テキストをベクトル化（OpenAI互換）"""
        # シンプルなハッシュベースの埋め込み（APIキーなしで動作）
        import hashlib
        embeddings = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            # 256次元のベクトルに変換
            vec = [((b / 255.0) - 0.5) * 2 for b in h]
            # 1536次元にパディング
            vec = vec * 6  # 256*6 = 1536
            embeddings.append(vec[:1536])
        return np.array(embeddings, dtype=np.float32)

    rag = LightRAG(
        working_dir=LIGHTRAG_DIR,
        llm_model_func=claude_complete,
        embedding_func=EmbeddingFunc(
            embedding_dim=1536,
            max_token_size=8192,
            func=embed_text,
        ),
    )
    return rag


class FinanceRAG:
    """金融データのRAG検索クラス"""

    def __init__(self):
        self.rag = None

    async def _init(self):
        if not self.rag:
            self.rag = await init_rag()

    async def add_document(self, text: str, source: str = ""):
        """ドキュメントを追加"""
        await self._init()
        await self.rag.ainsert(text)
        print(f"✅ ドキュメント追加: {source[:50]}")

    async def query(self, question: str, mode: str = "hybrid") -> str:
        """質問に回答"""
        await self._init()
        from lightrag import QueryParam
        result = await self.rag.aquery(
            question,
            param=QueryParam(mode=mode)
        )
        return result

    def add_market_report(self, report_text: str):
        """市場レポートを追加（同期版）"""
        asyncio.run(self.add_document(report_text, "market_report"))

    def search(self, question: str) -> str:
        """検索（同期版）"""
        return asyncio.run(self.query(question))


if __name__ == "__main__":
    print("⚛️ LightRAG 金融データ検索エンジン テスト")
    import asyncio

    async def test():
        rag = FinanceRAG()

        # テストドキュメントを追加
        test_doc = """
        トヨタ自動車（7203.T）2026年3月期 財務分析
        
        売上高: 45兆円（前年比+8%）
        営業利益: 4.5兆円（過去最高）
        ROE: 15.2%
        自己資本比率: 38.5%
        
        EV戦略: 2026年までに電気自動車30車種投入予定
        主要リスク: 半導体不足、円安影響、中国市場競争激化
        
        バフェット評価: 優良バリュー株。長期保有に適した堅固なビジネスモデル。
        """

        await rag.add_document(test_doc, "トヨタ財務分析")
        print("✅ ドキュメント追加完了")

        # 質問テスト
        result = await rag.query("トヨタのROEと自己資本比率は？")
        print(f"\n質問: トヨタのROEと自己資本比率は？")
        print(f"回答: {result[:200]}")

    asyncio.run(test())
