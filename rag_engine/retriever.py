"""
RAG 检索器 — 对外暴露标准接口，供 Student A 的 LangGraph 节点调用。
使用前必须先运行 build_index.py 完成建库。
"""

from pathlib import Path

from sentence_transformers import SentenceTransformer
import chromadb

CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "autoaudit_poc_knowledge"

# 模块级单例，避免每次调用重复加载模型
_embedding_model: SentenceTransformer | None = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _embedding_model


def _get_collection():
    global _collection
    if _collection is None:
        if not CHROMA_DIR.exists():
            raise RuntimeError(
                "ChromaDB 数据库不存在！\n"
                "请先在 Anaconda Prompt 中运行：python rag_engine/build_index.py"
            )
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            _collection = client.get_collection(COLLECTION_NAME)
        except Exception:
            raise RuntimeError(
                f"集合 '{COLLECTION_NAME}' 不存在！\n"
                "请先在 Anaconda Prompt 中运行：python rag_engine/build_index.py"
            )
    return _collection


def retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]:
    """
    根据漏洞特征描述，从 ChromaDB 中检索最相关的历史 PoC 记录。

    Args:
        vulnerability_description: 漏洞的自然语言描述（由 Student A 的 Auditor Node 传入）
        top_k: 返回条数，MVP 阶段固定为 2

    Returns:
        list of dict，每条包含:
            vuln_type, source_protocol, description, poc_template, similarity_score
    """
    model = _get_model()
    collection = _get_collection()

    # bge 模型查询时加前缀可提升召回质量
    query_text = (
        f"Represent this sentence for searching relevant passages: "
        f"{vulnerability_description}"
    )
    query_embedding = model.encode(query_text, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for i in range(len(results["ids"][0])):
        metadata = results["metadatas"][0][i]
        # cosine distance → similarity
        similarity = round(1.0 - results["distances"][0][i], 4)
        output.append(
            {
                "vuln_type": metadata["vuln_type"],
                "source_protocol": metadata["protocol_name"],
                "description": results["documents"][0][i],
                "poc_template": metadata["poc_template"],
                "similarity_score": similarity,
            }
        )

    return output


# PyCharm 中右键 Run 这个文件可快速验证
if __name__ == "__main__":
    query = "external call made before balance state update allows recursive withdrawal reentrancy attack"
    print(f"查询：{query}\n")
    results = retrieve_similar_poc(query, top_k=2)
    for i, r in enumerate(results):
        print(f"[{i + 1}] {r['vuln_type']} | {r['source_protocol']}")
        print(f"     相似度: {r['similarity_score']}")
        print(f"     描述: {r['description'][:100]}...")
        print()
