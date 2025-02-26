import ctypes
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from tkinter import ttk
from tkinter.ttk import Progressbar
import json
from bs4 import BeautifulSoup
import os
from tkinter import *
from tkinter import filedialog
from tkinter import messagebox
import webbrowser
import threading
import concurrent
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import zipfile
from PIL import Image
import winreg

import NoVPNConnect
from utils import *

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画

relative_base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
config = {}

default_data = {
    "cookie": "",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
}


# 创建文件夹
def create_directory(*base_dir):
    mkdir = os.path.join(relative_base_path, *base_dir)
    os.makedirs(mkdir, exist_ok=True)
    return mkdir


# 创建或更新文件，清空文件内容
def touch(file_path):
    with open(file_path, 'wb') as f:
        f.truncate(0)


# 获取资源文件的绝对路径
def resource_path(relative_path):
    # PyInstaller 临时文件夹
    base_path = getattr(sys, '_MEIPASS', None)
    if base_path is None:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 初始化日志
def log_init():
    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    log_format = "%(asctime)s - %(levelname)s - %(message)s"

    # 创建文件处理器，将日志写入文件
    mkdir_log = create_directory("log")
    file_handler = TimedRotatingFileHandler(os.path.join(mkdir_log, 'my.log'),
                                            when='midnight', interval=1, backupCount=7, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.DEBUG)

    # 创建Tkinter日志处理器
    tkinter_handler = TkinterLogHandler(app.log_text)
    tkinter_handler.setFormatter(logging.Formatter(log_format))
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


# 读取json文件
def read_json():
    json_file = os.path.join(relative_base_path, "pixivCrawl.json")
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'cookie' not in data:
                data['cookie'] = ''
            if 'user_agent' not in data:
                data['user_agent'] = default_data['user_agent']
            return data
    except FileNotFoundError:
        logging.info("未找到配置文件，正在创建默认配置文件。")
        with open(json_file, 'w', encoding='utf-8') as f:
            out = json.dumps(default_data, indent=4, ensure_ascii=False)
            f.write(out)
        return default_data


# 更新json文件
def update_json(data):
    json_file = os.path.join(relative_base_path, "pixivCrawl.json")

    with open(json_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=4))
    logging.info(f"成功更新配置文件")


