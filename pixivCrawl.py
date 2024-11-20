import ctypes
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from tkinter.ttk import Progressbar
import requests
import urllib3
import json
from bs4 import BeautifulSoup
import os
from tkinter import *
import webbrowser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import zipfile
from PIL import Image
from requests.adapters import HTTPAdapter
import winreg

urllib3.disable_warnings()

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画


def thread_it(func, *args):
    thread = threading.Thread(target=func, args=args)
    thread.daemon = True
    thread.start()


# 判断响应码
def request_if_error(response):
    try:
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logging.error(f"请求失败，状态码: {response.status_code}")


# 创建文件夹
def create_directory(*base_dir):
    script_path = os.path.abspath(sys.argv[0])  # 获取绝对路径
    parent_dir = os.path.dirname(script_path)
    mkdir = os.path.join(parent_dir, *base_dir)
    os.makedirs(mkdir, exist_ok=True)
    return mkdir


# 创建或更新文件，清空文件内容
def touch(file_path):
    with open(file_path, 'wb') as f:
        f.truncate(0)


# 获取资源文件的绝对路径
def resource_path(relative_path):
    # PyInstaller 创建临时文件夹，所有 pyInstaller 程序运行时解压后的文件都在 _MEIPASS 中
    base_path = getattr(sys, '_MEIPASS', None)
    if base_path is None:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 初始化日志
def log_init():
    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # 创建文件处理器，将日志写入文件
    mkdirLog = create_directory("log")
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
        print("注册表键不存在，创建中...")
        root_key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path)
        key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path + "\\shell\\open\\command")
        winreg.SetValueEx(root_key, "URL Protocol", 0, winreg.REG_SZ, "")
    path = f'"{os.path.abspath(sys.argv[0])}" "%1"'
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, path)
    winreg.CloseKey(root_key)
    winreg.CloseKey(key)


# 读取json文件
def read_json():
    json_file = "pixivCrawl.json"
    default_data = {
        "PHPSESSID": "",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
    }
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        print("未找到配置文件，正在创建默认配置文件。")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=4)
        return default_data


# 更新json文件
def update_json(data_id):
    json_file = resource_path("pixivCrawl.json")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    data["PHPSESSID"] = data_id.replace("PHPSESSID=", "")

    with open(json_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=4))
    logging.info(f"成功更新配置文件，下次失效时再进行填写。")


