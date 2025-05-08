import logging
import os
from logging.handlers import TimedRotatingFileHandler
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QColor

from FileOrDirHandler import FileHandler

class QtLogHandler(QObject, logging.Handler):
    log_signal = pyqtSignal(str)

    def __init__(self, log_widget=None):
        super().__init__()
        self.log_widget = log_widget
        self.setFormatter(logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt='%m-%d %H:%M:%S'
        ))

    def handle_log_message(self, msg):
        if not self.log_widget:
            logging.error("handle_log_message方法错误，空指针异常")
            return
        format_mapping = {
            "DEBUG": self.create_text_format("blue"),
            "INFO": self.create_text_format("white"),
            "WARNING": self.create_text_format("#FF7608"),
            "ERROR": self.create_text_format("red"),
            "CRITICAL": self.create_text_format("purple")
        }

        log_level = "INFO"
        for level in format_mapping:
            if f"- {level} -" in msg:
                log_level = level
                break

        cursor = self.log_widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(msg.strip() + '\n', format_mapping[log_level])
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_widget.setTextCursor(cursor)

    def create_text_format(self, color):
        text_format = self.log_widget.currentCharFormat()
        text_format.setForeground(QColor(color))
        return text_format

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)


class FileLogHandler(TimedRotatingFileHandler):
    def __init__(self):
        # 创建日志目录
        log_dir = FileHandler.create_directory("log")
        log_path = os.path.join(log_dir, 'my.log')

        super().__init__(
            filename=log_path,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )

        self.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        self.setLevel(logging.DEBUG)


# 初始化日志
def log_init(qt_handler=None):
    logger = logging.getLogger()
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)

    logger.addHandler(FileLogHandler())
    if qt_handler:
        qt_handler.setLevel(logging.INFO)
        logger.addHandler(qt_handler)
