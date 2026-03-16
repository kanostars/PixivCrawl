import logging
import requests
from typing import Optional

from storage.file_manager import FileManager


class SessionManager:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.session: Optional[requests.Session] = None
        self.file_manager = FileManager()
        self.cookie_value: Optional[str] = None

    def init_session(self) -> requests.Session:
        try:
            # 读取配置
            config = self.file_manager.read_json()
            self.cookie_value = config.get("PHPSESSID", "")

            # 创建 Session
            self.session = requests.Session()
            if self.cookie_value:
                self.session.cookies.set('PHPSESSID', self.cookie_value)
                self.logger.debug("已加载 Cookie")

            return self.session

        except Exception as e:
            self.logger.error(f"初始化 Session 失败: {e}")
            raise

    def update_cookie(self, cookie_value: str) -> None:
        try:
            # 清理 Cookie 值
            cookie_value = cookie_value.replace("PHPSESSID=", "").strip()

            # 更新到配置文件
            self.file_manager.update_json(cookie_value)

            # 更新到 Session
            if self.session:
                self.session.cookies.set('PHPSESSID', cookie_value)

            self.cookie_value = cookie_value
            self.logger.info("Cookie 已更新")

        except Exception as e:
            self.logger.error(f"更新 Cookie 失败: {e}")
            raise

    def clear_cookie(self) -> None:
        try:
            self.file_manager.update_json("")

            if self.session:
                self.session.cookies.clear()

            self.cookie_value = None
            self.logger.info("Cookie 已清除")

        except Exception as e:
            self.logger.error(f"清除 Cookie 失败: {e}")
            raise

    def get_session(self) -> requests.Session:
        if not self.session:
            return self.init_session()
        return self.session
