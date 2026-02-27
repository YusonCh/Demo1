import io

from rag_engine import eval_retrieval


def test_eval_script_is_gbk_safe(monkeypatch):
    monkeypatch.setattr(
        eval_retrieval,
        "_load_records",
        lambda: [
            {"protocol_name": "EtherStore", "description": "reentrancy pattern"},
            {"protocol_name": "PancakeBunny", "description": "flashloan oracle pattern"},
        ],
    )
    monkeypatch.setattr(eval_retrieval, "warmup_retriever", lambda: None)

    def fake_retrieve(query: str, top_k: int = 2):
        q = query.lower()
        if "reentrancy" in q:
            return [
                {
                    "vuln_type": "SWC-107-Reentrancy",
                    "source_protocol": "EtherStore",
                    "description": "d",
                    "poc_template": "p",
                    "similarity_score": 0.95,
                }
            ][:top_k]
        if "flashloan" in q or "oracle" in q:
            return [
                {
                    "vuln_type": "Flashloan-Oracle-Manipulation",
                    "source_protocol": "PancakeBunny",
                    "description": "d",
                    "poc_template": "p",
                    "similarity_score": 0.93,
                }
            ][:top_k]
        return []

    monkeypatch.setattr(eval_retrieval, "retrieve_similar_poc", fake_retrieve)

    sink = io.BytesIO()
    gbk_stdout = io.TextIOWrapper(sink, encoding="gbk", errors="strict")
    monkeypatch.setattr("sys.stdout", gbk_stdout)

    code = eval_retrieval.run_evaluation()
    gbk_stdout.flush()
    out = sink.getvalue().decode("gbk")

    assert code in (0, 1)
    assert "AutoAudit RAG Evaluation" in out
    assert "FINAL:" in out
