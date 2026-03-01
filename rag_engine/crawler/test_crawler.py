"""
测试爬虫功能和数据验证
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from rag_engine.crawler.cli import run_crawl
from rag_engine.crawler.validator import DataValidator
from rag_engine import indexer


def test_crawler_small():
    """测试爬虫功能（小规模）"""
    print("=" * 60)
    print("测试爬虫功能（小规模）")
    print("=" * 60)
    
    try:
        result = run_crawl(
            max_github=5,
            max_cve=3,
            max_defihack=3,
            max_ethernaut=3,
            max_rekt=2,
            max_audit=2,
            github_token=None,
            rebuild_index=False,  # 先不重建索引，等验证完数据再重建
        )
        
        print("\n爬取结果:")
        print(f"  获取总数: {result['total_fetched']}")
        print(f"  新增保存: {result['total_saved']}")
        print(f"  现有总数: {result['existing_records']}")
        print(f"  数据来源: {result['sources']}")
        
        return result
        
    except Exception as e:
        print(f"爬取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_data_validation():
    """测试数据验证"""
    print("\n" + "=" * 60)
    print("测试数据验证")
    print("=" * 60)
    
    validator = DataValidator()
    result = validator.validate_all()
    
    print(f"\n验证结果:")
    print(f"  总文件数: {result['total_files']}")
    print(f"  有效文件: {result['valid_files']}")
    print(f"  无效文件: {result['invalid_files']}")
    
    if result['errors']:
        print(f"\n发现 {len(result['errors'])} 个无效文件:")
        for filename, errors in list(result['errors'].items())[:5]:  # 只显示前5个
            print(f"\n  [{filename}]")
            for error in errors[:3]:  # 每个文件只显示前3个错误
                print(f"    - {error}")
        if len(result['errors']) > 5:
            print(f"\n  ... 还有 {len(result['errors']) - 5} 个文件有错误")
    else:
        print("\n[OK] 所有文件格式正确！")
    
    return result


def test_indexer_compatibility():
    """测试与indexer的兼容性"""
    print("\n" + "=" * 60)
    print("测试与indexer的兼容性")
    print("=" * 60)
    
    try:
        # 尝试加载所有记录
        records = indexer.load_all_records()
        print(f"[OK] 成功加载 {len(records)} 条记录")
        
        # 尝试构建搜索文本
        if records:
            sample = records[0]
            search_text = indexer.build_search_text(sample)
            print(f"[OK] 搜索文本构建成功（示例长度: {len(search_text)} 字符）")
            print(f"  示例: {search_text[:100]}...")
        
        # 尝试构建索引（不实际构建，只检查数据格式）
        print("\n检查数据格式...")
        invalid_count = 0
        for record in records[:10]:  # 只检查前10条
            try:
                indexer._validate_record(record, Path("test.json"))
            except Exception as e:
                print(f"  [ERROR] 记录 {record.get('id', 'unknown')} 格式错误: {e}")
                invalid_count += 1
        
        if invalid_count == 0:
            print("[OK] 所有检查的记录格式正确")
        else:
            print(f"[ERROR] 发现 {invalid_count} 条格式错误的记录")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] indexer兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sample_data_format():
    """测试示例数据格式"""
    print("\n" + "=" * 60)
    print("测试示例数据格式")
    print("=" * 60)
    
    data_dir = Path(__file__).parent.parent / "data"
    json_files = sorted(data_dir.glob("*.json"))[:5]  # 检查前5个文件
    
    if not json_files:
        print("没有找到数据文件")
        return
    
    print(f"检查 {len(json_files)} 个示例文件...")
    
    validator = DataValidator()
    for json_file in json_files:
        is_valid, errors = validator.validate_file(json_file)
        status = "[OK]" if is_valid else "[ERROR]"
        print(f"  {status} {json_file.name}")
        if errors:
            for error in errors[:2]:
                print(f"      - {error}")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("RAG爬虫功能测试")
    print("=" * 60)
    
    # 1. 测试示例数据格式
    test_sample_data_format()
    
    # 2. 测试数据验证
    validation_result = test_data_validation()
    
    # 3. 测试indexer兼容性
    indexer_ok = test_indexer_compatibility()
    
    # 4. 如果数据验证通过，测试小规模爬取
    if validation_result['invalid_files'] == 0 and indexer_ok:
        print("\n" + "=" * 60)
        print("数据验证通过，开始测试爬虫功能...")
        print("=" * 60)
        crawl_result = test_crawler_small()
        
        if crawl_result and crawl_result['total_saved'] > 0:
            # 验证新爬取的数据
            print("\n验证新爬取的数据...")
            new_validation = test_data_validation()
            
            if new_validation['invalid_files'] == 0:
                print("\n" + "=" * 60)
                print("[OK] 所有测试通过！")
                print("=" * 60)
                print("\n建议运行以下命令重建索引:")
                print("  python -m rag_engine.build_index")
            else:
                print("\n[ERROR] 新爬取的数据中有格式错误")
        else:
            print("\n注意: 没有新数据被爬取（可能已存在）")
    else:
        print("\n[ERROR] 数据验证未通过，请先修复现有数据")
        print("  可以运行: python -m rag_engine.crawler.validator --fix")


if __name__ == "__main__":
    main()

