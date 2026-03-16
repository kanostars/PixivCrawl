import logging
from typing import Optional, Callable

import requests

from auth.browser_login import BrowserLogin
from auth.session_manager import SessionManager
from config.settings import get_headers
from utils.helpers import extract_username


class LoginManager:
    def __init__(self, session_manager: SessionManager) -> None:
        self.logger = logging.getLogger(__name__)
        self.session_manager = session_manager
        self.browser_login = BrowserLogin()
        
        self.is_logged_in = False
        self.username: Optional[str] = None

    def check_login_status(self) -> bool:
        try:
            self.logger.info("正在检查登录状态...")
            
            session = self.session_manager.get_session()
            
            # 请求 Pixiv 首页
            response = session.get(
                'https://www.pixiv.net/',
                headers=get_headers(),
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                username = extract_username(response.text)
                if username:
                    self.username = username
                    self.is_logged_in = True
                    self.logger.info(f'{username} 已登录')
                    return True
                else:
                    self.logger.warning("登录失败或 Cookie 已失效")
                    self.is_logged_in = False
                    return False
            else:
                self.logger.warning(f"请求失败，状态码: {response.status_code}")
                self.is_logged_in = False
                return False

        except requests.exceptions.ConnectionError:
            self.logger.warning("网络请求失败，请检查网络连接")
            return False
        except Exception as e:
            self.logger.error(f"检查登录状态失败: {e}")
            return False

    def login(self, on_success: Optional[Callable] = None, on_failure: Optional[Callable] = None) -> bool:
        try:
            self.logger.info("请求登录中...")
            cookie_value, username = self.browser_login.login()
            
            if cookie_value and username:
                # 更新 Cookie
                self.session_manager.update_cookie(cookie_value)
                
                # 更新状态
                self.username = username
                self.is_logged_in = True
                
                self.logger.info(f"用户 {username} 登录成功")
                
                # 调用成功回调
                if on_success:
                    on_success(username)
                
                return True
            else:
                self.logger.info("登录已取消或失败")
                
                # 调用失败回调
                if on_failure:
                    on_failure()
                
                return False

        except Exception as e:
            self.logger.error(f"登录失败: {e}")
            
            if on_failure:
                on_failure()
            
            return False

    def logout(self, on_success: Optional[Callable] = None) -> bool:
        try:
            self.logger.info("正在退出登录...")
            self.session_manager.clear_cookie()

            self.is_logged_in = False
            self.username = None
            
            self.logger.info("已成功退出")

            if on_success:
                on_success()
            
            return True

        except Exception as e:
            self.logger.error(f"退出登录失败: {e}")
            return False

    def get_username(self) -> Optional[str]:
        return self.username

    def is_authenticated(self) -> bool:
        return self.is_logged_in
