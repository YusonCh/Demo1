"""
命令行接口
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from rag_engine.crawler.fetchers import (
    GitHubSearcher, 
    CVEFetcher, 
    DeFiHackLabsFetcher,
    EthernautFetcher,
    RektNewsFetcher,
    AuditReportsFetcher,
)
from rag_engine.crawler.normalizer import DataNormalizer
from rag_engine.crawler.incremental_manager import IncrementalManager
from rag_engine.crawler.scheduler import CrawlerScheduler
from rag_engine import indexer


# 获取项目根目录
DATA_DIR = Path(__file__).parent.parent / "data"


def run_crawl(
    max_github: int = 30,
    max_cve: int = 20,
    max_defihack: int = 20,
    max_ethernaut: int = 20,
    max_rekt: int = 10,
    max_audit: int = 10,
    github_token: str = None,
    rebuild_index: bool = True,
) -> dict:
    """
    执行爬取任务
    
    Args:
        max_github: GitHub最大爬取数量
        max_cve: CVE最大爬取数量
        max_defihack: DeFiHackLabs最大爬取数量
        max_ethernaut: Ethernaut最大爬取数量
        max_rekt: Rekt News最大爬取数量
        max_audit: 审计报告最大爬取数量
        github_token: GitHub Token (可选)
        rebuild_index: 是否重建索引
        
    Returns:
        执行结果摘要
    """
    print("=" * 50)
    print("开始爬取漏洞数据...")
    print("=" * 50)

    # 初始化组件
    normalizer = DataNormalizer()
    inc_manager = IncrementalManager(DATA_DIR)
    existing_ids = inc_manager.get_existing_ids()

    print(f"现有记录数: {len(existing_ids)}")
    print(f"现有ID示例: {list(existing_ids)[:5]}")

    total_fetched = 0
    total_saved = 0
    sources = {}

    # 1. GitHub爬取
    print("\n[1/6] 正在从GitHub获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        github_crawled_ids = inc_manager.get_crawled_ids_for_source("github")
        print(f"  已爬取ID数: {len(github_crawled_ids)}")
        
        github_fetcher = GitHubSearcher(token=github_token)
        github_records = []
        github_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in github_fetcher.fetch(max_items=max_github):
            if record.id in github_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据，不发起API请求
            github_records.append(record)
            github_new_ids.append(record.id)
        
        total_fetched += len(github_records)
        sources["github"] = len(github_records)
        print(f"  获取到 {len(github_records)} 条新记录（跳过 {len(github_crawled_ids)} 条已爬取）")

        # 标准化并保存
        for normalized in normalizer.normalize_batch(github_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if github_new_ids:
            inc_manager.add_crawled_ids("github", github_new_ids)
        inc_manager.update_state("github", len(github_records))

    except Exception as e:
        print(f"  GitHub爬取失败: {e}")
        inc_manager.update_state("github", 0, str(e))

    # 2. CVE爬取
    print("\n[2/6] 正在从NVD CVE获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        cve_crawled_ids = inc_manager.get_crawled_ids_for_source("nvd_cve")
        print(f"  已爬取ID数: {len(cve_crawled_ids)}")
        
        cve_fetcher = CVEFetcher()
        cve_records = []
        cve_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in cve_fetcher.fetch(max_items=max_cve):
            if record.id in cve_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据
            cve_records.append(record)
            cve_new_ids.append(record.id)
        
        total_fetched += len(cve_records)
        sources["nvd_cve"] = len(cve_records)
        print(f"  获取到 {len(cve_records)} 条新记录（跳过 {len(cve_crawled_ids)} 条已爬取）")

        for normalized in normalizer.normalize_batch(cve_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if cve_new_ids:
            inc_manager.add_crawled_ids("nvd_cve", cve_new_ids)
        inc_manager.update_state("nvd_cve", len(cve_records))

    except Exception as e:
        print(f"  CVE爬取失败: {e}")
        inc_manager.update_state("nvd_cve", 0, str(e))

    # 3. DeFiHackLabs爬取
    print("\n[3/6] 正在从DeFiHackLabs获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        defihack_crawled_ids = inc_manager.get_crawled_ids_for_source("defihacklabs")
        print(f"  已爬取ID数: {len(defihack_crawled_ids)}")
        
        defihack_fetcher = DeFiHackLabsFetcher(token=github_token)
        defihack_records = []
        defihack_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in defihack_fetcher.fetch(max_items=max_defihack):
            if record.id in defihack_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据
            defihack_records.append(record)
            defihack_new_ids.append(record.id)
        
        total_fetched += len(defihack_records)
        sources["defihacklabs"] = len(defihack_records)
        print(f"  获取到 {len(defihack_records)} 条新记录（跳过 {len(defihack_crawled_ids)} 条已爬取）")

        for normalized in normalizer.normalize_batch(defihack_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if defihack_new_ids:
            inc_manager.add_crawled_ids("defihacklabs", defihack_new_ids)
        inc_manager.update_state("defihacklabs", len(defihack_records))

    except Exception as e:
        print(f"  DeFiHackLabs爬取失败: {e}")
        inc_manager.update_state("defihacklabs", 0, str(e))

    # 4. Ethernaut爬取
    print("\n[4/6] 正在从Ethernaut获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        ethernaut_crawled_ids = inc_manager.get_crawled_ids_for_source("ethernaut")
        print(f"  已爬取ID数: {len(ethernaut_crawled_ids)}")
        
        ethernaut_fetcher = EthernautFetcher()
        ethernaut_records = []
        ethernaut_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in ethernaut_fetcher.fetch(max_items=max_ethernaut):
            if record.id in ethernaut_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据
            ethernaut_records.append(record)
            ethernaut_new_ids.append(record.id)
        
        total_fetched += len(ethernaut_records)
        sources["ethernaut"] = len(ethernaut_records)
        print(f"  获取到 {len(ethernaut_records)} 条新记录（跳过 {len(ethernaut_crawled_ids)} 条已爬取）")

        for normalized in normalizer.normalize_batch(ethernaut_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if ethernaut_new_ids:
            inc_manager.add_crawled_ids("ethernaut", ethernaut_new_ids)
        inc_manager.update_state("ethernaut", len(ethernaut_records))

    except Exception as e:
        print(f"  Ethernaut爬取失败: {e}")
        inc_manager.update_state("ethernaut", 0, str(e))

    # 5. Rekt News爬取
    print("\n[5/6] 正在从Rekt News获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        rekt_crawled_ids = inc_manager.get_crawled_ids_for_source("rekt_news")
        print(f"  已爬取ID数: {len(rekt_crawled_ids)}")
        
        rekt_fetcher = RektNewsFetcher()
        rekt_records = []
        rekt_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in rekt_fetcher.fetch(max_items=max_rekt):
            if record.id in rekt_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据
            rekt_records.append(record)
            rekt_new_ids.append(record.id)
        
        total_fetched += len(rekt_records)
        sources["rekt_news"] = len(rekt_records)
        print(f"  获取到 {len(rekt_records)} 条新记录（跳过 {len(rekt_crawled_ids)} 条已爬取）")

        for normalized in normalizer.normalize_batch(rekt_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if rekt_new_ids:
            inc_manager.add_crawled_ids("rekt_news", rekt_new_ids)
        inc_manager.update_state("rekt_news", len(rekt_records))

    except Exception as e:
        print(f"  Rekt News爬取失败: {e}")
        inc_manager.update_state("rekt_news", 0, str(e))

    # 6. 审计报告爬取
    print("\n[6/6] 正在从审计报告获取数据...")
    try:
        # 获取已爬取的ID，避免重复请求API
        audit_crawled_ids = inc_manager.get_crawled_ids_for_source("audit_reports")
        print(f"  已爬取ID数: {len(audit_crawled_ids)}")
        
        audit_fetcher = AuditReportsFetcher()
        audit_records = []
        audit_new_ids = []
        
        # 只处理新数据，跳过已爬取的
        for record in audit_fetcher.fetch(max_items=max_audit):
            if record.id in audit_crawled_ids or record.id in existing_ids:
                continue  # 跳过已爬取的数据
            audit_records.append(record)
            audit_new_ids.append(record.id)
        
        total_fetched += len(audit_records)
        sources["audit_reports"] = len(audit_records)
        print(f"  获取到 {len(audit_records)} 条新记录（跳过 {len(audit_crawled_ids)} 条已爬取）")

        for normalized in normalizer.normalize_batch(audit_records, existing_ids):
            if normalized["id"] not in existing_ids:
                file_path = DATA_DIR / f"{normalized['id']}.json"
                file_path.write_text(
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                existing_ids.add(normalized["id"])
                total_saved += 1
                print(f"  保存: {normalized['id']}")

        # 更新已爬取ID列表
        if audit_new_ids:
            inc_manager.add_crawled_ids("audit_reports", audit_new_ids)
        inc_manager.update_state("audit_reports", len(audit_records))

    except Exception as e:
        print(f"  审计报告爬取失败: {e}")
        inc_manager.update_state("audit_reports", 0, str(e))

    # 重建索引
    index_stats = None
    if rebuild_index and total_saved > 0:
        print("\n重建向量索引...")
        try:
            index_stats = indexer.build_index()
            print(f"  索引完成: {index_stats}")
        except Exception as e:
            print(f"  索引构建失败: {e}")

    result = {
        "total_fetched": total_fetched,
        "total_saved": total_saved,
        "sources": sources,
        "existing_records": len(existing_ids),
        "index_stats": index_stats,
    }

    print("\n" + "=" * 50)
    print("爬取完成!")
    print(f"  获取总数: {total_fetched}")
    print(f"  新增保存: {total_saved}")
    print(f"  现有总数: {len(existing_ids)}")
    print("=" * 50)

    return result


def run_status() -> dict:
    """显示爬虫状态"""
    inc_manager = IncrementalManager(DATA_DIR)
    summary = inc_manager.get_summary()

    print("=" * 50)
    print("爬虫状态")
    print("=" * 50)
    print(f"现有记录总数: {summary['total_existing_records']}")
    print(f"最后更新时间: {summary['last_update']}")
    print("\n数据来源统计:")

    for source, state in summary["sources"].items():
        print(f"  [{source}]")
        print(f"    上次爬取: {state.get('last_crawl_time', 'N/A')}")
        print(f"    上次数量: {state.get('last_crawl_count', 0)}")
        print(f"    累计数量: {state.get('total_crawled', 0)}")
        print(f"    失败次数: {state.get('failed_attempts', 0)}")

    return summary


def run_schedule(
    cron_hour: int = 2,
    cron_minute: int = 0,
    run_now: bool = False,
    github_token: str = None,
) -> None:
    """启动定时调度"""
    scheduler = CrawlerScheduler(DATA_DIR, cron_hour, cron_minute)

    def scheduled_job():
        return run_crawl(github_token=github_token)

    scheduler.schedule(scheduled_job)
    scheduler.add_signal_handlers()
    scheduler.start(run_immediately=run_now)

    # 保持运行
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="RAG漏洞数据爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # fetch 命令
    fetch_parser = subparsers.add_parser("fetch", help="立即爬取数据")
    fetch_parser.add_argument(
        "--max-github", type=int, default=30, help="GitHub最大数量"
    )
    fetch_parser.add_argument(
        "--max-cve", type=int, default=20, help="CVE最大数量"
    )
    fetch_parser.add_argument(
        "--max-defihack", type=int, default=20, help="DeFiHackLabs最大数量"
    )
    fetch_parser.add_argument(
        "--max-ethernaut", type=int, default=20, help="Ethernaut最大数量"
    )
    fetch_parser.add_argument(
        "--max-rekt", type=int, default=10, help="Rekt News最大数量"
    )
    fetch_parser.add_argument(
        "--max-audit", type=int, default=10, help="审计报告最大数量"
    )
    fetch_parser.add_argument(
        "--token", type=str, default=None, help="GitHub Token"
    )
    fetch_parser.add_argument(
        "--no-index", action="store_true", help="不重建索引"
    )

    # status 命令
    subparsers.add_parser("status", help="查看爬虫状态")

    # schedule 命令
    schedule_parser = subparsers.add_parser("schedule", help="启动定时调度")
    schedule_parser.add_argument(
        "--hour", type=int, default=2, help="定时小时 (默认2)"
    )
    schedule_parser.add_argument(
        "--minute", type=int, default=0, help="定时分钟 (默认0)"
    )
    schedule_parser.add_argument(
        "--now", action="store_true", help="立即执行一次"
    )
    schedule_parser.add_argument(
        "--token", type=str, default=None, help="GitHub Token"
    )

    args = parser.parse_args()

    if args.command == "fetch":
        run_crawl(
            max_github=args.max_github,
            max_cve=args.max_cve,
            max_defihack=args.max_defihack,
            max_ethernaut=args.max_ethernaut,
            max_rekt=args.max_rekt,
            max_audit=args.max_audit,
            github_token=args.token,
            rebuild_index=not args.no_index,
        )
    elif args.command == "status":
        run_status()
    elif args.command == "schedule":
        run_schedule(
            cron_hour=args.hour,
            cron_minute=args.minute,
            run_now=args.now,
            github_token=args.token,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