# p站图片下载器
class PixivDownloader:
    def __init__(self, cookie_id, art_id, pixiv_app, t):
        self.id = art_id
        self.type = t
        self.app = pixiv_app
        self.artist = ""  # 画师名字
        self.dirs = ""  # 存放图片的文件夹
        self.numbers = 0  # 图片数量
        self.cookie = f'PHPSESSID={cookie_id}' if cookie_id else config['cookie']

        # 更新cookie
        if self.cookie and self.cookie != config['cookie']:
            config['cookie'] = self.cookie
            update_json(config)

        self.headers = {'Referer': "https://www.pixiv.net/",
                        'User-agent': config['user_agent'],
                        'Cookie': self.cookie,
                        'Accept-Transfer-Encoding': 'identity'}
        self.download_queue = []  # 下载队列
        self.downloading_resp = []
        self.need_com_gif = {}  # 需要合成的动图

    @log_it()
    def download_and_save_image(self, url, save_path):
        if self.app.is_stop:
            return
        while self.app.is_paused:
            time.sleep(0.5)
        resp = NoVPNConnect.connect(url, headers=self.headers)
        self.downloading_resp.append(resp)

        with open(save_path, 'rb+') as f:
            f.seek(0, 0)
            f.write(resp.content)

    def download_images(self, img_ids, t):
        try:
            self.type = t
            self.artist = self.get_worker_name(img_ids[0])
            if self.artist is None:
                return
            logging.info(f"画师名字: {self.artist}")
            if self.type == TYPE_WORKER:  # 类型是通过画师id
                logging.info(f"正在查找图片总数，图片id集为{len(img_ids)}个...")
                self.dirs = create_directory("workers_IMG", self.artist)
            elif self.type == TYPE_ARTWORKS:  # 类型是通过插画id
                self.dirs = create_directory("artworks_IMG", img_ids[0])

            self.download_by_art_worker_ids(img_ids)
            if self.app.is_stop:
                logging.info('用户停止下载')
                return
            while self.app.is_paused:
                time.sleep(0.5)

            logging.info(f"检索结束...")
            if self.numbers == 0:
                logging.warning("PHPSESSID已失效，请重新填写!")
                return

            logging.info(f"正在开始下载... 共{self.numbers}张图片...")
            self.app.update_progress_bar(0, len(self.download_queue))
            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 64)) as executor:
                futures = []
                executor.submit(self.download_progress_updater)
                try:
                    for (url, save_path) in self.download_queue:
                        logging.debug(f"{url} {save_path}")
                        f = executor.submit(self.download_and_save_image, url, save_path)
                        futures.append(f)
                    done, not_done = concurrent.futures.wait(
                        futures,
                        return_when=concurrent.futures.FIRST_EXCEPTION
                    )
                    for future in done:
                        future.result()  # 这里会立即抛出第一个异常
                    for future in not_done:
                        future.cancel()  # 取消未完成的任务
                    concurrent.futures.wait(not_done)  # 等待取消完成
                except Exception as e:
                    executor.shutdown(wait=False)
                    raise e

            if len(self.need_com_gif) > 0:
                logging.info(f"开始合成动图，数量:{len(self.need_com_gif)}")
                self.app.update_progress_bar(0, len(self.need_com_gif))
                com_count = 0
                for img_id in self.need_com_gif:
                    if self.app.is_stop:
                        logging.info('用户停止下载')
                        return
                    if self.app.is_paused:
                        time.sleep(0.5)
                        continue
                    self.comp_gif(img_id)
                    com_count += 1
                    self.app.update_progress_bar(com_count, len(self.need_com_gif))

            logging.info(f"下载完成，文件夹内共有{len(os.listdir(self.dirs))}张图片~")
            logging.info(f"存放路径：{os.path.abspath(self.dirs)}")
            os.startfile(self.dirs)
            if if_exit_finish:
                logging.info("程序即将自动退出~")
                time.sleep(3)
                root.destroy()

        except IndexError:
            logging.warning("未找到该画师,请重新输入~")

    def download_progress_updater(self):
        while True:
            if self.app.is_stop:
                for resp in self.downloading_resp:
                    resp.stop()
                break
            if self.app.is_paused:
                time.sleep(0.5)
                continue
            f_download = 0
            for resp in self.downloading_resp:
                f_download += resp.get_content_progress()
            self.app.update_progress_bar(f_download, len(self.download_queue))
            if f_download >= len(self.download_queue):
                break

    def get_worker_name(self, img_id):
        artworks_id = f"https://www.pixiv.net/artworks/{img_id}"
        requests_worker = NoVPNConnect.connect(artworks_id, headers=self.headers)

        soup = BeautifulSoup(requests_worker.content, 'html.parser')

        meta_tag = str(soup.find_all('meta')[-1])
        # 获取画师名字
        worker_url = re.findall(f'"userName":"(.*?)"', meta_tag)
        if worker_url:
            return re.sub(r'[/\\| ]', '_', worker_url[0])
        logging.warning("未找到该画师,请重新输入~")
        return None

    def download_by_art_worker_ids(self, img_ids):
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 64)) as executor:
            futures = []
            for img_id in img_ids:
                f = executor.submit(self.download_by_art_worker_id, img_id)
                futures.append(f)
            # 等待所有下载任务完成
            while True:
                if self.app.is_stop:
                    for future in futures:
                        future.cancel()
                    break
                if self.app.is_paused:
                    time.sleep(0.5)
                    continue
                completed_count = 0
                for future in futures:
                    if future.done():
                        completed_count += 1
                self.app.update_progress_bar(completed_count, len(futures))
                if completed_count == len(futures):
                    break

    def download_by_art_worker_id(self, img_id):
        ugoira_url = f"https://www.pixiv.net/ajax/illust/{img_id}/ugoira_meta"

        response = NoVPNConnect.connect(ugoira_url, headers=self.headers)

        data = response.json
        if data['error']:  # 是静态图
            self.download_static_images(img_id)
        else:  # 是动图
            self.download_gifs(data, img_id)

    def download_static_images(self, img_id):
        response = NoVPNConnect.connect(url=f"https://www.pixiv.net/ajax/illust/{img_id}/pages", headers=self.headers)

        # 解析响应以获取所有静态图片的URL
        static_url = response.json['body']
        for urls in static_url:
            # 原始分辨率图片的URL
            url = urls['urls']['original']
            name = os.path.basename(url)
            file_path = os.path.join(self.dirs, f"@{self.artist} {name}")
            touch(file_path)

            self.add_download_queue(url, file_path)

    def download_gifs(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.dirs, name)
        touch(file_path)
        self.need_com_gif[img_id] = delays

        self.add_download_queue(url, file_path)

    def add_download_queue(self, url, file_path):
        self.numbers += 1
        self.download_queue.append((url, file_path))

    def comp_gif(self, img_id):
        delays = self.need_com_gif[img_id]
        name = f"@{self.artist} {img_id}.gif"
        o_name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.dirs, name)
        o_file_name = os.path.join(self.dirs, o_name)
        with zipfile.ZipFile(o_file_name, 'r') as zip_ref:
            image_files = [f for f in zip_ref.namelist() if f.endswith(('.png', '.jpg', '.jpeg'))]
            images = [Image.open(zip_ref.open(image_file)).convert('RGBA') for image_file in image_files]
        if images:
            images[0].save(
                file_path,
                save_all=True,
                append_images=images[1:],
                duration=delays,
                loop=0
            )
        os.remove(o_file_name)

    # 获取用户的所有作品id
    def get_img_ids(self):
        id_url = f"https://www.pixiv.net/ajax/user/{self.id}/profile/all?lang=zh"
        response = NoVPNConnect.connect(id_url, headers=self.headers)
        return re.findall(r'"(\d+)":null', response.text)

    def pre_download(self):
        if self.type == TYPE_ARTWORKS:
            logging.info(f"正在通过插画ID({self.id})检索图片...")
            self.download_images([self.id], self.type)
        elif self.type == TYPE_WORKER:
            logging.info(f"正在通过画师ID({self.id})检索图片...")
            img_ids = self.get_img_ids()
            self.download_images(img_ids, self.type)


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


