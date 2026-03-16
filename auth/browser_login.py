import logging
from typing import Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from utils.helpers import extract_username


class BrowserLogin:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def login(self, timeout: int = 300) -> Tuple[Optional[str], Optional[str]]:
        driver = None
        try:
            self.logger.info("正在打开浏览器，请稍后...")

            service = Service(executable_path=ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service)

            driver.get('https://accounts.pixiv.net/login?lang=zh&source=pc&view_type=page')

            WebDriverWait(driver, timeout).until(
                EC.url_contains("www.pixiv.net")
            )

            cookie_value = None
            for cookie in driver.get_cookies():
                if cookie['name'] == 'PHPSESSID':
                    cookie_value = cookie['value']
                    self.logger.debug(f'获得 Cookie: {cookie_value}')
                    break
            
            if not cookie_value:
                self.logger.warning("未能获取 PHPSESSID Cookie")
                return None, None

            username = extract_username(driver.page_source)
            
            if username:
                self.logger.info(f"用户 {username} 登录成功")
            else:
                self.logger.warning("登录成功但未能获取用户名")
            
            return cookie_value, username

        except Exception as e:
            self.logger.error(f"浏览器登录失败: {e}")
            return None, None

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    self.logger.debug(f"关闭浏览器时出错: {e}")
