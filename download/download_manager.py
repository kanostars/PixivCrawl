import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, List

from config.settings import MAX_WORKERS, MAX_RETRIES, BACKOFF_FACTOR
from download.progress_tracker import ProgressTracker
from download.download_task import DownloadTask
from exceptions import DownloadException


class DownloadManager:
    """下载管理器"""
    
    def __init__(self, api_client, progress_callback: Optional[Callable] = None,
                 task_complete_callback: Optional[Callable] = None) -> None:
        """
        初始化下载管理器
        
        Args:
            api_client: API 客户端实例
            progress_callback: 进度回调函数
            task_complete_callback: 任务完成回调函数 (metadata) -> None
        """
        self.api_client = api_client
        self.progress_tracker = ProgressTracker(progress_callback)
        self.task_complete_callback = task_complete_callback
        self.download_queue: List[DownloadTask] = []
        self.is_paused = threading.Event()
        self.is_stopped = threading.Event()
        self.file_locks = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
    
    def add_task(self, url: str, save_path: str, start: int = 0, 
                 end: int = 0, metadata: Optional[dict] = None) -> None:
        """
        添加下载任务到队列
        
        Args:
            url: 文件 URL
            save_path: 保存路径
            start: 起始字节位置
            end: 结束字节位置
            metadata: 任务元数据
        """
        task = DownloadTask(
            url=url,
            save_path=save_path,
            start=start,
            end=end,
            metadata=metadata or {},
            max_retries=MAX_RETRIES
        )
        with self.lock:
            self.download_queue.append(task)
    
    def start(self, max_workers: Optional[int] = None, task_id: str = "default", expected_total: Optional[int] = None) -> None:
        """
        开始下载
        
        Args:
            max_workers: 最大工作线程数
            task_id: 任务 ID
            expected_total: 预期的总任务数（如果提供，将用于统计；否则使用实际队列长度）
        """
        if not self.download_queue:
            self.logger.info("图片下载队列为空，跳过图片下载")
            return
        
        max_workers = max_workers or MAX_WORKERS
        actual_tasks = len(self.download_queue)
        
        # 使用预期任务数或实际任务数
        total_tasks = expected_total if expected_total is not None else actual_tasks
        
        # 初始化进度追踪
        self.progress_tracker.init_task(task_id, total_tasks)
        
        # 如果预期任务数与实际任务数不一致，记录警告
        if expected_total is not None and expected_total != actual_tasks:
            missing_tasks = expected_total - actual_tasks
            self.logger.warning(f"预期 {expected_total} 个任务，但实际只添加了 {actual_tasks} 个任务到队列")
            self.logger.warning(f"有 {missing_tasks} 个任务在添加阶段失败")
        
        self.logger.info(f"开始下载，共 {actual_tasks} 个任务......")
        self.logger.info(f"下载中......")

        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            
            for task in self.download_queue:
                if self.is_stopped.is_set():
                    break
                future = executor.submit(self._download_task, task, task_id)
                futures.append(future)
            
            # 等待所有任务完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"下载任务失败: {e}")
        
        # 标记任务完成
        self.progress_tracker.mark_completed(task_id)
        
        # 清空队列
        with self.lock:
            self.download_queue.clear()
    
    def _download_task(self, task: DownloadTask, task_id: str) -> None:
        """
        执行单个下载任务
        
        Args:
            task: 下载任务
            task_id: 任务 ID
        """
        while self.is_paused.is_set():
            time.sleep(1)

        if self.is_stopped.is_set():
            task.mark_failed("下载被停止")
            return
        
        # 确保目录存在
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        
        # 获取文件锁
        file_lock = self._get_file_lock(task.save_path)
        
        try:
            # 标记任务开始
            task.mark_started()
            
            with file_lock:
                # 执行下载
                self._download_with_retry(task)
            
            # 标记任务完成
            task.mark_completed()
            
            # 更新进度
            self.progress_tracker.update_progress(task_id, 1, failed=False)
            self.logger.debug(f"下载成功: {task.save_path}")
            
            # 通知任务完成（用于历史记录）
            if self.task_complete_callback and task.metadata:
                self.task_complete_callback(task.metadata)
            
        except Exception as e:
            # 标记任务失败
            task.mark_failed(str(e))
            
            self.progress_tracker.update_progress(task_id, 1, failed=True)
            self.logger.error(f"下载失败: {task.save_path}, 错误: {e}")
            raise DownloadException(f"下载失败: {str(e)}")
    
    def _download_with_retry(self, task: DownloadTask) -> None:
        """
        带重试的下载
        
        Args:
            task: 下载任务
        """
        last_exception = None
        
        while task.can_retry():
            try:
                self.api_client.download_file(
                    task.url, 
                    task.save_path, 
                    task.start, 
                    task.end
                )
                return  # 下载成功
                
            except Exception as e:
                last_exception = e
                task.increment_retry()
                
                if task.can_retry():
                    wait_time = BACKOFF_FACTOR * (2 ** (task.retries - 1))
                    self.logger.warning(
                        f"下载失败，{wait_time}秒后重试 "
                        f"({task.retries}/{task.max_retries}): {e}"
                    )
                    time.sleep(wait_time)
        
        # 所有重试都失败
        raise DownloadException(f"下载失败，已重试 {task.max_retries} 次: {last_exception}")
    
    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """
        获取文件锁
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件锁对象
        """
        with self.lock:
            if file_path not in self.file_locks:
                self.file_locks[file_path] = threading.Lock()
            return self.file_locks[file_path]
    
    def pause(self):
        self.is_paused.set()
        self.logger.info("下载已暂停")
    
    def resume(self):
        self.is_paused.clear()
        self.logger.info("下载已恢复")
    
    def stop(self):
        self.is_stopped.set()
        self.logger.info("下载已停止")
    
    def clear_queue(self):
        """清空下载队列"""
        with self.lock:
            self.download_queue.clear()
        self.logger.info("下载队列已清空")
    
    def get_queue_status(self) -> dict:
        """
        获取队列状态统计
        
        Returns:
            包含各状态任务数量的字典
        """
        with self.lock:
            status_count = {
                "pending": 0,
                "downloading": 0,
                "completed": 0,
                "failed": 0,
                "total": len(self.download_queue)
            }
            
            for task in self.download_queue:
                if task.status in status_count:
                    status_count[task.status] += 1
            
            return status_count
    
    def get_failed_tasks(self) -> List[DownloadTask]:
        """
        获取所有失败的任务
        
        Returns:
            失败任务列表
        """
        with self.lock:
            return [task for task in self.download_queue if task.status == "failed"]
    
    def retry_failed_tasks(self) -> None:
        """重试所有失败的任务"""
        failed_tasks = self.get_failed_tasks()
        
        if not failed_tasks:
            self.logger.info("没有失败的任务需要重试")
            return
        
        self.logger.info(f"准备重试 {len(failed_tasks)} 个失败的任务")
        
        for task in failed_tasks:
            # 重置任务状态
            task.status = "pending"
            task.retries = 0
            task.error = None
            task.started_at = None
            task.completed_at = None
