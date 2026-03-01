"""
定时调度器 - APScheduler定时任务
"""

import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(
        self,
        data_dir: Path,
        cron_hour: int = 2,
        cron_minute: int = 0,
    ):
        self.data_dir = Path(data_dir)
        self.scheduler = BackgroundScheduler()
        self.cron_hour = cron_hour
        self.cron_minute = cron_minute
        self._stop_event = False

    def schedule(self, func, job_id: str = "crawl") -> None:
        """添加定时任务"""
        trigger = CronTrigger(
            hour=self.cron_hour,
            minute=self.cron_minute,
        )
        self.scheduler.add_job(
            func,
            trigger,
            id=job_id,
            replace_existing=True,
        )

    def start(self, run_immediately: bool = False) -> None:
        """启动调度器"""
        if run_immediately:
            print(f"立即执行爬虫任务...")
        
        self.scheduler.start()
        print(
            f"调度器已启动 - 每天 {self.cron_hour:02d}:{self.cron_minute:02d} 执行"
        )

    def stop(self) -> None:
        """停止调度器"""
        self.scheduler.shutdown(wait=True)
        print("调度器已停止")

    def add_signal_handlers(self) -> None:
        """添加信号处理器"""

        def signal_handler(signum, frame):
            print("\n收到停止信号，正在关闭...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def run_once(self, func) -> None:
        """立即执行一次"""
        try:
            result = func()
            print(f"执行完成: {result}")
        except Exception as e:
            print(f"执行失败: {e}")

    def list_jobs(self) -> list[dict]:
        """列出所有任务"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
        return jobs
