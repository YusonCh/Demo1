import json
from pathlib import Path

import pytest

from rag_engine import indexer, retriever


class _FakeEmbeddings:
    def __init__(self, rows):
        self._rows = rows

    def tolist(self):
        return self._rows


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False):
        if isinstance(texts, str):
            texts = [texts]
        rows = []
        for t in texts:
            base = float((sum(ord(c) for c in t) % 97) + 1)
            rows.append([base / 100.0, 0.5, 0.25])
        return _FakeEmbeddings(rows)


def _write_record(path: Path, rec_id: str, protocol: str, desc: str):
    payload = {
        "id": rec_id,
        "vuln_type": "SWC-107-Reentrancy",
        "protocol_name": protocol,
        "attack_date": "2024-01-01",
        "description": desc,
        "poc_template": f"// poc {protocol}",
        "tags": ["reentrancy"],
        "attack_primitives": ["external-call-before-state-update"],
        "aliases": [protocol.lower()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_indexer_incremental_build(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    db_dir = tmp_path / "db"
    data_dir.mkdir(parents=True, exist_ok=True)

    _write_record(data_dir / "001_a.json", "001", "A", "a desc")
    _write_record(data_dir / "002_b.json", "002", "B", "b desc")
    _write_record(data_dir / "003_c.json", "003", "C", "c desc")

    monkeypatch.setattr(indexer, "DATA_DIR", data_dir)
    monkeypatch.setattr(indexer, "CHROMA_DIR", db_dir)
    monkeypatch.setattr(indexer, "MANIFEST_PATH", db_dir / "manifest.json")
    monkeypatch.setattr(indexer, "_get_model", lambda: _FakeModel())

    stats1 = indexer.build_index(force_rebuild=True, batch_size=2, quiet=True)
    assert stats1["total_records"] == 3
    assert stats1["processed_records"] == 3
    assert stats1["removed_records"] == 0
    assert stats1["collection_count"] == 3

    # one updated, one removed, one added
    _write_record(data_dir / "002_b.json", "002", "B", "b desc changed")
    (data_dir / "003_c.json").unlink()
    _write_record(data_dir / "004_d.json", "004", "D", "d desc")

    stats2 = indexer.build_index(force_rebuild=False, batch_size=2, quiet=True)
    assert stats2["total_records"] == 3
    assert stats2["processed_records"] == 2
    assert stats2["removed_records"] == 1
    assert stats2["collection_count"] == 3


def test_retriever_missing_index_error(monkeypatch, tmp_path):
    missing = tmp_path / "missing_db_dir"
    monkeypatch.setattr(retriever, "CHROMA_DIR", missing)
    monkeypatch.setattr(retriever, "_collection", None)

    with pytest.raises(RuntimeError, match="build_index.py"):
        retriever.retrieve_similar_poc("reentrancy", top_k=1)
