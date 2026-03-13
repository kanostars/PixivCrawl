import json
import logging
import os


def _create_empty_history():
    """创建空的历史记录结构"""
    return {
        "artist_id": "",
        "artist_name": "",
        "last_update": "",
        "downloaded_artworks": [],
        "downloaded_collections": [],
        "downloaded_novels": [],
        "total_count": 0
    }


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
                return _create_empty_history()
        return _create_empty_history()

    def get_downloaded_ids(self):
        """获取已下载的作品ID集合（包括插画、珍藏册、小说）"""
        artworks = set(self.history_data.get("downloaded_artworks", []))
        collections = set(self.history_data.get("downloaded_collections", []))
        novels = set(self.history_data.get("downloaded_novels", []))
        return artworks | collections | novels

    def add_artwork(self, artwork_id):
        """
        添加一个已下载的作品ID
        :param artwork_id: 作品ID
        """
        if artwork_id not in self.history_data["downloaded_artworks"]:
            self.history_data["downloaded_artworks"].append(artwork_id)
            self._update_total_count()
            self._save_history()

    def add_collection(self, collection_id):
        """
        添加一个已下载的珍藏册ID
        :param collection_id: 珍藏册ID
        """
        if "downloaded_collections" not in self.history_data:
            self.history_data["downloaded_collections"] = []
        if collection_id not in self.history_data["downloaded_collections"]:
            self.history_data["downloaded_collections"].append(collection_id)
            self._update_total_count()
            self._save_history()

    def add_novel(self, novel_id):
        """
        添加一个已下载的小说ID
        :param novel_id: 小说ID
        """
        if "downloaded_novels" not in self.history_data:
            self.history_data["downloaded_novels"] = []
        if novel_id not in self.history_data["downloaded_novels"]:
            self.history_data["downloaded_novels"].append(novel_id)
            self._update_total_count()
            self._save_history()

    def _update_total_count(self):
        """更新总下载数量"""
        self.history_data["total_count"] = (
            len(self.history_data.get("downloaded_artworks", [])) +
            len(self.history_data.get("downloaded_collections", [])) +
            len(self.history_data.get("downloaded_novels", []))
        )

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