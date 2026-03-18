import json
import logging
import os
import sys
import threading
from functools import wraps
from typing import Callable, Any

from config.settings import ARTWORK_DIR, COLLECTION_DIR, NOVEL_DIR, WORKER_DIR, USER_ARTWORK_DIR, USER_COLLECTION_DIR, \
    USER_NOVEL_DIR
from exceptions import FileOperationException
from utils.helpers import sanitize_filename as clean_filename

CONFIG_FILENAME = "pixivCrawl.json"
DEFAULT_CONFIG = {
    "PHPSESSID": "",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
}


class FileManager:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.file_locks = {}
        self.lock = threading.Lock()
        self._config_path = None

    @property
    def config_path(self) -> str:
        if self._config_path is None:
            self._config_path = os.path.join(
                os.path.dirname(os.path.abspath(sys.argv[0])),
                CONFIG_FILENAME
            )
        return self._config_path

    @staticmethod
    def handle_file_operation(operation_name: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    file_path = kwargs.get('file_path') or (args[1] if len(args) > 1 else 'unknown')
                    raise FileOperationException(f"{operation_name}失败: {file_path}, 错误: {e}")

            return wrapper

        return decorator

    def get_file_lock(self, file_path: str) -> threading.Lock:
        with self.lock:
            if file_path not in self.file_locks:
                self.file_locks[file_path] = threading.Lock()
            return self.file_locks[file_path]

    @handle_file_operation("写入文件")
    def write_file(self, file_path: str, content: bytes, mode: str = 'wb') -> None:
        # 确保目录存在
        self.ensure_directory(os.path.dirname(file_path))

        # 获取文件锁
        file_lock = self.get_file_lock(file_path)

        with file_lock:
            with open(file_path, mode) as f:
                f.write(content)

        self.logger.info(f"文件写入成功: {file_path}")

    def append_file(self, file_path: str, content: bytes) -> None:
        self.write_file(file_path, content, mode='ab')

    @handle_file_operation("删除文件")
    def delete_file(self, file_path: str) -> None:
        if self.file_exists(file_path):
            os.remove(file_path)
            self.logger.info(f"文件删除成功: {file_path}")

    def _get_content_directory(self, base_dir: str, content_id: str) -> str:
        directory = os.path.join(base_dir, str(content_id))
        self.ensure_directory(directory)
        return directory

    def get_artwork_directory(self, artwork_id: str) -> str:
        return self._get_content_directory(ARTWORK_DIR, artwork_id)

    def get_collection_directory(self, collection_id: str) -> str:
        return self._get_content_directory(COLLECTION_DIR, collection_id)

    def get_user_directory(self, user_id: str, artist_name: str = None) -> str:
        """获取画师的根目录
        
        Args:
            user_id: 画师ID
            artist_name: 画师名称（可选，如果提供则使用"名字(id)"格式）
        """
        if artist_name:
            safe_name = clean_filename(artist_name)
            folder_name = f"{safe_name}({user_id})"
            directory = os.path.join(WORKER_DIR, folder_name)
            self.ensure_directory(directory)
            return directory
        return self._get_content_directory(WORKER_DIR, user_id)

    def get_user_artwork_directory(self, user_id: str, artwork_id: str = None, artist_name: str = None) -> str:
        """获取画师模式下的插画目录
        
        Args:
            user_id: 画师ID
            artwork_id: 作品ID（可选，如果不提供则返回artworks根目录）
            artist_name: 画师名称（可选，用于文件夹命名）
        """
        user_dir = self.get_user_directory(user_id, artist_name)
        artwork_base = os.path.join(user_dir, 'artworks')

        if artwork_id:
            artwork_dir = os.path.join(artwork_base, str(artwork_id))
            self.ensure_directory(artwork_dir)
            return artwork_dir
        else:
            self.ensure_directory(artwork_base)
            return artwork_base

    def get_user_collection_directory(self, user_id: str, collection_id: str, artist_name: str = None) -> str:
        user_dir = self.get_user_directory(user_id, artist_name)
        collection_base = os.path.join(user_dir, 'collections')
        collection_dir = os.path.join(collection_base, str(collection_id))
        self.ensure_directory(collection_dir)
        return collection_dir

    def get_user_novel_directory(self, user_id: str, artist_name: str = None) -> str:
        user_dir = self.get_user_directory(user_id, artist_name)
        novel_dir = os.path.join(user_dir, 'novels')
        self.ensure_directory(novel_dir)
        return novel_dir

    def get_user_novel_path(self, user_id: str, novel_id: str, title: str, author: str, artist_name: str = None) -> str:
        novel_dir = self.get_user_novel_directory(user_id, artist_name)
        safe_title = clean_filename(title)
        safe_author = clean_filename(author)
        filename = f"《{safe_title}》- {safe_author}.txt"
        return os.path.join(novel_dir, filename)

    @staticmethod
    def get_novel_path(title: str, author: str) -> str:
        safe_title = clean_filename(title)
        safe_author = clean_filename(author)
        filename = f"《{safe_title}》- {safe_author}.txt"
        return os.path.join(NOVEL_DIR, filename)

    @staticmethod
    def get_novel_directory() -> str:
        return NOVEL_DIR

    @staticmethod
    @handle_file_operation("创建目录")
    def ensure_directory(directory: str):
        os.makedirs(directory, exist_ok=True)

    @staticmethod
    @handle_file_operation("读取文件")
    def read_file(file_path: str, mode: str = 'rb') -> bytes:
        with open(file_path, mode) as f:
            return f.read()

    @staticmethod
    def file_exists(file_path: str) -> bool:
        return os.path.exists(file_path) and os.path.isfile(file_path)

    @staticmethod
    @handle_file_operation("获取文件大小")
    def get_file_size(file_path: str) -> int:
        return os.path.getsize(file_path)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        # Windows 非法字符
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        return filename.strip()

    @staticmethod
    def create_temp_resource(relative_path: str) -> str:
        # PyInstaller 创建临时文件夹，所有 pyInstaller 程序运行时解压后的文件都在 _MEIPASS 中
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    @staticmethod
    def create_directory(*base_dir: str) -> str:
        script_path = os.path.abspath(sys.argv[0])  # 获取绝对路径
        parent_dir = os.path.dirname(script_path)
        mkdir = os.path.join(parent_dir, *base_dir)
        os.makedirs(mkdir, exist_ok=True)
        return mkdir

    def _read_or_create_config(self) -> dict:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保必要字段存在
                if 'PHPSESSID' not in data:
                    data["PHPSESSID"] = ""
                    self._write_config(data)
                return data
        except FileNotFoundError:
            logging.info("未找到配置文件，正在创建默认配置文件。")
            self._write_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

    def _write_config(self, data: dict) -> None:
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def read_json(self) -> dict:
        return self._read_or_create_config()

    def update_json(self, data_id: str) -> None:
        data = self._read_or_create_config()
        data["PHPSESSID"] = data_id.replace("PHPSESSID=", "")
        self._write_config(data)
        logging.info("成功更新配置文件，下次失效时再进行填写。")

    @staticmethod
    @handle_file_operation("创建空文件")
    def touch(file_path: str) -> None:
        with open(file_path, 'wb') as f:
            f.truncate(0)
