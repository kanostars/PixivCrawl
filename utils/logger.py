import logging
import os
from logging.handlers import RotatingFileHandler

from config.settings import (
    LOG_DIR, LOG_FORMAT, LOG_DATE_FORMAT, 
    LOG_MAX_BYTES, LOG_BACKUP_COUNT, ensure_directories
)


class TkinterLogHandler(logging.Handler):
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.configure_tags()

    def configure_tags(self):
        self.text_widget.tag_configure("DEBUG", foreground="blue")
        self.text_widget.tag_configure("INFO", foreground="black")
        self.text_widget.tag_configure("WARNING", foreground="#FF7608")
        self.text_widget.tag_configure("ERROR", foreground="red")
        self.text_widget.tag_configure("CRITICAL", foreground="purple")

    def emit(self, record):
        msg = self.format(record)
        log_level = record.levelname

        self.text_widget.configure(state='normal')
        self.text_widget.insert('end', msg + '\n', log_level)
        self.text_widget.see('end')
        self.text_widget.configure(state='disabled')


class LoggerManager:
    """日志管理器类"""
    
    def __init__(self, name: str = 'pixiv_downloader', 
                 log_file: str = None,
                 level: int = logging.INFO):
        self.name = name
        self.log_file = log_file
        self.level = level
        self.logger = None
        
    def setup(self) -> logging.Logger:
        """设置并返回日志记录器"""
        # 确保日志目录存在
        ensure_directories()
        
        # 创建日志记录器
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.level)
        
        # 避免重复添加处理器
        if self.logger.handlers:
            return self.logger
        
        # 创建格式化器
        formatter = logging.Formatter(
            LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT
        )
        
        # 添加控制台处理器
        self._add_console_handler(formatter)
        
        # 添加文件处理器
        self._add_file_handler(formatter)
        
        return self.logger
    
    def _add_console_handler(self, formatter: logging.Formatter):
        """添加控制台处理器"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def _add_file_handler(self, formatter: logging.Formatter):
        """添加文件处理器"""
        if self.log_file is None:
            self.log_file = os.path.join(LOG_DIR, f'{self.name}.log')
        
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(self.level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def get_logger(self) -> logging.Logger:
        """获取日志记录器"""
        if self.logger is None:
            return self.setup()
        return self.logger


def setup_logger(name: str = 'pixiv_downloader', 
                 log_file: str = None,
                 level: int = logging.INFO) -> logging.Logger:
    manager = LoggerManager(name, log_file, level)
    return manager.setup()
