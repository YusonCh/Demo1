from rag_engine import retriever


class _DummyCollection:
    def count(self):
        return 3

    def query(self, query_embeddings, n_results, include):
        assert len(query_embeddings) == 1
        assert n_results == 3
        return {
            "ids": [["001", "002", "003"]],
            "documents": [[
                "reentrancy external call before state update",
                "erc777 callback reentrancy",
                "flashloan oracle manipulation",
            ]],
            "metadatas": [[
                {"vuln_type": "SWC-107-Reentrancy", "protocol_name": "EtherStore"},
                {"vuln_type": "SWC-107-Reentrancy", "protocol_name": "Lendf.Me"},
                {"vuln_type": "Flashloan-Oracle-Manipulation", "protocol_name": "PancakeBunny"},
            ]],
            "distances": [[0.1, 0.2, 0.5]],
        }


def _patch_common(monkeypatch):
    monkeypatch.setattr(retriever, "_get_collection", lambda: _DummyCollection())
    monkeypatch.setattr(
        retriever,
        "_load_records_index",
        lambda: {
            "001": {"description": "d1", "poc_template": "p1"},
            "002": {"description": "d2", "poc_template": "p2"},
            "003": {"description": "d3", "poc_template": "p3"},
        },
    )
    monkeypatch.setattr(retriever, "_build_doc_idf", lambda: {"reentrancy": 1.0, "oracle": 1.0})
    monkeypatch.setattr(retriever, "_get_min_score", lambda: 0.0)
    monkeypatch.setattr(retriever, "_encode_query_cached", lambda _: (0.1, 0.2, 0.3))


def test_retrieve_contract_fields_and_order(monkeypatch):
    _patch_common(monkeypatch)
    out = retriever.retrieve_similar_poc(
        "Contract sends ether before updating state enabling reentrancy", top_k=2
    )
    assert len(out) == 2
    for row in out:
        assert set(row.keys()) == {
            "vuln_type",
            "source_protocol",
            "description",
            "poc_template",
            "similarity_score",
        }
    assert out[0]["source_protocol"] == "EtherStore"


def test_retrieve_topk_boundaries(monkeypatch):
    _patch_common(monkeypatch)
    assert retriever.retrieve_similar_poc("x", top_k=0) == []
    assert retriever.retrieve_similar_poc("x", top_k=-1) == []
    out = retriever.retrieve_similar_poc("x", top_k=100)
    assert 0 < len(out) <= 3
