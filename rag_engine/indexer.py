"""
RAG 知识库索引器
将 data/ 目录下的 JSON 文件嵌入并写入 ChromaDB。
"""

import json
from pathlib import Path

from sentence_transformers import SentenceTransformer
import chromadb

# ── 路径配置 ──────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "autoaudit_poc_knowledge"

# ── 全局模型（首次运行自动下载约 130MB，之后复用缓存）────────────
print("正在加载嵌入模型 bge-small-en-v1.5 ...")
embedding_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
print("模型加载完成。\n")


def get_chroma_collection():
    """获取或创建 ChromaDB 持久化集合。"""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def load_all_records() -> list[dict]:
    """从 data/ 目录读取所有 JSON 文件。"""
    records = []
    json_files = sorted(DATA_DIR.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(
            f"data/ 目录下没有找到 JSON 文件！路径：{DATA_DIR.resolve()}"
        )
    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            record = json.load(f)
            records.append(record)
            print(f"  已加载: {json_file.name}  ->  {record['protocol_name']}")
    return records


def build_index(force_rebuild: bool = False) -> None:
    """
    构建 ChromaDB 索引。

    Args:
        force_rebuild: True 时先清空旧索引再重建。
    """
    collection = get_chroma_collection()

    existing_count = collection.count()
    if existing_count > 0 and not force_rebuild:
        print(f"索引已存在（{existing_count} 条记录），跳过重建。")
        print("如需重建，请在 build_index.py 中传入 --rebuild 参数。")
        return

    if force_rebuild and existing_count > 0:
        print("强制重建：清空旧索引...")
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        client.delete_collection(COLLECTION_NAME)
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    print("开始构建 RAG 知识库索引...")
    records = load_all_records()

    ids, documents, metadatas = [], [], []

    for record in records:
        ids.append(record["id"])
        # 嵌入 description（自然语言），poc_template 作为 metadata 存储
        documents.append(record["description"])
        metadatas.append(
            {
                "vuln_type": record["vuln_type"],
                "protocol_name": record["protocol_name"],
                "attack_date": record["attack_date"],
                "poc_template": record["poc_template"],
            }
        )

    print(f"\n正在嵌入 {len(documents)} 条记录（建库时不加前缀）...")
    embedding_vectors = embedding_model.encode(
        documents, normalize_embeddings=True
    ).tolist()

    collection.add(
        ids=ids,
        embeddings=embedding_vectors,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"\n✅ 索引构建完成！共写入 {collection.count()} 条记录。")
    print(f"   数据库路径: {CHROMA_DIR.resolve()}")