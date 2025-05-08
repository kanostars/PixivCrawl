import logging
import sys

from PyQt6.QtCore import pyqtSignal, Qt, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QCheckBox,
    QProgressBar, QTextEdit, QButtonGroup
)

from FileOrDirHandler import FileHandler
from LogHandler import log_init, QtLogHandler

TYPE_WORKER = "users"  # 类型是画师
TYPE_ARTWORKS = "artworks"  # 类型是插画
type_config = {
    0: TYPE_WORKER,  # 画师配置
    1: TYPE_ARTWORKS  # 插画配置
}

cookie_json = f'{FileHandler.read_json()["PHPSESSID"]}'


class PixivApp(QMainWindow):
    progress_updated = pyqtSignal(int, int)

    def __init__(self, qt_handler=None):
        super().__init__()
        self.init_ui()
        self.qt_handler = QtLogHandler(self.log_text) if qt_handler is None else qt_handler
        self.isLogin = False
        self.is_stopped = False
        self.is_paused = False
        self.connect_signals()

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle('pixiv下载器')
        self.setFixedSize(430, 570)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 15, 20, 15)  # 四周留白

        # 顶部图片区域
        # img_label = QLabel()
        # pixmap = QPixmap(FileHandler.resource_path('img\\92260993.png'))
        # img_label.setPixmap(pixmap.scaled(800, 200, Qt.AspectRatioMode.KeepAspectRatio))
        # layout.addWidget(img_label)

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
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                height: 10px;
                background: #F0F0F0;  
                border: 2px solid #C0C0C0;  
                border-radius: 4px;  
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;  
                width: 10px;
            }
        """)

        self.progress_label = QLabel("0%")
        self.progress_label.setContentsMargins(10, 0, 0, 0)
        self.stop_btn = QPushButton("X")
        self.stop_btn.setStyleSheet("background-color: red;")
        self.stop_btn.setFixedSize(30, 30)  # 新增固定尺寸
        self.pause_btn = QPushButton("||")
        self.pause_btn.setFixedSize(30, 30)  # 新增固定尺寸
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

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"{(current / total * 100):.2f}%")

    # 保留原有业务方法（需要适配PyQt6的信号槽机制）
    def login_or_out(self):
        # 需要重写为PyQt6实现...
        pass

    def submit_id(self):
        # 需要重写为PyQt6实现...
        pass

    def update_type(self, text):
        logging.debug(f"更新内容：{text}")
        if TYPE_WORKER in text:
            self.type_group.button(0).setChecked(True)
        elif TYPE_ARTWORKS in text:
            self.type_group.button(1).setChecked(True)

    def connect_signals(self):
        self.login_btn.clicked.connect(self.login_or_out)
        self.submit_btn.clicked.connect(self.submit_id)
        self.uid_input.textChanged.connect(self.update_type)
        self.progress_updated.connect(self.update_progress)
        self.qt_handler.log_signal.connect(self.qt_handler.handle_log_message)

    def closeEvent(self, event):
        logging.debug("程序已安全退出")
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PixivApp()
    log_init(window.qt_handler)

    window.show()
    sys.exit(app.exec())
