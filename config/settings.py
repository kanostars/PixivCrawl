import os

TYPE_USER = 'users'
TYPE_ARTWORK = 'artworks'
TYPE_COLLECTION = 'collection'
TYPE_NOVEL = 'novel'

STATUS_PENDING = 'pending'
STATUS_DOWNLOADING = 'downloading'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
STATUS_PAUSED = 'paused'

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
NOVEL_EXTENSION = '.txt'
UGOIRA_EXTENSION = '.gif'

ERROR_NETWORK = '网络错误'
ERROR_AUTH = '认证失败'
ERROR_NOT_FOUND = '资源不存在'
ERROR_DOWNLOAD = '下载失败'
ERROR_FILE_IO = '文件操作失败'

CONFIG_FILENAME = 'pixivCrawl.json'
DEFAULT_CONFIG = {
    'PHPSESSID': '',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
}


BASE_URL = 'https://www.pixiv.net'
API_ENDPOINTS = {
    'user_profile': '/ajax/user/{user_id}/profile/all',
    'artwork': '/ajax/illust/{artwork_id}',
    'artwork_pages': '/ajax/illust/{artwork_id}/pages',
    'collection': '/ajax/collection/{collection_id}',
    'novel': '/ajax/novel/{novel_id}',
    'ugoira': '/ajax/illust/{illust_id}/ugoira_meta'
}

LINK_ENDPOINTS = {
    TYPE_USER: '/users/{user_id}',
    TYPE_ARTWORK: '/artworks/{artwork_id}',
    TYPE_COLLECTION: '/collections/{collection_id}',
    TYPE_NOVEL: '/novel/show.php?id={novel_id}'
}


# 下载配置
MAX_WORKERS = min(os.cpu_count() or 4, 4)
CHUNK_SIZE = 1024 * 1024  # 1MB
RATE_LIMIT = 3  # 每秒请求数

# 超时配置
CONNECT_TIMEOUT = 10  # 连接超时（秒）
READ_TIMEOUT = 30  # 读取超时（秒）

# 批次处理配置
BATCH_SIZE = 20  # 每批处理的作品数
BATCH_INTERVAL = 2  # 批次间隔（秒）

# 重试配置
MAX_RETRIES = 5
BACKOFF_FACTOR = 5
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

# 目录配置
BASE_DIR = 'content'
ARTWORK_DIR = os.path.join(BASE_DIR, 'artworks_IMG')  # 图像作品目录
WORKER_DIR = os.path.join(BASE_DIR, 'workers_IMG')  # 画师目录
COLLECTION_DIR = os.path.join(BASE_DIR, 'collections_IMG')  # 收藏册目录
NOVEL_DIR = os.path.join(BASE_DIR, 'novels')  # 小说目录
LOG_DIR = 'log'

USER_ARTWORK_DIR = os.path.join(WORKER_DIR, '{user_id}/artworks')  # 画师作品目录
USER_COLLECTION_DIR = os.path.join(WORKER_DIR, '{user_id}/collections')  # 画师收藏册目录
USER_NOVEL_DIR = os.path.join(WORKER_DIR, '{user_id}/novels')  # 画师小说目录


# 日志配置
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5


def get_headers():
    """获取默认请求头"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.pixiv.net/'
    }


def ensure_directories():
    """确保所有必要的目录存在"""
    directories = [
        ARTWORK_DIR,
        WORKER_DIR,
        COLLECTION_DIR,
        NOVEL_DIR,
        LOG_DIR
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
