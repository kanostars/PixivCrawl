import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Set, Optional

from exceptions import FileOperationException
from config.settings import TYPE_ARTWORK, TYPE_COLLECTION, TYPE_NOVEL

class HistoryManager:
    """下载历史记录管理器"""
    
    def __init__(self, history_file: str = "download_history.json"):
        """
        初始化历史管理器
        
        Args:
            history_file: 历史记录文件路径（默认值，画师模式下会被覆盖）
        """
        self.history_file = history_file
        self.artist_id: Optional[str] = None
        self.artist_name: Optional[str] = None
        self.downloaded_artworks: Set[str] = set()
        self.downloaded_collections: Set[str] = set()
        self.downloaded_novels: Set[str] = set()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self.is_loaded = False

    def set_history_file(self, history_file: str, artist_id: str = None, artist_name: str = None):
        """
        设置历史记录文件路径并加载
        
        Args:
            history_file: 历史记录文件路径
            artist_id: 画师ID
            artist_name: 画师名称
        """
        self.history_file = history_file
        self.artist_id = artist_id
        self.artist_name = artist_name
        self.load()
    
    def reset(self):
        """重置历史记录管理器（用于新的下载任务）"""
        with self.lock:
            self.artist_id = None
            self.artist_name = None
            self.downloaded_artworks.clear()
            self.downloaded_collections.clear()
            self.downloaded_novels.clear()
            self.is_loaded = False
    
    def load(self):
        """从文件加载历史记录"""
        try:
            if Path(self.history_file).exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.artist_id = data.get('artist_id', self.artist_id)
                    self.artist_name = data.get('artist_name', self.artist_name)
                    self.downloaded_artworks = set(data.get('downloaded_artworks', []))
                    self.downloaded_collections = set(data.get('downloaded_collections', []))
                    self.downloaded_novels = set(data.get('downloaded_novels', []))
                total = len(self.downloaded_artworks) + len(self.downloaded_collections) + len(self.downloaded_novels)
                self.logger.info(f"加载历史记录: {total} 条 - {self.history_file}")
            else:
                self.logger.debug(f"历史记录文件不存在，创建新记录 - {self.history_file}")
                self.downloaded_artworks = set()
                self.downloaded_collections = set()
                self.downloaded_novels = set()
            self.is_loaded = True
        except Exception as e:
            self.logger.error(f"加载历史记录失败: {e}")
            self.downloaded_artworks = set()
            self.downloaded_collections = set()
            self.downloaded_novels = set()
            self.is_loaded = True
    
    def save(self):
        """保存历史记录到文件"""
        try:
            with self.lock:
                # 确保目录存在
                os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
                
                total_count = len(self.downloaded_artworks) + len(self.downloaded_collections) + len(self.downloaded_novels)
                
                data = {
                    'artist_id': self.artist_id or '',
                    'artist_name': self.artist_name or '',
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'downloaded_artworks': sorted(list(self.downloaded_artworks)),
                    'downloaded_collections': sorted(list(self.downloaded_collections)),
                    'downloaded_novels': sorted(list(self.downloaded_novels)),
                    'total_count': total_count
                }
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.logger.info(f"保存历史记录: {total_count} 条 - {self.history_file}")
        except Exception as e:
            raise FileOperationException(f"保存历史记录失败: {e}")
    
    def add(self, resource_id: str, resource_type: str = TYPE_ARTWORK):
        """
        添加下载记录
        
        Args:
            resource_id: 资源 ID
            resource_type: 资源类型 ('artwork', 'collection', 'novel')
        """
        with self.lock:
            if resource_type == TYPE_ARTWORK:
                self.downloaded_artworks.add(str(resource_id))
            elif resource_type == TYPE_COLLECTION:
                self.downloaded_collections.add(str(resource_id))
            elif resource_type == TYPE_NOVEL:
                self.downloaded_novels.add(str(resource_id))
    
    def is_downloaded(self, resource_id: str, resource_type: str = TYPE_ARTWORK) -> bool:
        """
        检查资源是否已下载
        
        Args:
            resource_id: 资源 ID
            resource_type: 资源类型 ('artwork', 'collection', 'novel')
            
        Returns:
            是否已下载
        """
        with self.lock:
            resource_id = str(resource_id)
            if resource_type == TYPE_ARTWORK:
                return resource_id in self.downloaded_artworks
            elif resource_type == TYPE_COLLECTION:
                return resource_id in self.downloaded_collections
            elif resource_type == TYPE_NOVEL:
                return resource_id in self.downloaded_novels
            return False
    
    def remove(self, resource_id: str, resource_type: str = TYPE_ARTWORK):
        """
        移除下载记录
        
        Args:
            resource_id: 资源 ID
            resource_type: 资源类型 ('artwork', 'collection', 'novel')
        """
        with self.lock:
            resource_id = str(resource_id)
            if resource_type == TYPE_ARTWORK:
                self.downloaded_artworks.discard(resource_id)
            elif resource_type == TYPE_COLLECTION:
                self.downloaded_collections.discard(resource_id)
            elif resource_type == TYPE_NOVEL:
                self.downloaded_novels.discard(resource_id)
    
    def clear(self):
        """清空所有历史记录"""
        with self.lock:
            self.downloaded_artworks.clear()
            self.downloaded_collections.clear()
            self.downloaded_novels.clear()
        self.save()
        self.logger.info("历史记录已清空")
    
    def get_count(self) -> int:
        with self.lock:
            return len(self.downloaded_artworks) + len(self.downloaded_collections) + len(self.downloaded_novels)
