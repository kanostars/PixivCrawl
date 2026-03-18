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
        标记任务完成并输出统计信息
        
        Args:
            task_id: 任务 ID
        """
        with self.lock:
            if task_id in self.tasks:
                task_info = self.tasks[task_id]
                total = task_info['total']
                completed = task_info['completed']
                failed = task_info['failed']
                
                # 计算未下载的任务数（预期但未完成的）
                not_downloaded = total - completed - failed
                
                self.logger.info("=" * 20)
                self.logger.info(f"  预期下载: {total} 个文件")
                self.logger.info(f"  成功下载: {completed} 个文件")
                self.logger.info(f"  下载失败: {failed} 个文件")
                
                if not_downloaded > 0:
                    self.logger.warning(f"  未下载: {not_downloaded} 个文件 (可能在添加任务时失败)")

                self.logger.info("=" * 20)

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