# p站图片下载器
class PixivDownloader:
    def __init__(self, cookie_id, pixiv_app):
        self.app = pixiv_app
        self.type = ""  # 输入的id类型
        self.artist = ""  # 画师名字
        self.mkdirs = ""  # 存放图片的文件夹
        self.numbers = 0  # 图片数量
        self.cookie = f'PHPSESSID={cookie_id}' if cookie_id != '' else f'PHPSESSID={cookie}'
        # 更新cookie
        if self.cookie != cookie and self.cookie != f'PHPSESSID={cookie}':
            update_json(self.cookie)
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}
        self.download_queue = []  # 下载队列
        self.download_size = 1024 * 1024  # 每次下载的大小
        self.need_com_gif = {}  # 需要合成的动图
        self.s = requests.Session()

        # 配置HTTP和HTTPS连接的池和重试策略
        adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=5)
        self.s.mount('http://', adapter)
        self.s.mount('https://', adapter)

    def download_and_save_image(self, url, save_path, start_size, end_size=''):
        # 根据起始和结束位置构建HTTP请求的Range头
        byte_range = f'bytes={start_size}-{end_size}'
        d_headers = {
            'User-Agent': user_agent,
            'referer': 'https://www.pixiv.net/',
            'Range': byte_range
        }
        resp = self.s.get(url, headers=d_headers, verify=False)
        with open(save_path, 'rb+') as f:
            if start_size == '':
                f.seek(0, 0)
            else:
                f.seek(int(start_size), 0)
            f.write(resp.content)
        self.app.update_progress_bar(1)  # 更新进度条

    def download_images(self, img_ids, t):
        try:
            self.type = t
            self.artist = self.get_worker_name(img_ids[0])
            if self.artist is None:
                return
            logging.info(f"画师名字: {self.artist}")
            if self.type == TYPE_WORKER:  # 类型是通过画师id
                logging.info(f"正在查找图片总数，图片id集为{len(img_ids)}个...")
                self.mkdirs = create_directory("workers_IMG", self.artist)
            elif self.type == TYPE_ARTWORKS:  # 类型是通过插画id
                self.mkdirs = create_directory("artworks_IMG", img_ids[0])
            self.app.update_progress_bar(0, len(img_ids))
            self.download_by_art_worker_ids(img_ids)

            self.app.update_progress_bar(0, len(self.download_queue))  # 初始化进度条
            logging.info(f"检索结束...")
            if self.numbers == 0:
                logging.warning("PHPSESSID已失效，请重新填写!")
                return
            logging.info(f"正在开始下载... 共{self.numbers}张图片...")
            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 64)) as executor:
                futures = []
                for (url, save_path, start_size, end_size) in self.download_queue:
                    f = executor.submit(self.download_and_save_image, url, save_path, start_size, end_size)
                    futures.append(f)
            for future in as_completed(futures):
                future.result()

            if len(self.need_com_gif) > 0:
                logging.info(f"开始合成动图，数量:{len(self.need_com_gif)}")
                self.app.update_progress_bar(0, len(self.need_com_gif))
                for img_id in self.need_com_gif:
                    self.comp_gif(img_id)
                    self.app.update_progress_bar(1)

            logging.info(f"下载完成，文件夹内共有{len(os.listdir(self.mkdirs))}张图片~")
            logging.info(f"存放路径：{os.path.abspath(self.mkdirs)}")
            os.startfile(self.mkdirs)
            if if_exit_finish:
                logging.info("程序即将自动退出~")
                time.sleep(3)
                root.destroy()

        except IndexError:
            logging.warning("未找到该画师,请重新输入~")

    def get_worker_name(self, img_id):
        artworks_id = f"https://www.pixiv.net/artworks/{img_id}"
        requests_worker = self.s.get(artworks_id, headers=self.headers, verify=False)
        soup = BeautifulSoup(requests_worker.text, 'html.parser')
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
        for future in as_completed(futures):
            future.result()

    def download_by_art_worker_id(self, img_id):
        ugoira_url = f"https://www.pixiv.net/ajax/illust/{img_id}/ugoira_meta"
        response = self.s.get(url=ugoira_url, headers=self.headers, verify=False)
        data = response.json()
        if data['error']:  # 是静态图
            self.download_static_images(img_id)
        else:  # 是动图
            self.download_gifs(data, img_id)
        self.app.update_progress_bar(1)

    def download_static_images(self, img_id):
        response = self.s.get(url=f"https://www.pixiv.net/ajax/illust/{img_id}/pages", headers=self.headers,
                              verify=False)
        request_if_error(response)
        # 解析响应以获取所有静态图片的URL
        static_url = json.loads(response.text)['body']
        for urls in static_url:
            # 原始分辨率图片的URL
            url = urls['urls']['original']
            name = os.path.basename(url)
            file_path = os.path.join(self.mkdirs, f"@{self.artist} {name}")
            touch(file_path)
            resp = self.s.get(url=url, headers=self.headers, verify=False)

            self.add_download_queue(url, file_path, resp)

    def download_gifs(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.mkdirs, name)
        touch(file_path)
        self.need_com_gif[img_id] = delays

        resp = self.s.get(url, headers=self.headers, verify=False)
        self.add_download_queue(url, file_path, resp)

    def add_download_queue(self, url, file_path, response):
        self.numbers += 1
        try:
            length = int(response.headers['Content-Length'])
            i = 0
            while i < length - self.download_size:
                self.download_queue.append((url, file_path, i, i + self.download_size - 1))
                i += self.download_size
            self.download_queue.append((url, file_path, i, ''))
        except KeyError:
            # 如果无法获取文件大小，则对整个文件不分块下载
            self.download_queue.append((url, file_path, '', ''))

    def comp_gif(self, img_id):
        delays = self.need_com_gif[img_id]
        name = f"@{self.artist} {img_id}.gif"
        o_name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.mkdirs, name)
        o_file_name = os.path.join(self.mkdirs, o_name)
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


# 通过输入框获取id下载图片
class ThroughId(PixivDownloader):
    def __init__(self, cookie_id, id, pixiv_app, t):
        super().__init__(cookie_id, pixiv_app)
        self.id = id
        self.type = t

    # 获取用户的所以作品id
    def get_img_ids(self):
        id_url = f"https://www.pixiv.net/ajax/user/{self.id}/profile/all?lang=zh"
        response = requests.get(id_url, headers=self.headers, verify=False)
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
        self.root.geometry('700x700+400+5')
        self.root.title('pixiv下载器')
        img_path = resource_path('img\\92260993.png')
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
        global cookie
        try:
            cookie = f'{read_json()["PHPSESSID"]}'
            # 防止用户在处理期间进行交互
            self.button_artist.config(state=DISABLED)
            self.button_artwork.config(state=DISABLED)
            cookieID = self.inputCookie_var.get()
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
    cookie = ''
    user_agent = read_json()["user_agent"]

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
        if '/' in url_get:
            args = url_get.split('/')

    # 命令行参数解析
    for arg in args:
        if arg == "-worker-id":
            worker_id = args[args.index(arg) + 1]
        elif arg == "-artwork-id":
            artwork_id = args[args.index(arg) + 1]
        elif arg == "-cookie":
            cookie = args[args.index(arg) + 1].replace("PHPSESSID=", "")
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
