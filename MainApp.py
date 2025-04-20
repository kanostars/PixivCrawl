import ctypes
import logging
import os
import sys
import argparse
import threading
import time
import webbrowser
import winreg
import re
from logging.handlers import TimedRotatingFileHandler
from tkinter import *
from tkinter import ttk
from tkinter.ttk import Progressbar

import requests
from urllib3 import disable_warnings

from FileOrDirHandler import FileHandler
from PixivDownloader import ThroughId, get_username
from TkinterLogHandler import TkinterLogHandler

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

disable_warnings()

TYPE_WORKER = "users"  # 类型是画师
TYPE_ARTWORKS = "artworks"  # 类型是插画
type_config = {
    0: TYPE_WORKER,  # 画师配置
    1: TYPE_ARTWORKS  # 插画配置
}

cookie_json = f'{FileHandler.read_json()["PHPSESSID"]}'


def thread_it(func, *args):
    thread = threading.Thread(target=func, args=args)
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


# 创建注册表键
def check_registry_key_exists(key_path):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        logging.warning("请以管理员权限运行本程序")
        return
    try:
        # 尝试打开注册表键
        root_key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path)
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path + "\\shell\\open\\command")
        winreg.DeleteKey(key, "")
        winreg.CloseKey(key)
        key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path + "\\shell\\open\\command")
    except FileNotFoundError:
        # 创建注册表键
        logging.info("注册表键不存在，创建中...")
        root_key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path)
        key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path + "\\shell\\open\\command")
        winreg.SetValueEx(root_key, "URL Protocol", 0, winreg.REG_SZ, "")
    path = f'"{os.path.abspath(sys.argv[0])}" --url "%1"'
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, path)
    winreg.CloseKey(root_key)
    winreg.CloseKey(key)


# 应用界面框
class PixivApp:
    def __init__(self, root_app):
        self.downloader = None
        self.isLogin = False
        self.is_stopped_btn = False
        self.is_paused_btn = False
        self.root = root_app
        self.root.geometry('700x600+400+5')
        self.root.title('pixiv下载器')
        img_path = FileHandler.resource_path('img\\92260993.png')
        self.root.img = PhotoImage(file=img_path)
        self.log_text = ''
        self.total_progress = 0
        self.current_progress = 0
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.button_submit = None
        self.process_text = None
        self.btn_pause = None
        self.btn_stop = None
        self.cookie = None
        self.username = None
        self.progress_bar = {}
        self.input_var_UID = StringVar()  # 接受链接/uid
        self.input_var_UID.trace("w", self.update_content)
        self.space_visit = BooleanVar()  # 是否查看画师主页
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

    def create_widgets(self):
        # 图片框
        label_img = Label(self.root, image=self.root.img, width=800, height=200)
        label_img.pack(fill='both')

        # 登录
        login_frame = LabelFrame(self.root)
        login_btn = Button(login_frame, textvariable=self.login_btn_text, font=('黑体', 15), command=self.login_or_out,
                           width=40, relief='groove',
                           compound='center')
        login_welcome = Label(login_frame, textvariable=self.welcome, font=('黑体', 12))
        login_welcome.pack(side='left', padx=5)
        login_btn.pack(side='right')
        login_frame.pack(fill='both', pady=(0, 5))

        # 键入uid
        input_frame = LabelFrame(self.root)
        label_input = Label(input_frame, text='请输入链接/UID:', font=('黑体', 18))
        entry = Entry(input_frame, width=40, relief='flat', textvariable=self.input_var_UID)
        type_btn1 = Radiobutton(input_frame, text='画师', font=('宋体', 10), height=1, variable=self.type, value=0)
        type_btn2 = Radiobutton(input_frame, text='插画', font=('宋体', 10), height=1, variable=self.type, value=1)
        label_type = Label(input_frame, text='作品类型:', font=('黑体', 12))
        type_btn2.pack(side='right', padx=5)
        type_btn1.pack(side='right', padx=5)
        label_input.pack(side='left')
        entry.pack(side='left', fill='both')
        label_type.pack(side='right', padx=10)
        input_frame.pack(fill='both', pady=(0, 5))

        # 跳转空间
        choose_frame = LabelFrame(self.root)
        label = Label(choose_frame, text='要去空间看看吗？', font=('黑体', 12))

        space_btn1 = Radiobutton(choose_frame, text='是的，我要康', font=('宋体', 11), variable=self.space_visit,
                                 value=True, height=2)
        space_btn2 = Radiobutton(choose_frame, text='不用了，懒得点', font=('宋体', 11), variable=self.space_visit,
                                 value=False, height=2)
        self.space_visit.set(False)
        label.pack(side='left')
        space_btn2.pack(side='left', padx=20)
        space_btn1.pack(side='left', padx=20)

        choose_frame.pack(fill='both', pady=(0, 5))

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
                             '登录以下载更多图片，失效时再重新登录。\n'
                             '---------------------------------------------------------------------------------------------------\n')
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
                        div_text = driver.find_element(By.CSS_SELECTOR, 'div.jePfsr').get_attribute('outerHTML')
                        self.username = re.search(r'<div class="sc-4bc73760-3 jePfsr">(.*?)</div>', div_text).group(1)
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
        username = get_username()
        if username:
            self.login_btn_text.set("退出登录")
            self.welcome.set(f"你好，{username}！")
            self.isLogin = True
            logging.info(f'{username}已登录。')
        else:
            self.isLogin = False

    # 是否查看网页
    def is_visit_space(self):
        return self.space_visit.get()

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

            if self.is_visit_space():
                webbrowser.open(f"https://www.pixiv.net/{type}/{input_UID}")

            self.downloader = ThroughId(input_UID, app, type)
            self.downloader.pre_download()

            if if_exit_finish:
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

    def update_content(self, *args):
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
    check_registry_key_exists(r"pixivdownload")

    is_start_now = False
    if_exit_finish = False

    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '-work',  help='画师ID')
    parser.add_argument('-a', '-artwork', help='作品ID')
    parser.add_argument('-cookie', help='cookie')
    parser.add_argument('-sn', '-start-now',  action='store_true', help='是否立即开始下载')
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
