import re
import sys
from logging.handlers import TimedRotatingFileHandler
from tkinter.ttk import Progressbar, Style
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

urllib3.disable_warnings()

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画


def thread_it(func, *args):
    thread = threading.Thread(target=func, args=args)
    thread.daemon = True
    thread.start()


# 判断响应码
def request_if_error(response):
    """
       检查响应对象是否有错误状态码。

       如果响应状态码表示有错误（即状态码不为2xx），则记录错误日志并抛出异常。
       这个函数主要用于HTTP请求的错误处理。

       参数:
       response: requests.Response对象，代表HTTP响应。

       异常:
       抛出requests.exceptions.RequestException，如果响应状态码表示有错误。
       """
    try:
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logging.error(f"请求失败，状态码: {response.status_code}")


# 创建文件夹
def create_directory(*base_dir):
    """
       根据给定的目录参数创建目录。

       该函数接受一个或多个目录参数，将它们与当前工作目录结合，并创建对应的目录。
       如果目录已经存在，不会重新创建，以防止重复创建导致的错误。

       参数:
       *base_dir: 可变数量的参数，代表需要创建的目录层级。每个参数代表目录层级中的一个部分。

       返回值:
       返回创建的目录路径，或者已经存在的目录路径。
       """
    mkdir = os.path.join(os.getcwd(), *base_dir)
    os.makedirs(mkdir, exist_ok=True)
    return mkdir


# 创建或更新文件，清空文件内容
def touch(file_path):
    with open(file_path, 'wb') as f:
        f.truncate(0)


def resource_path(relative_path):
    """ 获取资源文件的绝对路径 """
    try:
        # PyInstaller 创建临时文件夹，所有 pyInstaller 程序运行时解压后的文件都在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def log_init():
    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
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


# p站图片下载器
class PixivDownloader:
    def __init__(self, cookie_id, pixiv_app):
        """
           初始化Pixiv下载器类的构造函数。

           :param cookie_id: 用户的Cookie ID，用于登录认证。
           :param pixiv_app: Pixiv应用实例，用于与Pixiv API进行交互。
        """
        self.app = pixiv_app
        self.type = ""  # 输入的id类型
        self.artist = ""  # 画师名字
        self.mkdirs = ""  # 存放图片的文件夹
        self.numbers = 0  # 图片数量
        self.cookie = cookie_id if cookie_id != "" else cookie
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
        """
           下载并保存图片。

           根据给定的URL和保存路径，以及指定的字节范围，下载图片并保存到本地。

           参数:
           url (str): 图片的URL地址。
           save_path (str): 图片保存的本地路径。
           start_size (str): 下载图片的起始字节位置。
           end_size (str, optional): 下载图片的结束字节位置。默认为空，表示下载到图片结尾。

           返回:
           无
        """
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
        """
           根据提供的img_ids和类型t下载图片。

           参数:
           img_ids (list): 图片ID列表。
           t (str): 下载类型，可以是'artist'（画师）或'artWork'（插画）。

           返回:
           无
        """
        self.type = t
        self.artist = self.get_worker_name(img_ids[0])
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

        logging.info(f"下载完成，共有{len(os.listdir(self.mkdirs))}张图片~")

    def get_worker_name(self, img_id):
        """
            根据图片ID获取画师名字。

            参数:
            img_id (int): 图片的唯一标识符。

            返回:
            str: 画师的名字，如果找不到则返回None。
        """
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
        """
           并发下载插画作品。

           利用ThreadPoolExecutor创建一个最多可同时运行64个线程的线程池。
           对于每个插画id，提交一个下载任务到线程池，异步执行下载操作。

           参数:
           img_ids (list): 插画id列表，用于指定需要下载的插画作品。

           返回:
           无
        """
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 64)) as executor:
            futures = []
            for img_id in img_ids:
                f = executor.submit(self.download_by_art_worker_id, img_id)
                futures.append(f)
        # 等待所有下载任务完成
        for future in as_completed(futures):
            future.result()

    def download_by_art_worker_id(self, img_id):
        """
           根据插画ID判断插画的类型。

           如果下载的是ugoira类型的作品（一种动画图像格式），则调用下载动图的方法；
           否则，调用下载静态图片的方法。

           参数:
           img_id (int): 插画ID。
        """
        ugoira_url = f"https://www.pixiv.net/ajax/illust/{img_id}/ugoira_meta"
        response = self.s.get(url=ugoira_url, headers=self.headers, verify=False)
        data = response.json()
        if data['error']:  # 是静态图
            self.download_static_images(img_id)
        else:  # 是动图
            self.download_gifs(data, img_id)
        self.app.update_progress_bar(1)

    def download_static_images(self, img_id):
        """
           下载静态图片

           通过给定的图片ID，请求并下载对应的静态图片资源

           参数:
           img_id (str): 图片的唯一标识符

           返回:
           无
        """
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
        """
           下载GIF图像。

           该方法从提供的数据中提取帧延迟和原始URL，构造文件名和路径，并发起HTTP请求以下载GIF图像。

           参数:
           - data: 包含GIF图像信息的字典，包括帧延迟和原始URL。
           - img_id: 图像的唯一标识符，用于构造文件名和引用。

           返回:
           无直接返回值，但会触发GIF图像的下载，并将延迟信息存储在实例变量中。
        """
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.mkdirs, name)
        touch(file_path)
        self.need_com_gif[img_id] = delays

        resp = self.s.get(url, headers=self.headers, verify=False)
        self.add_download_queue(url, file_path, resp)

    def add_download_queue(self, url, file_path, response):
        """
           添加下载任务到下载队列中。

           根据文件的大小，将文件分割成多个部分，每个部分使用一个下载任务。
           如果无法获取文件大小（Content-Length），则对整个文件不分块下载。

           参数:
           - url: 下载链接的URL。
           - file_path: 保存下载文件的路径。
           - response: HTTP响应对象，用于获取文件大小。

           返回值:
           无
        """
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
        """
          根据给定的img_id合成GIF动画并保存。

          该函数从need_com_gif字典中获取指定img_id的延迟时间列表，构造GIF文件名和ZIP文件名，
          然后从ZIP文件中读取所有图片文件，将其转换为RGBA模式，并合并为GIF动画，最后删除ZIP文件

          参数:
          img_id (str): 图像ID，用于标识特定的ZIP文件和生成的GIF文件。

          返回:
          无
        """
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
    """
       根据ID下载Pixiv上的图片。

       继承自PixivDownloader类，提供了根据画师ID或作品ID下载图片的功能。

       属性:
       - cookie_id: 用于登录Pixiv的cookie ID。
       - id: 画师ID或作品ID。
       - pixiv_app: Pixiv应用的相关信息。
       - t: 下载类型，决定是通过画师id下载ta的所有作品，
            还是通过插画id下载对于的作品。
    """

    def __init__(self, cookie_id, id, pixiv_app, t):
        super().__init__(cookie_id, pixiv_app)
        self.id = id
        self.type = t

    def get_img_ids(self):
        """
           获取用户的所有作品ID。

           通过发送GET请求到Pixiv的用户profile页面，解析返回的JSON数据来获取作品ID。

           返回:
           - 一个包含所有作品ID的列表。
        """
        id_url = f"https://www.pixiv.net/ajax/user/{self.id}/profile/all?lang=zh"
        response = requests.get(id_url, headers=self.headers, verify=False)
        return re.findall(r'"(\d+)":null', response.text)

    def pre_download(self):
        if self.type == TYPE_ARTWORKS:
            logging.info(f"正在通过插画ID({self.id})下载图片...")
            self.download_images([self.id], self.type)
        elif self.type == TYPE_WORKER:
            logging.info(f"正在通过画师ID({self.id})下载图片...")
            img_ids = self.get_img_ids()
            self.download_images(img_ids, self.type)


