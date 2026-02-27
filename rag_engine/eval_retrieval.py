"""
Evaluation script for RAG retrieval quality and latency.

Usage:
    python rag_engine/eval_retrieval.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_engine.retriever import retrieve_similar_poc, warmup_retriever

DATA_DIR = Path(__file__).parent / "data"


def _load_records() -> list[dict]:
    rows = []
    for f in sorted(DATA_DIR.glob("*.json")):
        rows.append(json.loads(f.read_text(encoding="utf-8")))
    return rows


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _eval_canonical(records: list[dict]) -> tuple[float, float]:
    hit1 = 0
    hit2 = 0
    for rec in records:
        out = retrieve_similar_poc(rec["description"], top_k=2)
        top1 = out[0]["source_protocol"] if len(out) >= 1 else ""
        top2 = [item["source_protocol"] for item in out[:2]]
        expected = rec["protocol_name"].lower()
        ok1 = expected in top1.lower()
        ok2 = any(expected in p.lower() for p in top2)
        hit1 += 1 if ok1 else 0
        hit2 += 1 if ok2 else 0
    total = max(1, len(records))
    return hit1 / total, hit2 / total


def _eval_paraphrase() -> tuple[float, float]:
    tests = [
        {
            "query": (
                "External call sends ETH before balance reset. "
                "Attacker fallback recursively calls withdraw."
            ),
            "expect": "EtherStore",
        },
        {
            "query": (
                "ERC777 receive hook reenters lending logic before account state update."
            ),
            "expect": "Lendf.Me",
        },
        {
            "query": (
                "Single transaction flashloan manipulates AMM spot price oracle then "
                "mints overvalued assets."
            ),
            "expect": "PancakeBunny",
        },
        {
            "query": (
                "Flashloan drives temporary market distortion and protocol reads bad "
                "price as trusted collateral value."
            ),
            "expect": "Cream Finance",
        },
    ]
    hit1 = 0
    hit2 = 0
    for row in tests:
        out = retrieve_similar_poc(row["query"], top_k=2)
        top1 = out[0]["source_protocol"] if len(out) >= 1 else ""
        top2 = [item["source_protocol"] for item in out[:2]]
        expected = row["expect"].lower()
        ok1 = expected in top1.lower()
        ok2 = any(expected in p.lower() for p in top2)
        hit1 += 1 if ok1 else 0
        hit2 += 1 if ok2 else 0
    total = len(tests)
    return hit1 / total, hit2 / total


def _eval_irrelevant() -> tuple[float, float, float]:
    tests = [
        "Integer overflow mints unlimited tokens in arithmetic accounting.",
        "Missing onlyOwner allows arbitrary admin parameter updates.",
        "Timestamp dependence enables lottery manipulation by block producers.",
        "Unchecked low-level call return value causes silent transfer failures.",
    ]
    scores = []
    empty_count = 0
    for q in tests:
        out = retrieve_similar_poc(q, top_k=1)
        if not out:
            empty_count += 1
            scores.append(0.0)
        else:
            scores.append(float(out[0]["similarity_score"]))
    avg_score = statistics.mean(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    empty_rate = empty_count / len(tests) if tests else 0.0
    return avg_score, max_score, empty_rate


def _eval_latency() -> tuple[float, float]:
    query = "contract sends Ether before updating state and attacker reenters withdraw"
    t0 = time.perf_counter()
    retrieve_similar_poc(query, top_k=2)
    cold_ms = (time.perf_counter() - t0) * 1000

    n = 30
    t1 = time.perf_counter()
    for _ in range(n):
        retrieve_similar_poc(query, top_k=2)
    warm_avg_ms = ((time.perf_counter() - t1) * 1000) / n
    return cold_ms, warm_avg_ms


def run_evaluation() -> int:
    print("=" * 72)
    print("AutoAudit RAG Evaluation")
    print("=" * 72)

    records = _load_records()
    print(f"records: {len(records)}")

    warmup_retriever()

    recall1, recall2 = _eval_canonical(records)
    para1, para2 = _eval_paraphrase()
    irr_avg, irr_max, empty_rate = _eval_irrelevant()
    cold_ms, warm_ms = _eval_latency()

    print("-" * 72)
    print(f"Canonical Recall@1: {recall1:.3f}")
    print(f"Canonical Recall@2: {recall2:.3f}")
    print(f"Paraphrase Recall@1: {para1:.3f}")
    print(f"Paraphrase Recall@2: {para2:.3f}")
    print(f"Irrelevant avg score: {irr_avg:.3f}")
    print(f"Irrelevant max score: {irr_max:.3f}")
    print(f"Empty result rate (irrelevant): {empty_rate:.3f}")
    print(f"Cold query latency ms: {cold_ms:.2f}")
    print(f"Warm avg latency ms: {warm_ms:.2f}")
    print("-" * 72)

    checks = [
        ("Canonical Recall@1 >= 0.95", recall1 >= 0.95),
        ("Paraphrase Recall@1 >= 0.85", para1 >= 0.85),
        ("Irrelevant avg <= 0.58", irr_avg <= 0.58),
        ("Warm avg latency <= 40ms", warm_ms <= 40.0),
    ]
    for label, ok in checks:
        print(f"[{_status(ok)}] {label}")

    all_ok = all(ok for _, ok in checks)
    print("=" * 72)
    print("FINAL: " + ("PASS" if all_ok else "FAIL"))
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run_evaluation())
