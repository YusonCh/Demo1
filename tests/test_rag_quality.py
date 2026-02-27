import json
from pathlib import Path

from rag_engine.indexer import build_index
import rag_engine.retriever as retriever


DATA_DIR = Path(__file__).resolve().parent.parent / "rag_engine" / "data"


def _records():
    rows = []
    for f in sorted(DATA_DIR.glob("*.json")):
        rows.append(json.loads(f.read_text(encoding="utf-8")))
    return rows


def test_rag_quality_thresholds():
    build_index(force_rebuild=True, batch_size=16, quiet=True)
    retriever._collection = None
    retriever._encode_query_cached.cache_clear()
    retriever.warmup_retriever()

    records = _records()
    assert len(records) >= 20

    # Canonical Recall@1
    hit = 0
    for rec in records:
        out = retriever.retrieve_similar_poc(rec["description"], top_k=1)
        top = out[0]["source_protocol"] if out else ""
        hit += 1 if rec["protocol_name"].lower() in top.lower() else 0
    recall1 = hit / len(records)
    assert recall1 >= 0.95

    # Paraphrase Recall@1 on representative anchors
    paraphrase_cases = [
        (
            "Ether transfer before state update enables recursive withdraw in fallback.",
            "EtherStore",
        ),
        (
            "ERC777 tokensReceived hook triggers reentry before lending state is settled.",
            "Lendf.Me",
        ),
        (
            "One block flashloan distorts AMM spot oracle and mints overvalued rewards.",
            "PancakeBunny",
        ),
        (
            "Attacker combines flashloan liquidity and stale collateral accounting windows.",
            "Cream Finance",
        ),
    ]
    para_hit = 0
    for query, expected in paraphrase_cases:
        out = retriever.retrieve_similar_poc(query, top_k=1)
        top = out[0]["source_protocol"] if out else ""
        para_hit += 1 if expected.lower() in top.lower() else 0
    para_recall1 = para_hit / len(paraphrase_cases)
    assert para_recall1 >= 0.85

    # Irrelevant average score and empty-result behavior
    irrelevant_queries = [
        "Integer overflow allows arbitrary token minting by wrapping uint math.",
        "Missing onlyOwner permits unauthorized protocol parameter updates.",
        "Timestamp dependence in lottery contracts allows miner manipulation.",
    ]
    scores = []
    empty_count = 0
    for query in irrelevant_queries:
        out = retriever.retrieve_similar_poc(query, top_k=1)
        if not out:
            scores.append(0.0)
            empty_count += 1
        else:
            scores.append(float(out[0]["similarity_score"]))

    avg_score = sum(scores) / len(scores)
    assert avg_score <= 0.58
    assert empty_count >= 1
