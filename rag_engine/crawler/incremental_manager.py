"""
增量管理器 - 避免重复爬取，管理爬取状态
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class CrawlState:
    """爬取状态"""
    source: str  # 数据来源
    last_crawl_time: str = ""  # 上次爬取时间 ISO格式
    last_crawl_count: int = 0  # 上次爬取数量
    total_crawled: int = 0  # 累计爬取数量
    failed_attempts: int = 0  # 失败次数
    last_error: str = ""  # 上次错误信息
    crawled_ids: list[str] = field(default_factory=list)  # 已爬取的ID列表（用于避免重复请求API）
    last_crawl_position: dict[str, Any] = field(default_factory=dict)  # 上次爬取位置（用于增量爬取）


@dataclass
class IncrementalManager:
    """增量管理器"""
    data_dir: Path
    state_file: Path = field(init=False)

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.state_file = self.data_dir.parent / "crawler_state.json"

    def load_state(self) -> dict[str, CrawlState]:
        """加载爬取状态"""
        if not self.state_file.exists():
            return {}

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return {
                source: CrawlState(**state)
                for source, state in data.items()
            }
        except Exception:
            return {}

    def save_state(self, states: dict[str, CrawlState]) -> None:
        """保存爬取状态"""
        data = {
            source: asdict(state)
            for source, state in states.items()
        }
        self.state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def update_state(
        self,
        source: str,
        count: int,
        error: str = "",
    ) -> None:
        """更新爬取状态"""
        states = self.load_state()

        if source not in states:
            states[source] = CrawlState(source=source)

        state = states[source]
        state.last_crawl_time = datetime.now().isoformat()
        state.last_crawl_count = count
        state.total_crawled += count
        state.last_error = error
        state.failed_attempts = 0 if not error else state.failed_attempts + 1

        self.save_state(states)

    def get_existing_ids(self) -> set[str]:
        """获取现有数据的ID集合"""
        existing_ids = set()

        for json_file in self.data_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if "id" in data:
                    existing_ids.add(data["id"])
            except Exception:
                continue

        return existing_ids

    def get_crawled_ids_for_source(self, source: str) -> set[str]:
        """获取特定数据源已爬取的ID集合"""
        state = self.get_source_state(source)
        if state and state.crawled_ids:
            return set(state.crawled_ids)
        return set()

    def add_crawled_ids(self, source: str, ids: list[str]) -> None:
        """添加已爬取的ID"""
        states = self.load_state()
        if source not in states:
            states[source] = CrawlState(source=source)
        
        state = states[source]
        existing_set = set(state.crawled_ids)
        for id_val in ids:
            if id_val not in existing_set:
                state.crawled_ids.append(id_val)
        
        # 限制列表大小，只保留最近1000个
        if len(state.crawled_ids) > 1000:
            state.crawled_ids = state.crawled_ids[-1000:]
        
        self.save_state(states)

    def get_last_crawl_position(self, source: str) -> dict[str, Any]:
        """获取上次爬取位置"""
        state = self.get_source_state(source)
        if state and state.last_crawl_position:
            return state.last_crawl_position
        return {}

    def set_last_crawl_position(self, source: str, position: dict[str, Any]) -> None:
        """设置上次爬取位置"""
        states = self.load_state()
        if source not in states:
            states[source] = CrawlState(source=source)
        
        states[source].last_crawl_position = position
        self.save_state(states)

    def get_source_state(self, source: str) -> Optional[CrawlState]:
        """获取特定来源的状态"""
        states = self.load_state()
        return states.get(source)

    def get_last_crawl_time(self, source: str) -> Optional[datetime]:
        """获取上次爬取时间"""
        state = self.get_source_state(source)
        if state and state.last_crawl_time:
            try:
                return datetime.fromisoformat(state.last_crawl_time)
            except ValueError:
                pass
        return None

    def should_retry(self, source: str, max_retries: int = 3) -> bool:
        """检查是否应该重试"""
        state = self.get_source_state(source)
        if not state:
            return True
        return state.failed_attempts < max_retries

    def get_summary(self) -> dict[str, Any]:
        """获取爬取摘要"""
        states = self.load_state()
        existing_ids = self.get_existing_ids()

        return {
            "total_existing_records": len(existing_ids),
            "sources": {
                source: asdict(state)
                for source, state in states.items()
            },
            "last_update": datetime.now().isoformat(),
        }
