import logging
import os
from logging.handlers import TimedRotatingFileHandler

import file_handler


# 创建日志输出
class TkinterLogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget  # 保存Text控件作为日志输出目标
        self.configure_tags()

    def configure_tags(self):
        # 定义不同日志级别的样式
        self.text_widget.tag_configure("DEBUG", foreground="blue")
        self.text_widget.tag_configure("INFO", foreground="black")
        self.text_widget.tag_configure("WARNING", foreground="#FF7608")
        self.text_widget.tag_configure("ERROR", foreground="red")
        self.text_widget.tag_configure("CRITICAL", foreground="purple")

    def emit(self, record):
        msg = self.format(record)
        log_level = record.levelname  # 获取日志级别

        self.text_widget.configure(state='normal')
        self.text_widget.insert('end', msg + '\n', log_level)  # 使用日志级别作为标签
        self.text_widget.see('end')
        self.text_widget.configure(state='disabled')


# 初始化日志
def log_init(app):
    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    log_format = "%(asctime)s - %(levelname)s - %(message)s"

    # 创建文件处理器，将日志写入文件
    mkdir_log = file_handler.create_directory("log")
    log_file_handler = TimedRotatingFileHandler(os.path.join(mkdir_log, 'my.log'),
                                                when='midnight', interval=1, backupCount=7, encoding='utf-8')
    log_file_handler.setFormatter(logging.Formatter(log_format))
    log_file_handler.setLevel(logging.DEBUG)

    # 创建Tkinter日志处理器
    tkinter_handler = TkinterLogHandler(app.log_text)
    tkinter_handler.setFormatter(logging.Formatter(log_format))
    tkinter_handler.setLevel(logging.INFO)

    # 添加处理器到日志记录器
    logger.addHandler(log_file_handler)
    logger.addHandler(tkinter_handler)
