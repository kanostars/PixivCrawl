import threading
import logging
from typing import Dict, Callable, Optional


class ProgressTracker:
    """下载进度追踪"""

    def __init__(self, callback: Optional[Callable] = None) -> None:
        """
        初始化进度追踪器
        
        Args:
            callback: 进度更新回调函数
        """
        self.callback = callback
        self.tasks: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def init_task(self, task_id: str, total: int, metadata: Optional[dict] = None) -> None:
        """
        初始化任务
        
        Args:
            task_id: 任务 ID
            total: 总数量
            metadata: 任务元数据
        """
        with self.lock:
            self.tasks[task_id] = {
                'total': total,
                'completed': 0,
                'failed': 0,
                'metadata': metadata or {}
            }
            self.logger.info(f"初始化任务 {task_id}，总数: {total}")

    def update_progress(self, task_id: str, increment: int = 1, failed: bool = False) -> None:
        """
        更新进度
        
        Args:
            task_id: 任务 ID
            increment: 增量
            failed: 是否失败
        """
        with self.lock:
            if task_id not in self.tasks:
                self.logger.warning(f"任务 {task_id} 不存在")
                return

            if failed:
                self.tasks[task_id]['failed'] += increment
            else:
                self.tasks[task_id]['completed'] += increment

            # 调用回调函数
            if self.callback:
                self.callback(increment)

    def get_progress(self, task_id: str) -> dict:
        """
        获取任务进度
        
        Args:
            task_id: 任务 ID
            
        Returns:
            进度信息字典
        """
        with self.lock:
            if task_id not in self.tasks:
                return {}
            return self.tasks[task_id].copy()

    def mark_completed(self, task_id: str) -> None:
        """
        标记任务完成
        
        Args:
            task_id: 任务 ID
        """
        with self.lock:
            if task_id in self.tasks:
                self.logger.info(
                    f"任务 {task_id} 完成: "
                    f"成功 {self.tasks[task_id]['completed']}, "
                    f"失败 {self.tasks[task_id]['failed']}"
                )

    def clear_task(self, task_id: str) -> None:
        """
        清除任务记录
        
        Args:
            task_id: 任务 ID
        """
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                self.logger.info(f"任务 {task_id} 已清除")
