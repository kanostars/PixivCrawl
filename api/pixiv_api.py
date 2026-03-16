import os
import logging
import requests
from functools import wraps
from config.settings import (
    BASE_URL, API_ENDPOINTS, RATE_LIMIT,
    CONNECT_TIMEOUT, READ_TIMEOUT, RETRY_STATUS_CODES,
    CHUNK_SIZE, get_headers
)
from api.rate_limiter import RateLimiter
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
            **kwargs: 其他请求参数

        Returns:
            响应的 JSON 数据
        """
        self.rate_limiter.acquire()

        kwargs.setdefault('headers', self.headers)
        kwargs.setdefault('verify', False)
        kwargs.setdefault('timeout', (CONNECT_TIMEOUT, READ_TIMEOUT))

        response = self.session.request(method, url, **kwargs)

        # 处理 HTTP 状态码
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

    @handle_network_errors
    def get_user_works(self, user_id: str) -> dict:
        """
        获取用户的所有作品

        Args:
            user_id: 用户 ID

        Returns:
            用户作品数据
        """
        url = f"{BASE_URL}{API_ENDPOINTS['user_profile']}?lang=zh"
        url = url.format(user_id=user_id)
        self.logger.info(f"获取用户 {user_id} 的作品列表")
        data = self._make_request(url)

        # 记录返回的数据类型和结构（用于调试）
        self.logger.debug(f"API 返回数据类型：{type(data).__name__}")
        if isinstance(data, dict):
            self.logger.debug(f"返回的键：{list(data.keys())[:10]}")  # 只显示前 10 个键

        return data

    @handle_network_errors
    def get_artwork_info(self, artwork_id: str) -> dict:
        """
        获取插画基本信息

        Args:
            artwork_id: 插画 ID

        Returns:
            插画信息
        """
        url = f"{BASE_URL}{API_ENDPOINTS['artwork']}"
        url = url.format(artwork_id=artwork_id)
        self.logger.debug(f"获取插画 {artwork_id} 的信息")
        return self._make_request(url)

    @handle_network_errors
    def get_artwork_pages(self, artwork_id: str) -> dict:
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
        return self._make_request(url)

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
    def get_novel_content(self, novel_id: str) -> dict:
        """
        获取小说内容
        
        Args:
            novel_id: 小说 ID
            
        Returns:
            小说内容数据
        """
        url = f"{BASE_URL}{API_ENDPOINTS['novel']}?lang=zh"
        url = url.format(novel_id=novel_id)
        self.logger.debug(f"获取小说 {novel_id} 的内容")
        return self._make_request(url)

    def get_ugoira_meta(self, illust_id: str) -> dict | None:
        """
        获取动图元数据，若为静态图则返回 None
        
        Args:
            illust_id: 插画 ID
            
        Returns:
            动图元数据，静态图返回 None
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
            response.raise_for_status()
            data = response.json()
            if data.get('error'):
                return None  # 静态图
            return data.get('body', data)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

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
