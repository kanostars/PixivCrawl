import logging
import sys
import threading
import webbrowser
import os
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QEvent
from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QCheckBox,
    QProgressBar, QTextEdit, QButtonGroup
)

from FileOrDirHandler import FileHandler
from LogHandler import log_init, QtLogHandler
from LoginHandler import CookieMonitor
from PixivDownloader import ThroughId, get_username

TYPE_WORKER = "users"  # 类型是画师
TYPE_ARTWORKS = "artworks"  # 类型是插画
type_config = {
    0: TYPE_WORKER,  # 画师配置
    1: TYPE_ARTWORKS  # 插画配置
}
preCookie = f'{FileHandler.read_json()["PHPSESSID"]}'

class PixivApp(QMainWindow):
    update_ui = pyqtSignal(bool)

    def __init__(self, qt_handler=None):
        super().__init__()
        self.login_window = None
        self.download_thread = None
        self.downloader = None
        self.init_ui()
        self.qt_handler = QtLogHandler(self.log_text) if qt_handler is None else qt_handler

        self.isLogin = False  # 登录状态
        self.is_paused_btn = False  # 暂停按钮的状态
        self.is_stopped_btn = False  # 停止按钮的状态
        self.total_progress = 0
        self.current_progress = 0
        self.connect_signals()
        if not logging.getLogger().handlers:
            log_init(self.qt_handler)
        else:
            logging.getLogger().addHandler(self.qt_handler)
        threading.Thread(target=self.handle_login_cookie, args=(preCookie,), daemon=True).start()

    def init_ui(self):
        self.setWindowTitle('pixiv下载器')
        self.setFixedSize(430, 570)

        main_widget = QWidget()
        bg_color = self.palette().color(QPalette.ColorRole.Window).name()
        text_color = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.setStyleSheet(f"""
               QWidget {{
                   background-color: {bg_color};
                   color: {text_color};
               }}
               QPushButton {{ 
                   background-color: {self.palette().color(QPalette.ColorRole.Button).name()};
                   color: {self.palette().color(QPalette.ColorRole.ButtonText).name()};
               }}
           """)

        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 15, 20, 15)

        # 登录区域
        login_layout = QHBoxLayout()
        self.login_btn = QPushButton("登录")
        self.login_btn.setFixedSize(100, 30)
        self.welcome_label = QLabel("欢迎，登录可以下载更多图片！")
        login_layout.addWidget(self.welcome_label)
        login_layout.addWidget(self.login_btn)
        layout.addLayout(login_layout)

        # 输入区域
        input_layout = QHBoxLayout()
        self.uid_input = QLineEdit()
        self.uid_input.setStyleSheet("padding: 5px;")
        self.type_group = QButtonGroup(self)
        self.artist_radio = QRadioButton("画师")
        self.artwork_radio = QRadioButton("插画")
        self.type_group.addButton(self.artist_radio, 0)
        self.type_group.addButton(self.artwork_radio, 1)
        self.type_group.button(0).setChecked(True)  # 默认选中画师
        input_layout.addWidget(QLabel("请输入链接/UID:"))
        input_layout.addWidget(self.uid_input)
        input_layout.addWidget(self.artist_radio)
        input_layout.addWidget(self.artwork_radio)
        input_layout.setContentsMargins(0, 10, 0, 10)

        layout.addLayout(input_layout)

        # 选项和提交区域
        options_layout = QHBoxLayout()
        self.space_check = QCheckBox("跳转空间")
        self.open_check = QCheckBox("下载后打开")
        self.exit_check = QCheckBox("下载后退出")
        self.open_check.setChecked(True)
        self.submit_btn = QPushButton("提交")
        self.submit_btn.setStyleSheet("background-color: gray;")
        self.submit_btn.setFont(QFont("黑体", 15))
        options_layout.addWidget(self.space_check)
        options_layout.addWidget(self.exit_check)
        options_layout.addWidget(self.open_check)
        options_layout.addWidget(self.submit_btn)
        options_layout.setContentsMargins(0, 10, 0, 10)
        layout.addLayout(options_layout)

        # 进度条区域
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
                  QProgressBar {{
                      height: 15px;
                      background: white;
                      border: 2px solid gray;
                      border-radius: 5px;
                      text-align: center;
                  }}
                  QProgressBar::chunk {{
                      background-color: lightblue;
                       background: qlineargradient(
                      x1:0, y1:0, x2:1, y2:0,
                      stop:0 lightblue, 
                      stop:1 #FFB6C1
                  );
                  margin: 0.5px;  
                          }}
              """)

        self.progress_label = QLabel("0%")
        self.progress_label.setContentsMargins(10, 0, 0, 0)
        self.stop_btn = QPushButton("X")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: red;")
        self.stop_btn.setFixedSize(30, 30)
        self.pause_btn = QPushButton("||")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setFixedSize(30, 30)
        progress_layout.addWidget(self.progress_label, stretch=10)
        progress_layout.addWidget(self.progress_bar, stretch=90)
        progress_layout.addWidget(self.pause_btn, stretch=0)
        progress_layout.addWidget(self.stop_btn, stretch=0)
        layout.addLayout(progress_layout)

        # 日志区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.append('欢迎使用 PIXIV 图片下载器 ！\n登录以下载更多图片，失效时再重新登录。\n')
        layout.addWidget(self.log_text)

    def update_progress(self, increment, total=0):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.current_progress = 0
        else:
            self.current_progress += increment
        self.progress_bar.setValue(self.current_progress)
        progress_percent = (self.current_progress / self.progress_bar.maximum()) * 100
        self.progress_label.setText(f"{progress_percent:.2f}%")
        # 强制刷新UI
        QApplication.processEvents()

    def handle_progress(self, increment, total):
        if not self.downloader:
            return
        if total > 0:
            self.update_progress(0, total)  # 设置最大值
        else:
            self.update_progress(increment, 0)  # 增量更新

    def update_progress_bar_color(self, color_name):
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                height: 15px;
                background: white;
                border: 2px solid gray;
                border-radius: 5px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {color_name};
                 background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {color_name}, 
                stop:1 #FFB6C1
            );
            margin: 0.5px;  
                    }}
        """)

    def login_or_out(self):
        if self.isLogin:  # 注销
            logging.info("用户请求注销中。。。")
            FileHandler.update_json("")
            self.welcome_label.setText("欢迎，登录可以下载更多图片！")
            self.login_btn.setText("登录")
            self.isLogin = False
            logging.info("用户已成功注销")
        else:  # 登录
            if not self.login_window:
                logging.info("用户请求登录中。。。")
                self.login_window = CookieMonitor("https://accounts.pixiv.net/login")
                self.login_window.setWindowTitle("Pixiv登录窗口")
                self.login_window.setMinimumSize(800, 600)
                self.login_window.cookie_received.connect(self.handle_login_cookie)
                self.login_window.destroyed.connect(lambda: setattr(self, 'login_window', None))
                self.login_window.show()

    def handle_login_cookie(self, cookie_value: str):
        if not cookie_value:
            return
        try:
            logging.debug(f"接收到登录Cookie: {cookie_value}")
            FileHandler.update_json(cookie_value)
            username = get_username()
            logging.debug(f"用户名: {username}")
            if username:
                self.welcome_label.setText(f"欢迎，{username}！")
                self.login_btn.setText("注销")
                self.isLogin = True
                logging.info(f"登录成功: {username}")

                if self.downloader:
                    self.downloader.reset_session()
            else:
                logging.warning("获取用户信息失败，请检查网络连接或cookie有效性")

        except Exception as e:
            logging.error(f"处理登录Cookie时出错: {str(e)}")
            self.welcome_label.setText("登录状态异常，请重新登录")
            self.login_btn.setText("登录")
            self.isLogin = False

    def submit_id(self):
        try:
            self.update_progress(0, 0)
            self.progress_bar.setStyleSheet(f"""
                             QProgressBar {{
                                 height: 15px;
                                 background: white;
                                 border: 2px solid gray;
                                 border-radius: 5px;
                                 text-align: center;
                             }}
                             QProgressBar::chunk {{
                                 background-color: lightblue;
                                  background: qlineargradient(
                                 x1:0, y1:0, x2:1, y2:0,
                                 stop:0 lightblue, 
                                 stop:1 #FFB6C1
                             );
                             margin: 0.5px;  
                                     }}
                         """)

            if self.downloader and self.download_thread.is_alive():
                self.downloader.stop_all_tasks()
                self.download_thread.join(2)

            self.pause_btn.setText('||')
            self.update_button_state(False)

            input_uid = self.uid_input.text()
            if not input_uid:
                logging.warning('输入不能为空')
                self.update_ui.emit(True)
                return

            selected_type = type_config[self.type_group.checkedId()]
            parts = input_uid.split(f'/{selected_type}/')
            input_uid = parts[-1].split('/')[0] if parts else input_uid
            parts = input_uid.split('?')
            input_uid = parts[0] if parts else input_uid

            if self.space_check.isChecked():
                url = f"https://www.pixiv.net/{selected_type}/{input_uid}"
                logging.info(f"正在跳转空间: {url}")
                webbrowser.open(url)

            self.downloader = ThroughId(input_uid, self, selected_type)
            self.downloader.progress_updated.connect(
                self.handle_progress,
                Qt.ConnectionType.QueuedConnection
            )

            self.download_thread = threading.Thread(target=self.downloader.pre_download, daemon=True)
            self.download_thread.start()
            self.downloader.finished.connect(lambda path: self.on_download_complete(path))

        except Exception as e:
            logging.error(f"提交失败: {str(e)}")
            self.update_button_state(True)

    def toggle_pause(self):
        if self.downloader:
            if self.is_paused_btn:
                self.pause_btn.setText('▶')
                self.downloader.pause()
                logging.info("下载已暂停")
            else:
                self.pause_btn.setText('||')
                self.downloader.resume()
                logging.info("下载继续")
            self.is_paused_btn = not self.is_paused_btn

    def stop_download(self):
        if self.downloader:
            self.downloader.progress_updated.disconnect()
            self.downloader.finished.disconnect()
            self.downloader.deleteLater()
            self.downloader = None
        self.update_button_state(True)
        logging.info("下载已停止")

    def update_type(self, text):
        logging.debug(f"更新内容：{text}")
        if TYPE_WORKER in text:
            logging.info("类型切换到画师")
            self.type_group.button(0).setChecked(True)
            self.type_group.button(1).setChecked(False)
        elif TYPE_ARTWORKS in text:
            logging.info("类型切换到作品")
            self.type_group.button(1).setChecked(True)
            self.type_group.button(0).setChecked(False)

    def update_button_state(self, enable):
        self.submit_btn.setEnabled(enable)
        self.is_stopped_btn = not enable
        self.is_paused_btn = not enable
        self.stop_btn.setEnabled(not enable)
        self.pause_btn.setEnabled(not enable)

    def on_download_complete(self, save_path):
        if self.open_check.isChecked() and os.path.exists(save_path):
            logging.info(f"正在打开下载目录")
            os.startfile(save_path)

        if self.exit_check.isChecked():
            logging.info("下载完成，程序即将退出...")
            QTimer.singleShot(1000, QApplication.instance().quit)

        self.update_button_state(True)

    def closeEvent(self, event):
        logging.debug("正在停止所有下载任务...")
        try:
            if self.downloader:
                self.downloader.stop_all_tasks()
                self.downloader.progress_updated.disconnect()
                self.downloader.finished.disconnect()
            if self.download_thread and self.download_thread.is_alive():
                self.download_thread.join(2)
            logging.getLogger().removeHandler(self.qt_handler)
        except Exception as e:
            logging.error(f"关闭时发生异常: {str(e)}")
        finally:
            QApplication.quit()

    def connect_signals(self):
        self.login_btn.clicked.connect(self.login_or_out)
        self.submit_btn.clicked.connect(self.submit_id)
        self.stop_btn.clicked.connect(self.stop_download)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.uid_input.textChanged.connect(self.update_type)
        self.update_ui.connect(self.update_button_state)
        self.qt_handler.log_signal.connect(self.qt_handler.handle_log_message)


if __name__ == '__main__':
    # import warnings
    # from urllib3.exceptions import InsecureRequestWarning

    # warnings.filterwarnings("ignore", category=InsecureRequestWarning)

    app = QApplication(sys.argv)
    window = PixivApp()
    log_init(window.qt_handler)

    window.show()
    sys.exit(app.exec())
