import ctypes
import logging
import os
import sys
import threading
import time
import webbrowser
import winreg
from logging.handlers import TimedRotatingFileHandler
from tkinter import *
from tkinter.ttk import Progressbar

import requests
import urllib3

from FileOrDirHandler import FileHandler
from PixivDownloader import ThroughId
from TkinterLogHandler import TkinterLogHandler

urllib3.disable_warnings()

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画
cookie = ''

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
    path = f'"{os.path.abspath(sys.argv[0])}" "%1"'
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, path)
    winreg.CloseKey(root_key)
    winreg.CloseKey(key)

# 应用界面框
class PixivApp:
    def __init__(self, root_app):
        self.root = root_app
        self.root.geometry('700x700+400+5')
        self.root.title('pixiv下载器')
        img_path = FileHandler.resource_path('img\\92260993.png')
        self.root.img = PhotoImage(file=img_path)
        self.log_text = ''
        self.total_progress = 0
        self.current_progress = 0
        self.button_artist = None
        self.button_artwork = None
        self.process_text = None
        self.progress_bar = {}
        self.input_var_worker = StringVar()  # 接受画师uid
        self.input_var_artwork = StringVar()  # 接受作品uid
        self.inputCookie_var = StringVar()  # 接受登陆后的cookie
        self.b_users = BooleanVar()  # 是否查看画师主页
        self.b_artworks = BooleanVar()  # 是否查看作品网页

        # 创建控件
        self.create_widgets()

    def create_widgets(self):
        # 图片框
        label_img = Label(self.root, image=self.root.img, width=800, height=200)
        label_img.pack(fill='both')

        # 键入cookie
        message_cookie = LabelFrame(self.root)
        message_cookie.pack(fill='both', pady=(0, 10), anchor="n")
        cookie_label = Label(message_cookie, text='请输入PHPSESSID(可选):', font=('黑体', 15))
        cookie_label.pack(side=LEFT, pady=5)
        entry_cookie = Entry(message_cookie, width=95, relief='flat', textvariable=self.inputCookie_var)
        entry_cookie.pack(side=LEFT, fill='both')

        # 键入画师uid
        input_frame1 = LabelFrame(self.root)
        input_frame1.pack(fill='both')
        choose_frame1 = LabelFrame(self.root)
        choose_frame1.pack(fill='both')
        label1 = Label(choose_frame1, text='是否显示画师空间:', font=('黑体', 20))
        label1.pack(side=LEFT)
        radiobutton1 = Radiobutton(choose_frame1, text='是的，我要康', font=('宋体', 11), variable=self.b_users,
                                   value=True, height=2)
        radiobutton1.pack(side=LEFT, padx=20)
        radiobutton2 = Radiobutton(choose_frame1, text='不用了，懒得点', font=('宋体', 11), variable=self.b_users,
                                   value=False, height=2)
        radiobutton2.pack(side=LEFT, padx=20)
        self.b_users.set(False)
        self.button_artist = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                                    bg='lavender', height=2, command=lambda: thread_it(self.submit_id, TYPE_WORKER))
        self.button_artist.pack(fill='both', pady=(0, 10), anchor="n")
        label_input1 = Label(input_frame1, text='请输入画师uid:', font=('黑体', 20))
        label_input1.pack(side=LEFT)
        entry1 = Entry(input_frame1, width=95, relief='flat', textvariable=self.input_var_worker)
        entry1.pack(side=LEFT, fill='both')

        # 键入作品uid
        input_frame2 = LabelFrame(self.root)
        input_frame2.pack(fill='both')
        choose_frame2 = LabelFrame(self.root)
        choose_frame2.pack(fill='both')
        label2 = Label(choose_frame2, text='是否显示插画原网站:', font=('黑体', 20))
        label2.pack(side=LEFT)
        radiobutton3 = Radiobutton(choose_frame2, text='是的，我要康', font=('宋体', 11), variable=self.b_artworks,
                                   value=True, height=2)
        radiobutton3.pack(side=LEFT, padx=20)
        radiobutton4 = Radiobutton(choose_frame2, text='不用了，懒得点', font=('宋体', 11), variable=self.b_artworks,
                                   value=False, height=2)
        radiobutton4.pack(side=LEFT, padx=20)
        self.b_artworks.set(False)
        self.button_artwork = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                                     bg='lavender', height=2, command=lambda: thread_it(self.submit_id, TYPE_ARTWORKS))
        self.button_artwork.pack(fill='both', pady=(0, 0), anchor="n")
        label_input2 = Label(input_frame2, text='请输入图片uid:', font=('黑体', 20))
        label_input2.pack(side=LEFT)
        entry2 = Entry(input_frame2, width=95, relief='flat', textvariable=self.input_var_artwork)
        entry2.pack(side=LEFT, fill='both')

        # 进度条显示区域
        process_frame = Frame(self.root)
        process_frame.pack(fill='both')
        self.progress_bar = Progressbar(process_frame, orient='horizontal', mode='determinate',
                                        length=650, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.pack(side=LEFT)
        self.process_text = Label(process_frame, text='0%')
        self.process_text.pack(side=RIGHT)

        # 日志显示区域
        self.log_text = Text(self.root, height=10)
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.pack(fill='both', expand=True)
        self.log_text.insert('1.0',  # 插入默认日志信息
                             '欢迎使用 PIXIV 图片下载器 ！\n'
                             '填写PHPSESSID以下载更多图片，可以再浏览器开发者工具中获取值，失效时再进行填写。\n'
                             '---------------------------------------------------------------------------------------------------\n')
        self.log_text.config(state='disabled')  # 禁用编辑功能

    # 是否查看画师主页
    def isWorkers(self):
        return self.b_users.get()

    # 是否查看插画原网站
    def isArtworks(self):
        return self.b_artworks.get()

    # 提交id
    def submit_id(self, t):
        try:
            # 防止用户在处理期间进行交互
            self.button_artist.config(state=DISABLED)
            self.button_artwork.config(state=DISABLED)

            # 读取json文件中的cookie
            cookie_json = f'{FileHandler.read_json()["PHPSESSID"]}'

            cookieID = self.inputCookie_var.get() if self.inputCookie_var.get() else cookie_json
            if cookie:
                cookieID = cookie

            # 更新cookie
            if cookieID != cookie_json and cookieID is not None:
                FileHandler.update_json(cookieID)
                logging.debug(f"PHPSESSID已更新为：{cookieID}")

            logging.debug(f'使用的PHPSESSID为：{cookieID}')

            if t == TYPE_WORKER:  # 画师
                workerId = self.input_var_worker.get()
                if workerId == '':
                    logging.warning('输入的画师id不能为空~~')
                    return
                if self.isWorkers():
                    webbrowser.open(f"https://www.pixiv.net/users/{workerId}")
                ThroughId(cookieID, workerId, app, TYPE_WORKER).pre_download()
            elif t == TYPE_ARTWORKS:  # 插画
                ImgId = self.input_var_artwork.get()
                if ImgId == '':
                    logging.warning('输入的插画id不能为空~~')
                    return
                if self.isArtworks():
                    webbrowser.open(f"https://www.pixiv.net/artworks/{ImgId}")
                ThroughId(cookieID, ImgId, app, TYPE_ARTWORKS).pre_download()
            if if_exit_finish:
                logging.info("程序即将自动退出~")
                time.sleep(3)
                root.destroy()
        except requests.exceptions.ConnectTimeout:
            logging.warning("网络请求失败，用加速器试试，提个醒，别用代理工具~")
        except requests.exceptions.RequestException as e:
            logging.warning(f"网络请求失败: {e}")
        finally:
            self.button_artist.config(state=NORMAL)
            self.button_artwork.config(state=NORMAL)

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


if __name__ == '__main__':
    root = Tk()
    app = PixivApp(root)

    log_init()  # 日志初始化
    check_registry_key_exists(r"pixivdownload")

    worker_id = None
    artwork_id = None
    is_start_now = False
    if_exit_finish = False
    args = sys.argv

    # 获取命令行参数
    if len(sys.argv) > 1:
        url_get = sys.argv[1]
        logging.debug(f"获取的参数为：{url_get}")
        if '/' in url_get:
            args = url_get.split('/')

    # 命令行参数解析
    for arg in args:
        if arg == "-worker-id":
            worker_id = args[args.index(arg) + 1]
            logging.debug(f"浏览器获取的画师ID为：{worker_id}")
        elif arg == "-artwork-id":
            artwork_id = args[args.index(arg) + 1]
            logging.debug(f"浏览器获取的作品ID为：{artwork_id}")
        elif arg == "-cookie":
            cookie = args[args.index(arg) + 1].replace("PHPSESSID=", "")
            logging.debug(f"浏览器获取的cookie为：{cookie}")
        elif arg == "--start-now":
            is_start_now = True
        elif arg == "--exit-finish":
            if_exit_finish = True

    if worker_id and artwork_id and is_start_now:
        logging.warning("一个一个来~")
        exit(1)

    if worker_id:
        app.input_var_worker.set(worker_id)
        if is_start_now:
            app.button_artist.invoke()

    if artwork_id:
        app.input_var_artwork.set(artwork_id)
        if is_start_now:
            app.button_artwork.invoke()

    root.mainloop()
