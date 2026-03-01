"""
测试去重机制 - 验证不会重复爬取相同数据
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from rag_engine.crawler.cli import run_crawl
from rag_engine.crawler.incremental_manager import IncrementalManager
from rag_engine import indexer


def test_deduplication():
    """测试去重机制"""
    print("=" * 60)
    print("测试去重机制")
    print("=" * 60)
    
    DATA_DIR = Path(__file__).parent.parent / "data"
    inc_manager = IncrementalManager(DATA_DIR)
    
    # 1. 获取初始状态
    print("\n[步骤1] 获取初始状态...")
    initial_ids = inc_manager.get_existing_ids()
    print(f"  现有记录数: {len(initial_ids)}")
    
    # 获取各数据源的已爬取ID
    sources = ["github", "nvd_cve", "defihacklabs", "ethernaut", "rekt_news", "audit_reports"]
    initial_crawled = {}
    for source in sources:
        crawled_ids = inc_manager.get_crawled_ids_for_source(source)
        initial_crawled[source] = len(crawled_ids)
        print(f"  {source}: 已爬取 {len(crawled_ids)} 个ID")
    
    # 2. 第一次爬取（小规模）
    print("\n[步骤2] 第一次爬取（小规模测试）...")
    result1 = run_crawl(
        max_github=5,
        max_cve=3,
        max_defihack=2,
        max_ethernaut=2,
        max_rekt=2,
        max_audit=2,
        github_token=None,
        rebuild_index=False,
    )
    
    print(f"\n第一次爬取结果:")
    print(f"  获取总数: {result1['total_fetched']}")
    print(f"  新增保存: {result1['total_saved']}")
    
    # 3. 检查状态更新
    print("\n[步骤3] 检查状态更新...")
    after_first_ids = inc_manager.get_existing_ids()
    print(f"  现有记录数: {len(after_first_ids)}")
    print(f"  新增记录数: {len(after_first_ids) - len(initial_ids)}")
    
    after_first_crawled = {}
    for source in sources:
        crawled_ids = inc_manager.get_crawled_ids_for_source(source)
        after_first_crawled[source] = len(crawled_ids)
        new_count = len(crawled_ids) - initial_crawled[source]
        print(f"  {source}: 已爬取 {len(crawled_ids)} 个ID (新增 {new_count})")
    
    # 4. 第二次爬取（相同参数）
    print("\n[步骤4] 第二次爬取（相同参数，应该跳过已爬取的数据）...")
    result2 = run_crawl(
        max_github=5,
        max_cve=3,
        max_defihack=2,
        max_ethernaut=2,
        max_rekt=2,
        max_audit=2,
        github_token=None,
        rebuild_index=False,
    )
    
    print(f"\n第二次爬取结果:")
    print(f"  获取总数: {result2['total_fetched']}")
    print(f"  新增保存: {result2['total_saved']}")
    
    # 5. 验证去重效果
    print("\n[步骤5] 验证去重效果...")
    after_second_ids = inc_manager.get_existing_ids()
    print(f"  现有记录数: {len(after_second_ids)}")
    print(f"  第二次新增记录数: {len(after_second_ids) - len(after_first_ids)}")
    
    # 验证结果
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)
    
    if result2['total_saved'] == 0:
        print("[OK] 第二次爬取没有保存新数据，去重机制工作正常！")
    else:
        print(f"[WARNING] 第二次爬取保存了 {result2['total_saved']} 条新数据")
        print("  这可能是因为:")
        print("  1. 数据源返回了新的数据")
        print("  2. ID生成策略发生了变化")
        print("  3. 去重机制需要进一步优化")
    
    if result2['total_fetched'] < result1['total_fetched']:
        print(f"[OK] 第二次获取的数据量 ({result2['total_fetched']}) 少于第一次 ({result1['total_fetched']})")
        print("  说明部分数据被跳过，去重机制有效")
    else:
        print(f"[INFO] 第二次获取的数据量 ({result2['total_fetched']}) 与第一次相同或更多")
        print("  这可能是因为数据源返回了新的数据，或者去重在API请求之后进行")
    
    # 6. 显示状态文件内容（部分）
    print("\n[步骤6] 查看状态文件（部分内容）...")
    state_file = DATA_DIR.parent / "crawler_state.json"
    if state_file.exists():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        for source, state in list(state_data.items())[:2]:  # 只显示前2个
            print(f"\n  [{source}]")
            print(f"    上次爬取时间: {state.get('last_crawl_time', 'N/A')}")
            print(f"    上次爬取数量: {state.get('last_crawl_count', 0)}")
            print(f"    累计爬取数量: {state.get('total_crawled', 0)}")
            crawled_ids = state.get('crawled_ids', [])
            print(f"    已爬取ID数: {len(crawled_ids)}")
            if crawled_ids:
                print(f"    ID示例: {crawled_ids[:3]}")
    else:
        print("  状态文件不存在")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    return {
        "first_crawl": result1,
        "second_crawl": result2,
        "deduplication_effective": result2['total_saved'] == 0,
    }


if __name__ == "__main__":
    test_deduplication()

