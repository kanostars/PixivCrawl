import os
import logging
import requests
from functools import wraps
from typing import Optional, List
from config.settings import (
    BASE_URL, API_ENDPOINTS, RATE_LIMIT,
    CONNECT_TIMEOUT, READ_TIMEOUT, RETRY_STATUS_CODES,
    CHUNK_SIZE, get_headers
)
from api.rate_limiter import RateLimiter
from api.models import ArtworkInfo, ArtworkPage, UgoiraMeta, NovelInfo, UserProfile
from exceptions import NetworkException, AuthenticationException, ResourceNotFoundException


def handle_network_errors(func):
    """网络错误处理装饰器"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.Timeout:
            raise NetworkException("请求超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise NetworkException("网络连接失败，请检查代理设置")
        except requests.exceptions.RequestException as e:
            raise NetworkException(f"网络请求失败: {str(e)}")

    return wrapper


class PixivAPI:
    """Pixiv API 请求封装"""

    def __init__(self, session: requests.Session, headers: dict = None) -> None:
        """
        初始化 API 客户端

        Args:
            session: requests.Session 对象
            headers: 请求头字典
        """
        self.session = session
        self.headers = headers or get_headers()
        self.rate_limiter = RateLimiter(rate_per_second=RATE_LIMIT)
        self.logger = logging.getLogger(__name__)

    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> dict:
        """
        发起 HTTP 请求

        Args:
            url: 请求 URL
            method: 请求方法
            max_retries: 最大重试次数（仅针对 429 错误）
            **kwargs: 其他请求参数

        Returns:
            响应的 JSON 数据
        """
        kwargs.setdefault('headers', self.headers)
        kwargs.setdefault('verify', False)
        kwargs.setdefault('timeout', (CONNECT_TIMEOUT, READ_TIMEOUT))

        self.rate_limiter.acquire()

        try:
            response = self.session.request(method, url, **kwargs)

            if response.status_code == 429:
                raise NetworkException(f"服务器错误: 429; 图片被限制下载，跳过该图片，请稍后重新下载。")
            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationException("认证失败，请检查 Cookie 是否有效")
            elif response.status_code == 404:
                raise ResourceNotFoundException("资源不存在")
            elif response.status_code in RETRY_STATUS_CODES:
                raise NetworkException(f"服务器错误: {response.status_code}")

            response.raise_for_status()

            try:
                data = response.json()
                if data.get('error'):
                    raise NetworkException(f"API 返回错误: {data.get('message', '未知错误')}")
                return data.get('body', data)
            except ValueError:
                return response.text

        except NetworkException as e:
            last_exception = e
            if "429" not in str(e):
                raise

        if last_exception:
            raise last_exception
        raise NetworkException("请求失败")

    @handle_network_errors
    def get_user_works(self, user_id: str) -> UserProfile:
        """
        获取用户的所有作品

        Args:
            user_id: 用户 ID

        Returns:
            用户作品数据模型
        """
        url = f"{BASE_URL}{API_ENDPOINTS['user_profile']}?lang=zh"
        url = url.format(user_id=user_id)
        self.logger.info(f"获取用户 {user_id} 的作品列表")
        data = self._make_request(url)

        # 记录返回的数据类型和结构（用于调试）
        self.logger.debug(f"API 返回数据类型：{type(data).__name__}")
        if isinstance(data, dict):
            self.logger.debug(f"返回的键：{list(data.keys())[:10]}")  # 只显示前 10 个键

        # 返回数据模型
        return UserProfile.from_api_response({'body': data})

    @handle_network_errors
    def get_artwork_info(self, artwork_id: str) -> ArtworkInfo:
        """
        获取插画基本信息

        Args:
            artwork_id: 插画 ID

        Returns:
            插画信息数据模型
        """
        url = f"{BASE_URL}{API_ENDPOINTS['artwork']}"
        url = url.format(artwork_id=artwork_id)
        self.logger.debug(f"获取插画 {artwork_id} 的信息")
        data = self._make_request(url)
        return ArtworkInfo.from_api_response({'body': data})

    @handle_network_errors
    def get_artwork_pages(self, artwork_id: str) -> List[ArtworkPage]:
        """
        获取插画的所有页面
        
        Args:
            artwork_id: 插画 ID
            
        Returns:
            插画页面列表
        """
        url = f"{BASE_URL}{API_ENDPOINTS['artwork_pages']}"
        url = url.format(artwork_id=artwork_id)
        self.logger.debug(f"获取插画 {artwork_id} 的页面")
        data = self._make_request(url)
        
        # 转换为 ArtworkPage 对象列表
        pages = []
        if isinstance(data, list):
            for page_data in data:
                pages.append(ArtworkPage(
                    urls=page_data.get('urls', {}),
                    width=page_data.get('width', 0),
                    height=page_data.get('height', 0)
                ))
        return pages

    @handle_network_errors
    def get_collection_artworks(self, collection_id: str) -> dict:
        """
        获取珍藏册中的作品
        
        Args:
            collection_id: 珍藏册 ID
            
        Returns:
            珍藏册中的作品列表
        """
        url = f"{BASE_URL}{API_ENDPOINTS['collection']}?lang=zh"
        url = url.format(collection_id=collection_id)
        self.logger.debug(f"获取珍藏册 {collection_id} 的作品")
        data = self._make_request(url)
        return data.get('thumbnails', {}).get('illust', [])

    @handle_network_errors
    def get_novel_content(self, novel_id: str) -> NovelInfo:
        """
        获取小说内容
        
        Args:
            novel_id: 小说 ID
            
        Returns:
            小说内容数据模型
        """
        url = f"{BASE_URL}{API_ENDPOINTS['novel']}?lang=zh"
        url = url.format(novel_id=novel_id)
        self.logger.debug(f"获取小说 {novel_id} 的内容")
        data = self._make_request(url)
        return NovelInfo.from_api_response({'body': data})

    def get_ugoira_meta(self, illust_id: str) -> Optional[UgoiraMeta]:
        """
        获取动图元数据，若为静态图则返回 None
        
        Args:
            illust_id: 插画 ID
            
        Returns:
            动图元数据模型，静态图返回 None
        """
        url = f"{BASE_URL}{API_ENDPOINTS['ugoira']}"
        url = url.format(illust_id=illust_id)
        self.logger.debug(f"检查插画 {illust_id} 是否为动图")

        self.rate_limiter.acquire()

        try:
            response = self.session.get(
                url, headers=self.headers, verify=False,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )

            if response.status_code == 429:
                raise NetworkException(f"服务器错误: 429; 图片被限制下载，跳过该图片，请稍后重新下载。")

            if response.status_code == 404:
                return None  # 静态图

            response.raise_for_status()
            data = response.json()
            if data.get('error'):
                return None  # 静态图
            return UgoiraMeta.from_api_response(data)

        except requests.exceptions.HTTPError as e:
            if "404" in str(e):
                return None
            last_exception = e
            if "429" not in str(e):
                raise

        if last_exception:
            raise last_exception
        return None

    @handle_network_errors
    def download_file(self, url: str, save_path: str, start: int = 0, end: int = 0) -> None:
        """
        下载文件
        
        Args:
            url: 文件 URL
            save_path: 保存路径
            start: 起始字节位置
            end: 结束字节位置
        """
        self.rate_limiter.acquire()

        headers = self.headers.copy()
        if start > 0 or end > 0:
            headers['Range'] = f'bytes={start}-{end}' if end > 0 else f'bytes={start}-'

        response = self.session.get(
            url,
            headers=headers,
            verify=False,
            stream=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
        )
        response.raise_for_status()

        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # 写入文件
        mode = 'ab' if start > 0 else 'wb'
        with open(save_path, mode) as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
