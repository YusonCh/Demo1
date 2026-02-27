"""
Build script for AutoAudit RAG index.

Usage:
    python rag_engine/build_index.py
    python rag_engine/build_index.py --rebuild
    python rag_engine/build_index.py --batch-size 32 --quiet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_engine.indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AutoAudit RAG index.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force delete and rebuild the whole index.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Embedding batch size used during index build.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only final summary.",
    )
    args = parser.parse_args()

    stats = build_index(
        force_rebuild=args.rebuild,
        batch_size=args.batch_size,
        quiet=args.quiet,
    )
    if args.quiet:
        print(
            (
                "RAG index ready: total={total_records}, processed={processed_records}, "
                "removed={removed_records}, collection={collection_count}, elapsed_ms={elapsed_ms}"
            ).format(**stats)
        )


if __name__ == "__main__":
    main()
