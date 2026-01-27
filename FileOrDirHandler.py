import json
import logging
import os
import re
import sys


class FileHandlerManager:

    # 创建文件夹
    @staticmethod
    def create_directory(*base_dir):
        script_path = os.path.abspath(sys.argv[0])  # 获取绝对路径
        parent_dir = os.path.dirname(script_path)
        mkdir = os.path.join(parent_dir, *base_dir)
        os.makedirs(mkdir, exist_ok=True)
        return mkdir

    # 读取json文件
    @staticmethod
    def read_json():
        json_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "pixivCrawl.json")
        default_data = {
            "PHPSESSID": "",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
        }
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'PHPSESSID' not in data:
                    data["PHPSESSID"] = ""
                    FileHandlerManager.update_json('')
                return data
        except FileNotFoundError:
            logging.info("未找到配置文件，正在创建默认配置文件。")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
            return default_data

    # 更新json文件
    @staticmethod
    def update_json(data_id):
        json_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "pixivCrawl.json")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data["PHPSESSID"] = data_id.replace("PHPSESSID=", "")

        with open(json_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=4))
        logging.info(f"成功更新配置文件，下次失效时再进行填写。")

    # 创建或更新文件，清空文件内容
    @staticmethod
    def touch(file_path):
        try:
            with open(file_path, 'wb') as f:
                f.truncate(0)
        except OSError as e:
            logging.error(f"无法创建文件 {file_path}，错误原因：{e}")

    # 获取资源文件的绝对路径
    @staticmethod
    def resource_path(relative_path):
        # PyInstaller 创建临时文件夹，所有 pyInstaller 程序运行时解压后的文件都在 _MEIPASS 中
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # 移除Windows的非法字符
    @staticmethod
    def sanitize_filename(filename):
        if filename is None:
            return None
        cleaned = re.sub(r'[\\/*?:"<>|]', "_", filename)
        return cleaned.strip()


class DownloadHistoryManager:
    """下载历史记录管理器"""

    def __init__(self, artist_folder):
        """
        初始化管理器
        :param artist_folder: 画师作品文件夹路径
        """
        self.artist_folder = artist_folder
        self.history_file = os.path.join(artist_folder, "install.json")
        self.history_data = self._load_history()

    def _load_history(self):
        """加载历史记录，如果文件不存在则返回空结构"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"读取下载历史失败: {e}，将创建新记录")
                return self._create_empty_history()
        return self._create_empty_history()

    def _create_empty_history(self):
        """创建空的历史记录结构"""
        return {
            "artist_id": "",
            "artist_name": "",
            "last_update": "",
            "downloaded_artworks": [],
            "total_count": 0
        }

    def get_downloaded_ids(self):
        """获取已下载的作品ID集合"""
        return set(self.history_data.get("downloaded_artworks", []))

    def add_artwork(self, artwork_id):
        """
        添加一个已下载的作品ID
        :param artwork_id: 作品ID
        """
        if artwork_id not in self.history_data["downloaded_artworks"]:
            self.history_data["downloaded_artworks"].append(artwork_id)
            self.history_data["total_count"] = len(self.history_data["downloaded_artworks"])
            self._save_history()

    def update_metadata(self, artist_id, artist_name):
        """
        更新画师元数据
        :param artist_id: 画师ID
        :param artist_name: 画师名称
        """
        self.history_data["artist_id"] = artist_id
        self.history_data["artist_name"] = artist_name
        self._save_history()

    def _save_history(self):
        """保存历史记录到文件"""
        from datetime import datetime
        self.history_data["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logging.error(f"保存下载历史失败: {e}")
