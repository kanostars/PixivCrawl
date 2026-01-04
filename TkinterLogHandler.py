import logging


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
        self.text_widget.insert('end', msg + '\n', log_level)
        self.text_widget.see('end')
        self.text_widget.configure(state='disabled')
