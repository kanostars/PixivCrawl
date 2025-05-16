import logging
import os
import sys
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile

from PyQt6.QtNetwork import QNetworkCookie


# os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = '--host-rules="MAP api.fanbox.cc api.fanbox.cc,MAP *pixiv.net pixivision.net,MAP *fanbox.cc pixivision.net,MAP *pximg.net U4" --host-resolver-rules="MAP api.fanbox.cc 172.64.146.116,MAP pixivision.net 210.140.139.155,MAP U4 210.140.139.133" --test-type --ignore-certificate-errors'
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = '--test-type --ignore-certificate-errors'

class CookieMonitor(QWebEngineView):
    cookie_received = pyqtSignal(str)  # 新增信号

    def __init__(self, target_url):
        try:
            super().__init__()
            self.is_user_close = True
            self.cookie = ""
            self.target_host = QUrl('https://www.pixiv.net/').host()
            self.cookie_store = QWebEngineProfile.defaultProfile().cookieStore()
            self.loadFinished.connect(self.on_load_finished)
            self.cookie_store.cookieAdded.connect(self.handle_cookie_added)
            self.load(QUrl(target_url))
        except Exception as e:
            logging.error(f"WebEngine初始化失败: {str(e)}")

    def on_load_finished(self, ok):
        if ok and self.url().host() == self.target_host:
            logging.debug(f"已进入目标页面: {self.url().toString()} {self.target_host}")
            logging.debug(f"已获取Cookie: {str(self.cookie)}")
            self.cookie_received.emit(str(self.cookie))
            self.is_user_close = False
            self.close()

    def handle_cookie_added(self, cookie: QNetworkCookie):
        if cookie.name() == b"PHPSESSID":
            cookie_value = cookie.value().data().decode('utf-8')
            self.cookie = cookie_value

    def is_target_cookie(self, cookie):
        # 检查Cookie域名是否匹配目标页面
        return self.target_host in cookie.domain() or cookie.domain() == f".{self.target_host}"

    def closeEvent(self, event):
        if self.is_user_close:
            logging.info("用户取消登录")
        event.accept()
        self.deleteLater()


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        monitor = CookieMonitor("https://accounts.pixiv.net/login")
        monitor.show()
        app.exec()
    except Exception as e:
        print(f"发生错误: {e}")
