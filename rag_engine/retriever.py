"""
Retriever for AutoAudit RAG.

Public API contract:
    retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]
New optional helper:
    warmup_retriever() -> None
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer

CHROMA_DIR = Path(__file__).parent / "chroma_db"
DATA_DIR = Path(__file__).parent / "data"
COLLECTION_NAME = "autoaudit_poc_knowledge"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_TOP_N = 8
DEFAULT_MIN_SCORE = 0.62

_embedding_model: SentenceTransformer | None = None
_collection = None
_records_by_id: dict[str, dict[str, Any]] | None = None
_idf_by_token: dict[str, float] | None = None


def _configure_model_logging() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    try:
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except Exception:
        pass
    try:
        from transformers.utils import logging as transformers_logging

        transformers_logging.set_verbosity_error()
    except Exception:
        pass


_configure_model_logging()


def _get_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def _get_collection():
    global _collection
    if _collection is not None:
        try:
            # Ensure cached handle is still valid after rebuild.
            _collection.count()
            return _collection
        except NotFoundError:
            _collection = None

    if _collection is None:
        if not CHROMA_DIR.exists():
            raise RuntimeError(
                "ChromaDB not found. Please run: python rag_engine/build_index.py"
            )
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            _collection = client.get_collection(COLLECTION_NAME)
        except Exception as e:
            raise RuntimeError(
                f"Collection '{COLLECTION_NAME}' not found. "
                "Please run: python rag_engine/build_index.py"
            ) from e
    return _collection


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    out = text.lower()
    replacements = [
        (r"\breenter(?:ing|ed)?\b", "reentrancy"),
        (r"\breentrant\b", "reentrancy"),
        (r"\bflash[\s_-]*loan\b", "flashloan"),
        (r"\berc[\s_-]*777\b", "erc777"),
        (r"\berc[\s_-]*20\b", "erc20"),
        (r"\bprice[\s_-]*oracle\b", "oracle"),
    ]
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out)
    out = re.sub(r"[^a-z0-9\s]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _tokenize(text: str) -> list[str]:
    norm = _normalize_text(text)
    if not norm:
        return []
    tokens = norm.split(" ")
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "for",
        "of",
        "on",
        "in",
        "by",
        "with",
        "is",
        "are",
        "be",
        "from",
        "this",
        "that",
        "it",
        "as",
    }
    return [t for t in tokens if t and t not in stopwords]


def _load_records_index() -> dict[str, dict[str, Any]]:
    global _records_by_id
    if _records_by_id is not None:
        return _records_by_id

    records: dict[str, dict[str, Any]] = {}
    for f in sorted(DATA_DIR.glob("*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        rid = str(raw.get("id", "")).strip()
        if not rid:
            continue
        records[rid] = raw
    _records_by_id = records
    return _records_by_id


def _build_doc_idf() -> dict[str, float]:
    global _idf_by_token
    if _idf_by_token is not None:
        return _idf_by_token

    records = _load_records_index()
    if not records:
        _idf_by_token = {}
        return _idf_by_token

    docs = [str(rec.get("description", "")) for rec in records.values()]
    n_docs = len(docs)
    df = Counter()
    for doc in docs:
        df.update(set(_tokenize(doc)))

    idf: dict[str, float] = {}
    for token, freq in df.items():
        idf[token] = math.log((n_docs + 1) / (freq + 1)) + 1.0
    _idf_by_token = idf
    return _idf_by_token


@lru_cache(maxsize=256)
def _encode_query_cached(normalized_query: str) -> tuple[float, ...]:
    model = _get_model()
    query_text = (
        "Represent this sentence for searching relevant passages: "
        + normalized_query
    )
    embedding = model.encode(
        query_text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return tuple(float(v) for v in embedding.tolist())


def _sparse_score(query_tokens: list[str], doc_text: str, idf: dict[str, float]) -> float:
    if not query_tokens:
        return 0.0
    doc_tokens = set(_tokenize(doc_text))
    overlap = doc_tokens.intersection(query_tokens)
    if not overlap:
        return 0.0

    numerator = sum(idf.get(tok, 1.0) for tok in overlap)
    denominator = sum(idf.get(tok, 1.0) for tok in query_tokens)
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _get_min_score() -> float:
    raw = os.environ.get("RAG_MIN_SCORE")
    if not raw:
        return DEFAULT_MIN_SCORE
    try:
        val = float(raw)
    except Exception:
        return DEFAULT_MIN_SCORE
    return max(0.0, min(1.0, val))


def warmup_retriever() -> None:
    _get_collection()
    _get_model()
    _load_records_index()
    _build_doc_idf()
    _encode_query_cached("warmup reentrancy flashloan oracle")


def retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]:
    if top_k <= 0:
        return []

    norm_query = _normalize_text(vulnerability_description)
    if not norm_query:
        return []

    collection = _get_collection()
    record_by_id = _load_records_index()
    idf_by_token = _build_doc_idf()
    query_tokens = _tokenize(norm_query)

    count = collection.count()
    if count <= 0:
        return []

    top_n = min(count, max(DEFAULT_TOP_N, top_k * 4))
    query_embedding = list(_encode_query_cached(norm_query))

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_n,
        include=["documents", "metadatas", "distances"],
    )

    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    ranked: list[dict[str, Any]] = []
    for i in range(len(ids)):
        rid = ids[i]
        dense = 1.0 - float(dists[i]) if i < len(dists) else 0.0
        dense = max(0.0, min(1.0, dense))
        doc_text = docs[i] if i < len(docs) and docs[i] else ""
        sparse = _sparse_score(query_tokens, doc_text, idf_by_token)
        hybrid = 0.75 * dense + 0.25 * sparse

        meta = metas[i] if i < len(metas) and metas[i] else {}
        raw = record_by_id.get(rid, {})
        ranked.append(
            {
                "id": rid,
                "vuln_type": meta.get("vuln_type") or raw.get("vuln_type", ""),
                "source_protocol": meta.get("protocol_name")
                or raw.get("protocol_name", ""),
                "description": raw.get("description", ""),
                "poc_template": raw.get("poc_template", ""),
                "dense_score": dense,
                "sparse_score": sparse,
                "similarity_score": round(max(0.0, min(1.0, hybrid)), 4),
            }
        )

    ranked.sort(key=lambda x: x["similarity_score"], reverse=True)
    ranked = ranked[:top_k]

    if not ranked:
        return []
    if ranked[0]["similarity_score"] < _get_min_score():
        return []

    # keep output contract stable
    output = []
    for item in ranked:
        output.append(
            {
                "vuln_type": item["vuln_type"],
                "source_protocol": item["source_protocol"],
                "description": item["description"],
                "poc_template": item["poc_template"],
                "similarity_score": item["similarity_score"],
            }
        )
    return output


if __name__ == "__main__":
    warmup_retriever()
    query = "contract sends Ether before updating balance allowing attacker to reenter withdraw"
    out = retrieve_similar_poc(query, top_k=2)
    print(f"query: {query}")
    for idx, item in enumerate(out, start=1):
        print(
            f"[{idx}] {item['source_protocol']} | {item['vuln_type']} | score={item['similarity_score']}"
        )
