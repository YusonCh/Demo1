"""
数据验证模块 - 验证入库数据格式与indexer兼容
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .. import indexer


class DataValidator:
    """数据验证器"""

    REQUIRED_FIELDS = [
        "id",
        "vuln_type",
        "protocol_name",
        "attack_date",
        "description",
        "poc_template",
    ]

    OPTIONAL_FIELDS = [
        "slug",
        "tags",
        "attack_primitives",
        "aliases",
    ]

    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)

    def validate_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """
        验证单个JSON文件
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        if not file_path.exists():
            return False, [f"文件不存在: {file_path}"]
        
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return False, [f"JSON解析失败: {e}"]
        except Exception as e:
            return False, [f"读取文件失败: {e}"]
        
        # 检查必需字段
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"缺少必需字段: {field}")
            elif not data[field] or not str(data[field]).strip():
                errors.append(f"必需字段为空: {field}")
        
        # 验证字段类型和格式
        if "id" in data:
            if not isinstance(data["id"], str):
                errors.append(f"id必须是字符串类型")
            elif len(data["id"].strip()) == 0:
                errors.append(f"id不能为空")
        
        if "vuln_type" in data:
            if not isinstance(data["vuln_type"], str):
                errors.append(f"vuln_type必须是字符串类型")
        
        if "protocol_name" in data:
            if not isinstance(data["protocol_name"], str):
                errors.append(f"protocol_name必须是字符串类型")
        
        if "attack_date" in data:
            if not isinstance(data["attack_date"], str):
                errors.append(f"attack_date必须是字符串类型")
            # 验证日期格式 (YYYY-MM-DD)
            date_str = str(data["attack_date"]).strip()
            if len(date_str) < 10 or date_str[4] != "-" or date_str[7] != "-":
                errors.append(f"attack_date格式不正确，应为YYYY-MM-DD: {date_str}")
        
        if "description" in data:
            if not isinstance(data["description"], str):
                errors.append(f"description必须是字符串类型")
            elif len(data["description"].strip()) == 0:
                errors.append(f"description不能为空")
        
        if "poc_template" in data:
            if not isinstance(data["poc_template"], str):
                errors.append(f"poc_template必须是字符串类型")
            elif len(data["poc_template"].strip()) == 0:
                errors.append(f"poc_template不能为空")
        
        # 验证可选字段类型
        if "tags" in data and data["tags"] is not None:
            if not isinstance(data["tags"], list):
                errors.append(f"tags必须是列表类型")
            else:
                for tag in data["tags"]:
                    if not isinstance(tag, str):
                        errors.append(f"tags中的元素必须是字符串类型")
        
        if "attack_primitives" in data and data["attack_primitives"] is not None:
            if not isinstance(data["attack_primitives"], list):
                errors.append(f"attack_primitives必须是列表类型")
            else:
                for prim in data["attack_primitives"]:
                    if not isinstance(prim, str):
                        errors.append(f"attack_primitives中的元素必须是字符串类型")
        
        if "aliases" in data and data["aliases"] is not None:
            if not isinstance(data["aliases"], list):
                errors.append(f"aliases必须是列表类型")
            else:
                for alias in data["aliases"]:
                    if not isinstance(alias, str):
                        errors.append(f"aliases中的元素必须是字符串类型")
        
        # 使用indexer的验证函数进行最终验证
        try:
            validated = indexer._validate_record(data, file_path)
            # 如果indexer验证通过，说明格式正确
        except ValueError as e:
            errors.append(f"indexer验证失败: {e}")
        except Exception as e:
            errors.append(f"indexer验证异常: {e}")
        
        return len(errors) == 0, errors

    def validate_all(self) -> Dict[str, Any]:
        """
        验证所有JSON文件
        
        Returns:
            验证结果摘要
        """
        json_files = sorted(self.data_dir.glob("*.json"))
        
        if not json_files:
            return {
                "total_files": 0,
                "valid_files": 0,
                "invalid_files": 0,
                "errors": {},
                "summary": "没有找到JSON文件"
            }
        
        valid_count = 0
        invalid_count = 0
        errors = {}
        
        for json_file in json_files:
            is_valid, file_errors = self.validate_file(json_file)
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
                errors[json_file.name] = file_errors
        
        return {
            "total_files": len(json_files),
            "valid_files": valid_count,
            "invalid_files": invalid_count,
            "errors": errors,
            "summary": f"总计 {len(json_files)} 个文件，有效 {valid_count} 个，无效 {invalid_count} 个"
        }

    def validate_and_fix(self, file_path: Path) -> Tuple[bool, List[str]]:
        """
        验证并尝试修复文件
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            (是否修复成功, 修复信息列表)
        """
        is_valid, errors = self.validate_file(file_path)
        
        if is_valid:
            return True, ["文件格式正确，无需修复"]
        
        fixes = []
        
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            fixed = False
            
            # 尝试修复常见问题
            if "id" not in data or not data["id"]:
                data["id"] = file_path.stem
                fixes.append(f"添加缺失的id字段: {data['id']}")
                fixed = True
            
            if "slug" not in data:
                # 从protocol_name生成slug
                if "protocol_name" in data:
                    slug = data["protocol_name"].lower().replace(" ", "_")[:30]
                    data["slug"] = slug
                    fixes.append(f"添加缺失的slug字段: {slug}")
                    fixed = True
            
            # 确保列表字段存在
            for field in ["tags", "attack_primitives", "aliases"]:
                if field not in data or data[field] is None:
                    data[field] = []
                    fixes.append(f"添加缺失的{field}字段")
                    fixed = True
            
            # 确保字符串字段不为空
            for field in ["description", "poc_template"]:
                if field not in data or not data[field]:
                    data[field] = f"No {field} available"
                    fixes.append(f"填充空的{field}字段")
                    fixed = True
            
            if fixed:
                # 保存修复后的文件
                file_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                fixes.append("文件已保存修复")
            
            # 再次验证
            is_valid_after, errors_after = self.validate_file(file_path)
            if is_valid_after:
                fixes.append("修复后验证通过")
                return True, fixes
            else:
                fixes.append(f"修复后仍有错误: {errors_after}")
                return False, fixes
                
        except Exception as e:
            return False, [f"修复失败: {e}"]


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="验证RAG数据格式")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="数据目录路径（默认使用rag_engine/data）"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="尝试自动修复无效文件"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="验证单个文件"
    )
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir) if args.data_dir else None
    validator = DataValidator(data_dir)
    
    if args.file:
        # 验证单个文件
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = validator.data_dir / args.file
        
        print(f"验证文件: {file_path}")
        is_valid, errors = validator.validate_file(file_path)
        
        if is_valid:
            print("[OK] 文件格式正确")
        else:
            print("[ERROR] 文件格式错误:")
            for error in errors:
                print(f"  - {error}")
            
            if args.fix:
                print("\n尝试修复...")
                fixed, fixes = validator.validate_and_fix(file_path)
                for fix_msg in fixes:
                    print(f"  - {fix_msg}")
    else:
        # 验证所有文件
        print("=" * 50)
        print("验证所有数据文件...")
        print("=" * 50)
        
        result = validator.validate_all()
        
        print(f"\n{result['summary']}")
        print(f"有效文件: {result['valid_files']}")
        print(f"无效文件: {result['invalid_files']}")
        
        if result['errors']:
            print("\n错误详情:")
            for filename, errors in result['errors'].items():
                print(f"\n  [{filename}]")
                for error in errors:
                    print(f"    - {error}")
            
            if args.fix:
                print("\n尝试修复无效文件...")
                for filename in result['errors'].keys():
                    file_path = validator.data_dir / filename
                    print(f"\n修复: {filename}")
                    fixed, fixes = validator.validate_and_fix(file_path)
                    for fix_msg in fixes:
                        print(f"  - {fix_msg}")


if __name__ == "__main__":
    main()

