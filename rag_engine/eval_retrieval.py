"""
RAG 检索质量评估脚本 — Demo Day 直接跑这个向导师展示 H1 假设成立。

运行方式（Anaconda Prompt 项目根目录下）：
    python rag_engine/eval_retrieval.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_engine.retriever import retrieve_similar_poc


def run_evaluation():
    print("=" * 62)
    print("  AutoAudit RAG 检索质量评估报告")
    print("  验证目标：假设 H1（RAG 知识库能精准召回相关 PoC 模板）")
    print("=" * 62)

    # ── 测试组 1：相关查询，期望高分命中 ────────────────────────
    relevant_tests = [
        {
            "label": "重入漏洞（应命中 EtherStore）",
            "query": "The contract sends Ether to external address before updating "
                     "internal balance, allowing attacker fallback to recursively call "
                     "withdraw and drain all funds",
            "expected_protocol": "EtherStore",
        },
        {
            "label": "ERC777 重入（应命中 Lendf.Me）",
            "query": "ERC777 tokensReceived callback hook triggers reentry into lending "
                     "supply function before balance is updated enabling overborrowing",
            "expected_protocol": "Lendf.Me",
        },
        {
            "label": "闪电贷价格操纵（应命中 PancakeBunny）",
            "query": "Flash loan used to manipulate AMM spot price oracle, protocol mints "
                     "tokens at inflated price, attacker dumps tokens for profit in single tx",
            "expected_protocol": "PancakeBunny",
        },
    ]

    # ── 测试组 2：无关查询，期望相似度 < 0.5 ────────────────────
    irrelevant_tests = [
        {
            "label": "整数溢出（知识库中无此类型）",
            "query": "Arithmetic wraparound in balance calculation when adding large numbers exceeds maximum value",
        },
        {
            "label": "访问控制缺失（知识库中无此类型）",
            "query": "Missing permission check on administrative function allows unauthorized state modification",
        },
    ]

    # ── 评估相关查询 ─────────────────────────────────────────────
    print("\n【测试组 1】相关漏洞查询 — 期望 Top-1 精准命中")
    print("-" * 62)

    passed = 0
    for test in relevant_tests:
        results = retrieve_similar_poc(test["query"], top_k=2)
        top1 = results[0] if results else None
        hit = top1 is not None and test["expected_protocol"].lower() in top1["source_protocol"].lower()
        score = top1["similarity_score"] if top1 else 0.0

        if hit:
            passed += 1
        status = "✅ PASS" if hit else "❌ FAIL"

        print(f"\n  查询: {test['label']}")
        print(f"  Top-1: {top1['source_protocol'] if top1 else 'None'}  ({top1['vuln_type'] if top1 else 'N/A'})")
        print(f"  相似度: {score}")
        print(f"  结果: {status}")

    recall_at_1 = passed / len(relevant_tests)
    print(f"\n  >>> Recall@1 = {passed}/{len(relevant_tests)} = {recall_at_1:.2f}")

    # ── 评估无关查询 ─────────────────────────────────────────────
    print("\n【测试组 2】无关漏洞查询 — 期望相似度 < 0.5（无误召回）")
    print("-" * 62)

    no_fp = True
    for test in irrelevant_tests:
        results = retrieve_similar_poc(test["query"], top_k=1)
        top1 = results[0] if results else None
        score = top1["similarity_score"] if top1 else 0.0
        low = score < 0.6
        if not low:
            no_fp = False

        status = "✅ PASS（无误召回）" if low else f"⚠️  WARN（分数 {score} 偏高）"
        print(f"\n  查询: {test['label']}")
        print(f"  Top-1: {top1['source_protocol'] if top1 else 'None'}  相似度: {score}")
        print(f"  结果: {status}")

    # ── 总结 ─────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print("  评估总结")
    print("=" * 62)
    r1_ok = recall_at_1 == 1.0
    print(f"  Recall@1（精准命中率）:  {recall_at_1:.0%}   {'✅' if r1_ok else '❌'}")
    print(f"  误召回控制:              {'✅ 通过' if no_fp else '⚠️ 需关注'}")

    if r1_ok and no_fp:
        print("\n  🎉 假设 H1 验证通过：RAG 知识库检索质量达标，可用于 Demo。")
    else:
        print("\n  ⚠️  部分指标未达标，请检查 JSON 数据或重建索引：")
        print("      python rag_engine/build_index.py --rebuild")
    print("=" * 62)


if __name__ == "__main__":
    run_evaluation()