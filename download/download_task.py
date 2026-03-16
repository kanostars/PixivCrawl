from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime


@dataclass
class DownloadTask:
    """下载任务数据类"""
    
    # 基本信息
    url: str
    save_path: str
    
    # 分片下载
    start: int = 0
    end: int = 0
    
    # 任务元数据
    metadata: Optional[Dict] = field(default_factory=dict)
    
    # 重试信息
    retries: int = 0
    max_retries: int = 5
    
    # 状态信息
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 错误信息
    error: Optional[str] = None
    
    def mark_started(self):
        """标记任务开始"""
        self.status = "downloading"
        self.started_at = datetime.now()
    
    def mark_completed(self):
        """标记任务完成"""
        self.status = "completed"
        self.completed_at = datetime.now()
    
    def mark_failed(self, error: str):
        """标记任务失败"""
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now()
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retries < self.max_retries
    
    def increment_retry(self):
        """增加重试次数"""
        self.retries += 1
