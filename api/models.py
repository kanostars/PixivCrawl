from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ArtworkPage:
    """插画页面信息"""
    urls: Dict[str, str]  # {'thumb': '...', 'small': '...', 'regular': '...', 'original': '...'}
    width: int = 0
    height: int = 0


@dataclass
class ArtworkInfo:
    """插画信息"""
    id: str
    title: str
    user_name: str
    user_id: str
    page_count: int
    tags: List[str] = field(default_factory=list)
    create_date: Optional[str] = None
    description: str = ""
    width: int = 0
    height: int = 0
    is_bookmarked: bool = False
    bookmark_count: int = 0
    like_count: int = 0
    view_count: int = 0
    illust_type: int = 0  # 0=插画, 1=漫画, 2=动图
    
    def is_ugoira(self) -> bool:
        """判断是否为动图"""
        return self.illust_type == 2
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'ArtworkInfo':
        """从 API 响应创建实例"""
        body = data.get('body', {})
        user_info = body.get('userInfo', {}) or body
        
        return cls(
            id=str(body.get('id', '')),
            title=body.get('title', ''),
            user_name=user_info.get('userName', body.get('userName', '')),
            user_id=str(user_info.get('userId', body.get('userId', ''))),
            page_count=body.get('pageCount', 1),
            tags=[tag.get('tag', '') for tag in body.get('tags', {}).get('tags', [])],
            create_date=body.get('createDate'),
            description=body.get('description', ''),
            width=body.get('width', 0),
            height=body.get('height', 0),
            is_bookmarked=body.get('isBookmarked', False),
            bookmark_count=body.get('bookmarkCount', 0),
            like_count=body.get('likeCount', 0),
            view_count=body.get('viewCount', 0),
            illust_type=body.get('illustType', 0)
        )


@dataclass
class UgoiraMeta:
    """动图元数据"""
    original_src: str
    frames: List[Dict[str, Any]]
    mime_type: str = "image/jpeg"
    
    def get_delays(self) -> List[int]:
        """获取帧延迟列表"""
        return [frame.get('delay', 100) for frame in self.frames]
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> Optional['UgoiraMeta']:
        """从 API 响应创建实例"""
        if not data or 'body' not in data:
            return None
        
        body = data['body']
        return cls(
            original_src=body.get('originalSrc', ''),
            frames=body.get('frames', []),
            mime_type=body.get('mime_type', 'image/jpeg')
        )


@dataclass
class NovelInfo:
    """小说信息"""
    id: str
    title: str
    content: str
    user_name: str
    user_id: str
    tags: List[str] = field(default_factory=list)
    create_date: Optional[str] = None
    description: str = ""
    text_count: int = 0
    is_bookmarked: bool = False
    bookmark_count: int = 0
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'NovelInfo':
        """从 API 响应创建实例"""
        body = data.get('body', {})
        
        return cls(
            id=str(body.get('id', '')),
            title=body.get('title', ''),
            content=body.get('content', ''),
            user_name=body.get('userName', ''),
            user_id=str(body.get('userId', '')),
            tags=[tag.get('tag', '') for tag in body.get('tags', {}).get('tags', [])],
            create_date=body.get('createDate'),
            description=body.get('description', ''),
            text_count=body.get('textCount', 0),
            is_bookmarked=body.get('isBookmarked', False),
            bookmark_count=body.get('bookmarkCount', 0)
        )


@dataclass
class CollectionInfo:
    """珍藏册信息"""
    id: str
    title: str
    artworks: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_artwork_ids(self) -> List[str]:
        """获取所有作品ID"""
        return [str(artwork.get('id', '')) for artwork in self.artworks]
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'CollectionInfo':
        """从 API 响应创建实例"""
        body = data.get('body', {})
        
        return cls(
            id=str(body.get('id', '')),
            title=body.get('title', ''),
            artworks=body.get('artworks', [])
        )


@dataclass
class UserProfile:
    """用户信息"""
    id: str
    name: str
    illusts: List[str] = field(default_factory=list)
    manga: List[str] = field(default_factory=list)
    novels: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    
    def get_all_artwork_ids(self) -> List[str]:
        """获取所有插画ID（包括插画和漫画）"""
        return self.illusts + self.manga
    
    def get_total_works_count(self) -> int:
        """获取总作品数"""
        return len(self.illusts) + len(self.manga) + len(self.novels) + len(self.collections)
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'UserProfile':
        """从 API 响应创建实例"""
        body = data.get('body', {})
        
        # 处理可能是列表或字典的情况
        def extract_ids(works):
            if isinstance(works, dict):
                return list(works.keys())
            elif isinstance(works, list):
                return works
            return []
        
        return cls(
            id=str(body.get('userId', '')),
            name=body.get('userName', ''),
            illusts=extract_ids(body.get('illusts', {})),
            manga=extract_ids(body.get('manga', {})),
            novels=extract_ids(body.get('novels', {})),
            collections=extract_ids(body.get('collections', {}))
        )


@dataclass
class DownloadStats:
    """下载统计信息"""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_size: int = 0  # 字节
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100
    
    @property
    def duration(self) -> float:
        """持续时间（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def average_speed(self) -> float:
        """平均速度（字节/秒）"""
        duration = self.duration
        if duration > 0:
            return self.total_size / duration
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_tasks': self.total_tasks,
            'completed_tasks': self.completed_tasks,
            'failed_tasks': self.failed_tasks,
            'total_size': self.total_size,
            'success_rate': f"{self.success_rate:.2f}%",
            'duration': f"{self.duration:.2f}s",
            'average_speed': f"{self.average_speed / 1024:.2f} KB/s"
        }