class TkinterLogHandler(logging.Handler):
    """
        该类继承自logging.Handler，用于将日志消息定向到Tkinter的Text控件中。
    """

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget  # 保存Text控件作为日志输出目标

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state='normal')
        self.text_widget.insert('end', msg + '\n')
        self.text_widget.see('end')
        self.text_widget.configure(state='disabled')


# 应用界面框
class PixivApp:
    def __init__(self, root_app):
        self.root = root_app
        self.root.geometry('700x700+400+5')
        self.root.title('pixiv爬虫')
        img_path = resource_path('img//92260993.png')
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

        self.style = Style()
        self.style.configure("Custom.Horizontal.TProgressbar", background="blue")

        # 创建控件
        self.create_widgets()

    def create_widgets(self):
        # 图片框
        label_img = Label(self.root, image=self.root.img, width=800, height=200)
        label_img.pack(fill='both')

        # 键入cookie
        message_cookie = LabelFrame(self.root)
        message_cookie.pack(fill='both', pady=(0, 10), anchor="n")
        cookie_label = Label(message_cookie, text='请输入cookie(默认给的cookie没用在填!):', font=('黑体', 15))
        cookie_label.pack(side=LEFT, pady=20)
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
        process_label = Label(self.root)
        process_label.pack(fill='both')
        self.progress_bar = Progressbar(process_label, orient='horizontal', mode='determinate',
                                        length=650, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.pack(side=LEFT)
        self.process_text = Label(process_label, text='0%')
        self.process_text.pack(side=RIGHT)

        # 日志显示区域
        self.log_text = Text(self.root, height=10, state='disabled')
        self.log_text.pack(fill='both', expand=True)

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
    cookie = ""  # 自行登录去获取cookie
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"  # 自行去获取user-agent
    root = Tk()
    app = PixivApp(root)
    log_init()  # 日志初始化
    #
    # worker_id = None
    # artwork_id = None
    # is_start_now = False
    # for arg in sys.argv:
    #     if arg == "-worker-id":
    #         worker_id = sys.argv[sys.argv.index(arg) + 1]
    #     elif arg == "-artwork-id":
    #         artwork_id = sys.argv[sys.argv.index(arg) + 1]
    #     elif arg == "-cookie":
    #         cookie = sys.argv[sys.argv.index(arg) + 1]
    #     elif arg == "--start-now":
    #         is_start_now = True
    # if worker_id is not None:
    #     app.input_var_worker.set(worker_id)
    # if artwork_id is not None:
    #     app.input_var_artwork.set(artwork_id)
    # if is_start_now:
    #     app.WorkerId()
    #
    # print(worker_id)
    # print(artwork_id)
    # print(cookie)
    # print(is_start_now)
    root.mainloop()
