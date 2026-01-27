import logging
import os
import argparse
import threading
import time
import webbrowser
from logging.handlers import TimedRotatingFileHandler
from tkinter import *
from tkinter import ttk
from tkinter.ttk import Progressbar

import requests
from urllib3 import disable_warnings

from FileOrDirHandler import FileHandler
from PixivDownloader import ThroughId, get_username, get_page_content
from TkinterLogHandler import TkinterLogHandler
from config import TYPE_WORKER, TYPE_ARTWORKS, type_config, cookies

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

disable_warnings()

cookie_json = cookies.replace('PHPSESSID=', '')


def thread_it(func, *t_args):
    thread = threading.Thread(target=func, args=t_args)
    thread.daemon = True
    thread.start()


# 初始化日志
def log_init():
    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # 创建文件处理器，将日志写入文件
    mkdirLog = FileHandler.create_directory("log")
    file_handler = TimedRotatingFileHandler(os.path.join(mkdirLog, 'my.log'),
                                            when='midnight', interval=1, backupCount=7, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(logging.DEBUG)

    # 创建Tkinter日志处理器
    tkinter_handler = TkinterLogHandler(app.log_text)
    tkinter_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    tkinter_handler.setLevel(logging.INFO)

    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(tkinter_handler)


# 应用界面框
class PixivApp:
    def __init__(self, root_app):
        self.isLogin = False
        self.is_stopped_btn = False
        self.is_paused_btn = False
        self.root = root_app
        self.root.geometry('430x570+400+50')
        self.root.title('pixiv下载器')
        img_path = FileHandler.resource_path('img\\cover.png')
        self.root.img = PhotoImage(file=img_path)
        self.log_text = ''
        self.total_progress = 0
        self.current_progress = 0
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.downloader = None
        self.button_submit = None
        self.process_text = None
        self.btn_pause = None
        self.btn_stop = None
        self.cookie = None
        self.username = None
        self.progress_bar = {}
        self.input_var_UID = StringVar()  # 接受链接/uid
        self.input_var_UID.trace("w", self.update_content)
        self.is_space_visit = BooleanVar()  # 是否查看画师主页
        self.is_finish_exit = BooleanVar()  # 是否下载完退出
        self.is_open_dir = BooleanVar()  # 是否下载完打开目录
        self.type = IntVar()  # 画师类型  0: 画师  1: 插画
        self.welcome = StringVar()  # 欢迎语
        self.login_btn_text = StringVar()
        self.login_btn_text.set("登录")
        self.welcome.set("欢迎，登录可以下载更多图片！")
        # 创建控件
        self.create_widgets()
        self.root.after(100, lambda: thread_it(self.is_login_by_name))
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # 锁定窗口大小
        # self.root.resizable(False, False)

    def create_widgets(self):
        # 图片框
        label_img = Label(self.root, image=self.root.img, width=800, height=200)
        label_img.pack(fill='both')

        # 登录
        login_frame = LabelFrame(self.root)
        login_btn = Button(login_frame, textvariable=self.login_btn_text, font=('黑体', 12), command=self.login_or_out,
                           width=15, relief='groove',
                           compound='center')
        login_welcome = Label(login_frame, textvariable=self.welcome, font=('黑体', 12))
        login_welcome.pack(side='left', padx=5)
        login_btn.pack(side='right')
        login_frame.pack(fill='both', pady=(0, 5))

        # 键入uid
        input_frame = LabelFrame(self.root)
        label_input = Label(input_frame, text='请输入链接/UID:', font=('黑体', 10))
        entry = Entry(input_frame, width=50, relief='flat', textvariable=self.input_var_UID)
        type_btn1 = Radiobutton(input_frame, text='画师', font=('宋体', 10), height=2, variable=self.type, value=0)
        type_btn2 = Radiobutton(input_frame, text='插画', font=('宋体', 10), height=2, variable=self.type, value=1)
        type_btn2.pack(side='right', padx=5)
        type_btn1.pack(side='right', padx=5)
        label_input.pack(side='left')
        entry.pack(side='left', fill='both')
        input_frame.pack(fill='both', pady=(0, 5))

        # 跳转空间
        choose_frame = LabelFrame(self.root)
        goto_btn = Checkbutton(choose_frame, text='跳转空间', font=('黑体', 10),
                               height=2, variable=self.is_space_visit)
        open_btn = Checkbutton(choose_frame, text='下载后打开', font=('黑体', 10),
                               height=2, variable=self.is_open_dir)
        quit_btn = Checkbutton(choose_frame, text='下载后退出', font=('黑体', 10),
                               height=2, variable=self.is_finish_exit)
        goto_btn.pack(side='left', padx=15)
        quit_btn.pack(side='left', anchor='center', expand=True)
        open_btn.pack(side='right', padx=15)
        choose_frame.pack(fill='both', pady=(0, 5))
        self.is_space_visit.set(False)
        self.is_open_dir.set(True)
        self.is_finish_exit.set(False)

        # 提交按钮
        self.button_submit = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound='center',
                                    bg='lavender', height=2, command=lambda: thread_it(self.submit_id))
        self.button_submit.pack(fill='both', anchor="n")

        # 进度条显示区域
        process_frame = Frame(self.root)
        # 创建样式对象
        self.style.configure("Custom.Horizontal.TProgressbar", troughcolor='white', background='lightblue',
                             bordercolor='gray')
        self.progress_bar = Progressbar(process_frame, orient='horizontal', mode='determinate',
                                        length=550, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.config()
        self.process_text = Label(process_frame, text='0%')
        self.btn_stop = Button(process_frame, text=' X ', font=('黑体', 11), background="red", foreground="white",
                               command=lambda: thread_it(self.stop_download))
        self.btn_pause = Button(process_frame, text=' ▶ ', font=('黑体', 11),
                                command=lambda: thread_it(self.toggle_pause))
        self.btn_stop.config(state='disabled')
        self.btn_pause.config(state='disabled')
        process_frame.pack(fill='both')
        self.btn_pause.pack(side='right')
        self.btn_stop.pack(side='right', padx=5)
        self.process_text.pack(side='left', padx=10)
        self.progress_bar.pack(side='left', padx=2)

        # 日志显示区域
        self.log_text = Text(self.root, height=10)
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.insert('1.0',  # 插入默认日志信息
                             '欢迎使用 PIXIV 图片下载器 ！\n'
                             '登录以下载更多图片，失效时再重新登录。\n')
        self.log_text.config(state='disabled')  # 禁用编辑功能
        self.log_text.pack(fill='both', expand=True)

    # 登录
    def login_or_out(self):
        try:
            global cookie_json
            if not self.isLogin:
                service = Service(executable_path=ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service)
                driver.get('https://accounts.pixiv.net/login?lang=zh&source=pc&view_type=page')
                WebDriverWait(driver, 300).until(
                    EC.url_contains("www.pixiv.net")  # 检查目标URL包含的关键字
                )
                # 获取最终跳转后的URL
                for cookie in driver.get_cookies():
                    if cookie['name'] == 'PHPSESSID':
                        self.cookie = cookie['value']
                        logging.debug(f'用户登录获得的cookie: {self.cookie}')

                        self.username = get_username(driver.page_source)

                        logging.info(f"用户{self.username}已登录~")
                        self.welcome.set(f'你好，{self.username}！')
                        self.login_btn_text.set("退出登录")
                        self.isLogin = True
                        driver.close()
                        break
                cookie_temp = self.cookie if self.cookie else cookie_json

                # 更新cookie
                if cookie_temp != cookie_json and cookie_temp is not None:
                    FileHandler.update_json(cookie_temp)
                    logging.debug(f"PHPSESSID已更新为：{cookie_temp}")

            else:
                logging.info(f"已成功退出")
                self.isLogin = False
                FileHandler.update_json("")
                self.login_btn_text.set("登录")
                self.welcome.set("欢迎，登录可以下载更多图片！")


        except Exception as e:
            logging.debug(f"登录失败，错误信息：{e}")
            logging.info("已取消登录")

    def is_login_by_name(self):
        logging.info("正在获取用户信息。。。")
        username = get_username(get_page_content())
        if username:
            self.login_btn_text.set("退出登录")
            self.welcome.set(f"你好，{username}！")
            self.isLogin = True
            logging.info(f'{username}已登录。')
        else:
            self.isLogin = False

    # 提交id
    def submit_id(self):
        try:
            # 初始化状态
            self.is_paused_btn = False
            self.is_stopped_btn = False
            self.btn_pause.config(text=' ⏸ ')

            # 防止用户在处理期间进行交互
            self.button_submit.config(state=DISABLED)

            # 解锁暂停和停止按钮
            self.btn_stop.config(state=NORMAL)
            self.btn_pause.config(state=NORMAL)

            input_UID = self.input_var_UID.get()
            if input_UID == '':
                logging.warning('输入的画师id不能为空~~')
                return

            type = type_config[self.type.get()]

            parts = input_UID.split(f'/{type}/')
            input_UID = parts[-1].split('/')[0] if parts else input_UID
            parts = input_UID.split('?')
            input_UID = parts[0] if parts else input_UID

            if self.is_space_visit.get():
                logging.info(f"正在跳转空间,{self.input_var_UID.get()}")
                webbrowser.open(f"https://www.pixiv.net/{type}/{input_UID}")

            self.downloader = ThroughId(input_UID, app, type)
            already_path = self.downloader.pre_download()

            if already_path and self.is_open_dir.get():
                logging.debug(f"下载完后打开文件夹")
                os.startfile(already_path)
            if if_exit_finish or self.is_finish_exit.get():
                logging.info("程序即将自动退出~")
                time.sleep(3)
                root.destroy()
        except requests.exceptions.ConnectTimeout:
            logging.warning("网络请求失败，用加速器试试~")
        except requests.exceptions.RequestException as e:
            logging.warning(f"网络请求失败: {e}")
        finally:
            self.button_submit.config(state=NORMAL)
            self.btn_stop.config(state=DISABLED)
            self.btn_pause.config(state=DISABLED)

    # 更新输入框
    def update_content(self, *_):
        input_text = self.input_var_UID.get()
        logging.debug(f"update_content, 输入的id为：{input_text}")
        if TYPE_WORKER in input_text:
            self.type.set(0)
        elif TYPE_ARTWORKS in input_text:
            self.type.set(1)

    # 更新进度条
    def update_progress_bar(self, increment, total=0):
        if total:  # 设置进度条最大值
            self.total_progress = total
            self.progress_bar["maximum"] = total
            self.current_progress = 0
        else:  # 更新进度条值
            self.current_progress += increment
        self.progress_bar["value"] = self.current_progress
        self.progress_bar.update()  # 刷新UI显示

        # 更新文本显示
        self.process_text.config(text=f"{(self.current_progress / self.total_progress * 100):.2f}%")
        self.root.update_idletasks()

    def update_progress_bar_color(self, color):
        self.style.configure("Custom.Horizontal.TProgressbar", background=color)

    # 暂停下载
    def toggle_pause(self):
        self.is_paused_btn = not self.is_paused_btn
        if self.downloader:
            if self.is_paused_btn:
                self.btn_pause.config(text=' ▶ ')
                self.downloader.is_paused.set()
                self.downloader.reset_session()
                logging.info("操作已暂停")
            else:
                self.btn_pause.config(text=' ⏸ ')
                self.downloader.is_paused.clear()
                logging.info("操作继续")

    # 停止下载
    def stop_download(self):
        if self.downloader:
            self.is_stopped_btn = True
            self.downloader.stop_all_tasks()
            self.downloader = None
            self.button_submit.config(state=NORMAL)
            self.btn_stop.config(state=DISABLED)
            self.btn_pause.config(state=DISABLED)
            self.update_progress_bar(0, 1)
            logging.info("已停止下载")

    # 窗口关闭
    def on_closing(self):
        logging.debug("窗口关闭，正在停止所有下载任务...")
        self.stop_download()
        self.root.destroy()


if __name__ == '__main__':
    root = Tk()
    app = PixivApp(root)

    log_init()  # 日志初始化

    is_start_now = False
    if_exit_finish = False

    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '-work', help='画师ID')
    parser.add_argument('-a', '-artwork', help='作品ID')
    parser.add_argument('-cookie', help='cookie')
    parser.add_argument('-sn', '-start-now', action='store_true', help='是否立即开始下载')
    parser.add_argument('-ef', '-exit-finish', action='store_true', help='程序结束时自动退出')

    args = parser.parse_args()

    if args.a and args.w:
        logging.warning("一个一个来~")
        exit(1)

    # 命令行参数解析
    if args.w:
        logging.debug(f"浏览器获取的画师ID为：{args.w}")
    elif args.a:
        logging.debug(f"浏览器获取的作品ID为：{args.a}")
    elif args.cookie:
        args.cookie = args.cookie.replace("PHPSESSID=", "")
        logging.debug(f"浏览器获取的cookie为：{args.cookie}")

    is_start_now = args.sn
    if_exit_finish = args.ef

    if args.w or args.a:
        target_id = args.w if args.w else args.a
        app.type.set(0 if args.w else 1)  # 切换类型
        app.input_var_UID.set(target_id)
        # 更新cookie
        if args.cookie != cookie_json and args.cookie is not None:
            FileHandler.update_json(args.cookie)
            logging.debug(f"PHPSESSID已更新为：{args.cookie}")

        if is_start_now:
            app.button_submit.invoke()

    root.mainloop()
