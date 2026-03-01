"""
数据标准化模块 - 将不同来源数据转换为indexer兼容格式
"""

import re
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Generator, Optional

from .fetchers import VulnerabilityRecord


class DataNormalizer:
    """数据标准化器"""

    # 漏洞类型映射表
    VULN_TYPE_MAP = {
        "reentrancy": "SWC-107-Reentrancy",
        "re-entrancy": "SWC-107-Reentrancy",
        "integer overflow": "SWC-101-Integer-Overflow",
        "underflow": "SWC-101-Integer-Underflow",
        "access control": "SWC-103-Access-Control",
        "front running": "Front-Running",
        "sandwich attack": "Sandwich-Attack",
        "flash loan": "Flash-Loan-Attack",
        "flashloan": "Flash-Loan-Attack",
        "oracle manipulation": "Oracle-Manipulation",
        "price manipulation": "Oracle-Manipulation",
        "rug pull": "Rug-Pull",
        "exit scam": "Rug-Pull",
        "bridge exploit": "Bridge-Exploit",
        "delegatecall": "Delegatecall-Vulnerability",
        "selfdestruct": "Self-Destruct",
        "tx.origin": "Tx-Origin-Vulnerability",
        "unverified external call": "Unverified-Call",
        "erc20": "ERC20-Vulnerability",
        "nft": "NFT-Vulnerability",
        "permit": "Permit-Vulnerability",
    }

    def __init__(self):
        self.seen_ids = set()

    def normalize(
        self, 
        record: VulnerabilityRecord, 
        existing_ids: Optional[set[str]] = None
    ) -> Optional[dict[str, Any]]:
        """
        标准化单条记录
        
        Args:
            record: 原始记录
            existing_ids: 已存在的ID集合（用于去重）
            
        Returns:
            标准化后的字典，或None（如果无效）
        """
        if existing_ids is None:
            existing_ids = set()

        # 生成唯一ID
        record_id = self._generate_unique_id(record, existing_ids)
        if not record_id:
            return None

        # 生成slug
        slug = self._generate_slug(record, record_id)

        # 标准化漏洞类型
        vuln_type = self._normalize_vuln_type(record.vuln_type)

        # 标准化日期
        attack_date = self._normalize_date(record.attack_date)

        # 清理描述
        description = self._clean_text(record.description, max_len=800)

        # 标准化标签
        tags = self._normalize_tags(record.tags, record.source)

        # 标准化攻击原语
        attack_primitives = self._normalize_list(record.attack_primitives)

        # 标准化别名
        aliases = self._normalize_list(record.aliases)

        # 生成或清理PoC模板
        poc_template = self._normalize_poc(record.poc_template, vuln_type, record.protocol_name)

        return {
            "id": record_id,
            "slug": slug,
            "vuln_type": vuln_type,
            "protocol_name": self._clean_protocol_name(record.protocol_name),
            "attack_date": attack_date,
            "tags": tags,
            "attack_primitives": attack_primitives,
            "aliases": aliases,
            "description": description,
            "poc_template": poc_template,
        }

    def normalize_batch(
        self, 
        records: list[VulnerabilityRecord], 
        existing_ids: Optional[set[str]] = None
    ) -> Generator[dict[str, Any], None, None]:
        """批量标准化"""
        if existing_ids is None:
            existing_ids = set()
        seen = set(existing_ids)

        for record in records:
            normalized = self.normalize(record, seen)
            if normalized:
                seen.add(normalized["id"])
                yield normalized

    def _generate_unique_id(
        self, 
        record: VulnerabilityRecord, 
        existing_ids: set[str]
    ) -> Optional[str]:
        """生成唯一ID"""
        # 优先使用已有ID
        base_id = record.id or ""

        # 清理ID
        base_id = re.sub(r"[^a-zA-Z0-9_-]", "_", base_id)
        base_id = base_id[:30]

        if not base_id:
            # 生成随机ID
            base_id = f"auto_{uuid.uuid4().hex[:8]}"

        # 确保唯一
        if base_id not in existing_ids:
            return base_id

        # 尝试添加后缀
        for i in range(1, 100):
            new_id = f"{base_id}_{i}"
            if new_id not in existing_ids:
                return new_id

        return None

    def _generate_slug(self, record: VulnerabilityRecord, record_id: str) -> str:
        """生成slug"""
        # 使用protocol_name + vuln_type组合
        protocol = re.sub(r"[^a-z0-9]", "", record.protocol_name.lower())
        vuln = re.sub(r"[^a-z0-9]", "", record.vuln_type.lower())

        if protocol and vuln:
            slug = f"{protocol[:15]}_{vuln[:15]}"
        elif protocol:
            slug = protocol[:30]
        elif vuln:
            slug = vuln[:30]
        else:
            slug = record_id

        return slug.lower()

    def _normalize_vuln_type(self, vuln_type: str) -> str:
        """标准化漏洞类型"""
        if not vuln_type:
            return "Smart-Contract-Vulnerability"

        vuln_lower = vuln_type.lower().strip()

        # 检查映射表
        for key, mapped in self.VULN_TYPE_MAP.items():
            if key in vuln_lower:
                return mapped

        # 已经是标准格式
        if vuln_lower.startswith(("swc-", "cwe-")):
            return vuln_type.upper()

        # 默认格式
        return vuln_type[:50] or "Smart-Contract-Vulnerability"

    def _normalize_date(self, date_str: str) -> str:
        """标准化日期格式"""
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")

        # 尝试多种格式
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y%m%d",
        ]

        date_str = date_str.strip()[:20]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # 尝试提取日期部分
        match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", date_str)
        if match:
            return match.group(1).replace("/", "-")

        return datetime.now().strftime("%Y-%m-%d")

    def _clean_text(self, text: str, max_len: int = 800) -> str:
        """清理文本"""
        if not text:
            return "No description available"

        # 移除多余空白
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # 移除特殊字符
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)

        # 截断
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."

        return text

    def _normalize_tags(self, tags: list[str], source: str) -> list[str]:
        """标准化标签"""
        result = []

        for tag in tags:
            tag = re.sub(r"[^a-z0-9\-_]", "", tag.lower().strip())
            if tag and len(tag) < 30:
                result.append(tag)

        # 添加来源标签
        if source and source not in result:
            result.insert(0, source)

        return result[:10]  # 最多10个标签

    def _normalize_list(self, items: list[str]) -> list[str]:
        """标准化列表"""
        result = []
        for item in items:
            item = re.sub(r"[^a-z0-9\-_]", "", item.lower().strip())
            if item and len(item) < 50:
                result.append(item)
        return result[:10]

    def _normalize_poc(
        self, 
        poc: str, 
        vuln_type: str, 
        protocol_name: str
    ) -> str:
        """标准化PoC模板"""
        if not poc:
            return self._default_poc(vuln_type, protocol_name)

        # 基本清理
        poc = poc.strip()

        # 确保有 SPDX 许可证
        if "SPDX-License-Identifier" not in poc:
            poc = "// SPDX-License-Identifier: MIT\n" + poc

        return poc[:5000]  # 限制长度

    def _default_poc(self, vuln_type: str, protocol_name: str) -> str:
        """生成默认PoC模板"""
        return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import "forge-std/Test.sol";

// protocol: {protocol_name}
// vuln_type: {vuln_type}

contract {vuln_type[:20] if vuln_type else "Exploit"}Test is Test {{
    function testExploit() public {{
        // TODO: Implement PoC based on {protocol_name} {vuln_type} vulnerability
        assertTrue(true);
    }}
}}"""

    def _clean_protocol_name(self, name: str) -> str:
        """清理协议名称"""
        if not name:
            return "Unknown"
        
        # 移除特殊字符
        name = re.sub(r"[^a-zA-Z0-9\s\-_]", "", name)
        name = name.strip()[:50]
        
        return name or "Unknown"
