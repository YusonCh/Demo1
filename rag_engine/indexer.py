"""
RAG indexer for AutoAudit.

Key goals:
- lazy-load embedding model (no import-time heavy work)
- build structured searchable text
- support incremental index updates via a manifest hash file
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer

DATA_DIR = Path(__file__).parent / "data"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "autoaudit_poc_knowledge"
MANIFEST_PATH = CHROMA_DIR / "manifest.json"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_embedding_model: SentenceTransformer | None = None


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


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg)


def _get_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {
            "schema_version": 2,
            "model_name": MODEL_NAME,
            "records": {},
        }
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": 2,
            "model_name": MODEL_NAME,
            "records": {},
        }


def _save_manifest(records_hash: dict[str, str]) -> None:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "model_name": MODEL_NAME,
        "records": records_hash,
        "updated_at_epoch": int(time.time()),
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _validate_record(raw: dict[str, Any], src_file: Path) -> dict[str, Any]:
    required = [
        "id",
        "vuln_type",
        "protocol_name",
        "attack_date",
        "description",
        "poc_template",
    ]
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise ValueError(f"{src_file.name} missing required fields: {missing}")

    rec = dict(raw)
    rec["id"] = str(rec["id"]).strip()
    rec["vuln_type"] = str(rec["vuln_type"]).strip()
    rec["protocol_name"] = str(rec["protocol_name"]).strip()
    rec["attack_date"] = str(rec["attack_date"]).strip()
    rec["description"] = str(rec["description"]).strip()
    rec["poc_template"] = str(rec["poc_template"]).strip()
    rec["tags"] = _normalize_list(rec.get("tags"))
    rec["attack_primitives"] = _normalize_list(rec.get("attack_primitives"))
    rec["aliases"] = _normalize_list(rec.get("aliases"))
    return rec


def load_all_records() -> list[dict[str, Any]]:
    json_files = sorted(DATA_DIR.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found under: {DATA_DIR.resolve()}")

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for json_file in json_files:
        raw = json.loads(json_file.read_text(encoding="utf-8"))
        rec = _validate_record(raw, json_file)
        # 跳过重复ID，保留第一个
        if rec["id"] in seen_ids:
            print(f"Warning: Duplicate record id '{rec['id']}' in {json_file.name}, skipping")
            continue
        seen_ids.add(rec["id"])
        records.append(rec)
    return records


def build_search_text(record: dict[str, Any]) -> str:
    parts = [
        f"vuln_type: {record['vuln_type']}",
        f"protocol: {record['protocol_name']}",
    ]
    if record.get("aliases"):
        parts.append("aliases: " + " ".join(record["aliases"]))
    if record.get("tags"):
        parts.append("tags: " + " ".join(record["tags"]))
    if record.get("attack_primitives"):
        parts.append("primitives: " + " ".join(record["attack_primitives"]))
    parts.append("description: " + record["description"])
    return " | ".join(parts)


def _record_hash(record: dict[str, Any]) -> str:
    payload = {
        "id": record["id"],
        "vuln_type": record["vuln_type"],
        "protocol_name": record["protocol_name"],
        "attack_date": record["attack_date"],
        "description": record["description"],
        "poc_template": record["poc_template"],
        "tags": record.get("tags", []),
        "attack_primitives": record.get("attack_primitives", []),
        "aliases": record.get("aliases", []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _new_collection(client: chromadb.PersistentClient):
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def build_index(
    force_rebuild: bool = False,
    batch_size: int = 16,
    quiet: bool = False,
) -> dict[str, Any]:
    if batch_size <= 0:
        batch_size = 16

    t0 = time.perf_counter()
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    records = load_all_records()
    by_id = {rec["id"]: rec for rec in records}
    new_hash = {rid: _record_hash(rec) for rid, rec in by_id.items()}

    manifest = _load_manifest()
    old_hash: dict[str, str] = manifest.get("records", {})
    manifest_available = bool(old_hash)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    do_full_rebuild = force_rebuild
    if not force_rebuild:
        # If collection exists but no manifest, rebuild once to create a trustworthy baseline.
        try:
            existing_collection = client.get_collection(COLLECTION_NAME)
            if existing_collection.count() > 0 and not manifest_available:
                do_full_rebuild = True
                _log("Manifest not found, doing one-time full rebuild for consistency.", quiet)
        except Exception:
            pass

    if do_full_rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = _new_collection(client)
        changed_ids = sorted(by_id.keys())
        removed_ids: list[str] = []
    else:
        collection = _new_collection(client)
        changed_ids = sorted([rid for rid in by_id if old_hash.get(rid) != new_hash[rid]])
        removed_ids = sorted([rid for rid in old_hash if rid not in by_id])

    if removed_ids:
        collection.delete(ids=removed_ids)
        _log(f"Removed {len(removed_ids)} stale record(s).", quiet)

    processed = 0
    model = _get_model() if changed_ids else None
    for group in _chunked(changed_ids, batch_size):
        group_records = [by_id[rid] for rid in group]
        search_texts = [build_search_text(rec) for rec in group_records]
        embeddings = model.encode(  # type: ignore[union-attr]
            search_texts,
            normalize_embeddings=True,
            batch_size=min(batch_size, len(search_texts)),
            show_progress_bar=False,
        ).tolist()

        metadatas = [
            {
                "vuln_type": rec["vuln_type"],
                "protocol_name": rec["protocol_name"],
                "attack_date": rec["attack_date"],
            }
            for rec in group_records
        ]
        try:
            collection.upsert(
                ids=[rec["id"] for rec in group_records],
                embeddings=embeddings,
                documents=search_texts,
                metadatas=metadatas,
            )
        except NotFoundError:
            # Rare race with stale collection handle after delete/recreate.
            collection = _new_collection(client)
            collection.upsert(
                ids=[rec["id"] for rec in group_records],
                embeddings=embeddings,
                documents=search_texts,
                metadatas=metadatas,
            )
        processed += len(group_records)

    _save_manifest(new_hash)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    stats = {
        "total_records": len(records),
        "processed_records": processed,
        "removed_records": len(removed_ids),
        "rebuild": do_full_rebuild,
        "collection_count": collection.count(),
        "elapsed_ms": elapsed_ms,
        "data_dir": str(DATA_DIR.resolve()),
        "db_dir": str(CHROMA_DIR.resolve()),
        "manifest_path": str(MANIFEST_PATH.resolve()),
    }

    _log("RAG index build complete.", quiet)
    _log(
        (
            "total={total_records}, processed={processed_records}, removed={removed_records}, "
            "collection={collection_count}, elapsed_ms={elapsed_ms}"
        ).format(**stats),
        quiet,
    )
    return stats