# 应用界面框
class PixivApp:
    def __init__(self, root_app):
        self.root = root_app
        self.root.geometry('700x750')
        self.root.title('pixiv下载器')
        img_path = resource_path('img\\92260993.png')
        self.root.img = PhotoImage(file=img_path)

        # 组件
        self.label_img = None
        self.browser_frame = None
        self.browser_label = None
        self.browser_input = None
        self.browser_choose = None
        self.browser_button = None
        self.browser_alarm = None
        self.message_cookie = None
        self.cookie_label = None
        self.entry_cookie = None
        self.input_frame1 = None
        self.choose_frame1 = None
        self.label1 = None
        self.radiobutton1 = None
        self.radiobutton2 = None
        self.button_artist = None
        self.label_input1 = None
        self.entry1 = None
        self.input_frame2 = None
        self.choose_frame2 = None
        self.label2 = None
        self.radiobutton3 = None
        self.radiobutton4 = None
        self.button_artwork = None
        self.label_input2 = None
        self.entry2 = None
        self.process_frame = None
        self.process_text = None
        self.btn_stop = None
        self.btn_pause = None

        # 基础变量
        self.log_text = ''
        self.total_progress = 0
        self.current_progress = 0
        self.is_stop = False
        self.is_paused = False

        # 高级变量
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.progress_bar = {}
        self.input_var_worker = StringVar()  # 接受画师uid
        self.input_var_artwork = StringVar()  # 接受作品uid
        self.inputCookie_var = StringVar()  # 接受登陆后的cookie
        self.browser_path = StringVar() # 浏览器路径
        if config.get('browser_path'):
            self.browser_path.set(config.get('browser_path'))
        self.b_users = BooleanVar()  # 是否查看画师主页
        self.b_artworks = BooleanVar()  # 是否查看作品网页

        # 创建控件
        self.create_widgets()

        self.pack_widgets()

    def create_widgets(self):
        # 图片框
        self.label_img = Label(self.root, image=self.root.img, width=800, height=200)

        # 打开浏览器
        self.browser_frame = LabelFrame(self.root)
        self.browser_label = Label(self.browser_frame, text='浏览器位置：', font=('黑体', 15))
        self.browser_input = Entry(self.browser_frame, textvariable=self.browser_path)
        self.browser_choose = Button(self.browser_frame, pady=-10, text='...', command=self.choose_browser_path)
        self.browser_button = Button(self.browser_frame, text='打开pixiv', command=self.open_browser)
        self.browser_alarm = Label(self.browser_frame, text='警告：启动浏览器前将会关闭正在运行的浏览器')

        # 键入cookie
        self.message_cookie = LabelFrame(self.root)
        self.cookie_label = Label(self.message_cookie, text='请输入PHPSESSID(可选):', font=('黑体', 15))
        self.entry_cookie = Entry(self.message_cookie, width=95, relief='flat', textvariable=self.inputCookie_var)

        # 键入画师uid
        self.input_frame1 = LabelFrame(self.root)
        self.choose_frame1 = LabelFrame(self.root)
        self.label1 = Label(self.choose_frame1, text='是否显示画师空间:', font=('黑体', 20))
        self.radiobutton1 = Radiobutton(self.choose_frame1, text='是的，我要康', font=('宋体', 11), variable=self.b_users,
                                   value=True, height=2)
        self.radiobutton2 = Radiobutton(self.choose_frame1, text='不用了，懒得点', font=('宋体', 11), variable=self.b_users,
                                   value=False, height=2)
        self.b_users.set(False)
        self.button_artist = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                                    bg='lavender', height=2, command=lambda: self.submit_id(TYPE_WORKER))
        self.label_input1 = Label(self.input_frame1, text='请输入画师uid:', font=('黑体', 20))
        self.entry1 = Entry(self.input_frame1, width=95, relief='flat', textvariable=self.input_var_worker)

        # 键入作品uid
        self.input_frame2 = LabelFrame(self.root)
        self.choose_frame2 = LabelFrame(self.root)
        self.label2 = Label(self.choose_frame2, text='是否显示插画原网站:', font=('黑体', 20))
        self.radiobutton3 = Radiobutton(self.choose_frame2, text='是的，我要康', font=('宋体', 11), variable=self.b_artworks,
                                   value=True, height=2)
        self.radiobutton4 = Radiobutton(self.choose_frame2, text='不用了，懒得点', font=('宋体', 11), variable=self.b_artworks,
                                   value=False, height=2)
        self.b_artworks.set(False)
        self.button_artwork = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                                     bg='lavender', height=2, command=lambda: self.submit_id(TYPE_ARTWORKS))
        self.label_input2 = Label(self.input_frame2, text='请输入图片uid:', font=('黑体', 20))
        self.entry2 = Entry(self.input_frame2, width=95, relief='flat', textvariable=self.input_var_artwork)

        # 进度条显示区域
        self.process_frame = Frame(self.root)
        self.style.configure("Custom.Horizontal.TProgressbar", troughcolor='white', background='lightblue',
                             bordercolor='gray')
        self.progress_bar = Progressbar(self.process_frame, orient='horizontal', mode='determinate',
                                        length=580, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.config()

        self.process_text = Label(self.process_frame, text='0%')

        self.btn_stop = Button(self.process_frame, text=' X ', font=('黑体', 11), background="red", foreground="white",
                               command=self.stop_download)
        self.btn_pause = Button(self.process_frame, text=' ▶ ', font=('黑体', 11),
                                command=self.toggle_pause)

        self.btn_stop.config(state=DISABLED)
        self.btn_pause.config(state=DISABLED)

        # 日志显示区域
        self.log_text = Text(self.root, height=10)
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.insert('1.0',  # 插入默认日志信息
                             '欢迎使用 PIXIV 图片下载器 ！\n'
                             '填写PHPSESSID以下载更多图片，可以在浏览器开发者工具中获取值，失效时再进行填写。\n'
                             '---------------------------------------------------------------------------------------------------\n')
        self.log_text.config(state='disabled')  # 禁用编辑功能

    def pack_widgets(self):
        self.label_img.pack(fill='both')

        self.browser_frame.pack(fill='both', anchor='n')
        self.browser_label.pack(side=LEFT)
        self.browser_input.pack(side=LEFT)
        self.browser_choose.pack(side=LEFT)
        self.browser_button.pack(side=LEFT)
        self.browser_alarm.pack(side=LEFT)

        self.message_cookie.pack(fill='both', pady=(0, 10), anchor="n")
        self.cookie_label.pack(side=LEFT, pady=5)
        self.entry_cookie.pack(side=LEFT, fill='both')

        self.input_frame1.pack(fill='both')
        self.choose_frame1.pack(fill='both')
        self.label1.pack(side=LEFT)
        self.radiobutton1.pack(side=LEFT, padx=20)
        self.radiobutton2.pack(side=LEFT, padx=20)
        self.label_input1.pack(side=LEFT)
        self.button_artist.pack(fill='both', pady=(0, 10), anchor="n")
        self.entry1.pack(side=LEFT, fill='both')

        self.input_frame2.pack(fill='both')
        self.choose_frame2.pack(fill='both')
        self.label2.pack(side=LEFT)
        self.radiobutton3.pack(side=LEFT, padx=20)
        self.radiobutton4.pack(side=LEFT, padx=20)
        self.label_input2.pack(side=LEFT)
        self.button_artwork.pack(fill='both', pady=(0, 0), anchor="n")
        self.entry2.pack(side=LEFT, fill='both')

        self.process_frame.pack(fill='both')
        self.progress_bar.pack(side=LEFT)
        self.process_text.pack(side=LEFT)
        self.btn_stop.pack(side=RIGHT, padx=5)
        self.btn_pause.pack(side=RIGHT)

        self.log_text.pack(fill='both', expand=True)

    def choose_browser_path(self):
        self.browser_path.set(filedialog.askopenfilename(title="选择浏览器", filetypes=[("exe文件", "*.exe")]))

    def open_browser(self):
        result = messagebox.askokcancel("警告", "打开浏览器时会将正在运行的浏览器关闭！")
        if result:
            if (NoVPNConnect.open_pixiv(self.browser_path.get()) and
                    (not config.get('browser_path') or config.get('browser_path') != self.browser_path.get())):
                config['browser_path'] = self.browser_path.get()
                update_json(config)

    # 是否查看画师主页
    def is_workers(self):
        return self.b_users.get()

    # 是否查看插画原网站
    def is_artworks(self):
        return self.b_artworks.get()

    # 提交id
    @thread_it
    def submit_id(self, t):
        # 防止用户在处理期间进行交互
        self.button_artist.config(state=DISABLED)
        self.button_artwork.config(state=DISABLED)

        self.btn_pause.config(text=' ⏸ ')

        # 允许点击暂停和停止按钮
        self.btn_pause.config(state=NORMAL)
        self.btn_stop.config(state=NORMAL)

        try:
            cookie_id = self.inputCookie_var.get()
            if t == TYPE_WORKER:  # 画师
                input_worker_id = self.input_var_worker.get()
                if input_worker_id == '':
                    logging.warning('输入的画师id不能为空~~')
                    return
                if self.is_workers():
                    webbrowser.open(f"https://www.pixiv.net/users/{input_worker_id}")
                PixivDownloader(cookie_id, input_worker_id, app, TYPE_WORKER).pre_download()
            elif t == TYPE_ARTWORKS:  # 插画
                input_img_id = self.input_var_artwork.get()
                if input_img_id == '':
                    logging.warning('输入的插画id不能为空~~')
                    return
                if self.is_artworks():
                    webbrowser.open(f"https://www.pixiv.net/artworks/{input_img_id}")
                PixivDownloader(cookie_id, input_img_id, app, TYPE_ARTWORKS).pre_download()
        except Exception as e:
            logging.error(e)
        finally:
            self.is_stop = False
            self.is_paused = False
            self.btn_pause.config(text=' ⏸ ')

            self.button_artist.config(state=NORMAL)
            self.button_artwork.config(state=NORMAL)

            self.btn_pause.config(state=DISABLED)
            self.btn_stop.config(state=DISABLED)

    def update_progress_bar(self, value, total):
        self.progress_bar["value"] = value
        self.progress_bar["maximum"] = total
        self.progress_bar.update()  # 刷新UI显示

        # 更新文本显示
        self.process_text.config(text=f"{(value / total * 100):.2f}%")
        self.root.update_idletasks()

    @thread_it
    def toggle_pause(self):
        if self.is_paused:
            self.is_paused = False
            self.btn_pause.config(text=' ⏸ ')
        else:
            self.is_paused = True
            self.btn_pause.config(text=' ▶ ')

    @thread_it
    def stop_download(self):
        logging.info('正在停止下载')

        self.is_stop = True



if __name__ == '__main__':
    config = read_json()

    root = Tk()
    app = PixivApp(root)

    log_init()  # 日志初始化
    check_registry_key_exists(r"pixivdownload")
    line_cookie = ''

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
        elif arg == "-artwork-id":
            artwork_id = args[args.index(arg) + 1]
        elif arg == "-cookie":
            line_cookie = args[args.index(arg) + 1]
            logging.debug(f"设置cookie为：{line_cookie}")
        elif arg == "--start-now":
            is_start_now = True
        elif arg == "--exit-finish":
            if_exit_finish = True

    if worker_id and artwork_id and is_start_now:
        logging.warning("一个一个来~")
        exit(1)

    if line_cookie and line_cookie != config['cookie']:
        config['cookie'] = line_cookie
        update_json(config)

    if worker_id:
        app.input_var_worker.set(worker_id)
        if is_start_now:
            app.button_artist.invoke()
    if artwork_id:
        app.input_var_artwork.set(artwork_id)
        if is_start_now:
            app.button_artwork.invoke()

    root.mainloop()
