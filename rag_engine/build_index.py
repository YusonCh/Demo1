"""
一键建库脚本，在项目根目录的 Anaconda Prompt 中运行：
    python rag_engine/build_index.py
    python rag_engine/build_index.py --rebuild   ← 强制重建
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_engine.indexer import build_index

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建 AutoAudit RAG 知识库")
    parser.add_argument("--rebuild", action="store_true", help="强制清空并重建索引")
    args = parser.parse_args()

    build_index(force_rebuild=args.rebuild)