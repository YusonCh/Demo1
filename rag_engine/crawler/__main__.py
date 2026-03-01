"""
RAG爬虫模块主入口

支持以下运行方式:
    python -m rag_engine.crawler fetch      # 立即爬取
    python -m rag_engine.crawler status      # 查看状态
    python -m rag_engine.crawler schedule    # 启动定时调度
"""

from .cli import main

if __name__ == "__main__":
    main()
