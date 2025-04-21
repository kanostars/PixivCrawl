import argparse
import concurrent
import os
import re
import time
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from tkinter import *
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
from tkinter.ttk import Progressbar

from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdrivermanager_cn import ChromeDriverManagerAliMirror

import file_handler
import log_handler
import version
import zco
from utils import *

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画

config = {}

languages = {
    "zh_tw": ["的插畫", "的漫畫"],
    "zh": ["的插画", "的漫画"],
    "ja": ["のイラスト", "のマンガ"],
    "ko": ["의 일러스트", "의 만화"]
}


# p站图片下载器
@log_it()
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
            file_handler.update_json(config)

        self.headers = {'Referer': "https://www.pixiv.net/",
                        'User-agent': config['user_agent'],
                        'Cookie': self.cookie,
                        'Accept-Transfer-Encoding': 'identity'}
        self.download_queue = []  # 下载队列
        self.downloading_resp = []
        self.need_com_gif = {}  # 需要合成的动图

    def download_and_save_image(self, url, save_path):
        if self.app.is_stop:
            return
        while self.app.is_paused:
            time.sleep(0.5)
        resp = zco.connect(url, headers=self.headers)
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
                self.dirs = file_handler.create_directory("workers_IMG", self.artist)
            elif self.type == TYPE_ARTWORKS:  # 类型是通过插画id
                self.dirs = file_handler.create_directory("artworks_IMG", img_ids[0])

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
        requests_worker = zco.connect(artworks_id, headers=self.headers)
        re_txt = requests_worker.text
        # 获取浏览器语言
        lang = re.findall(r' lang="(.*?)"', re_txt)
        if lang:
            lang = lang[0]
        else:
            return None
        if lang in languages:
            # 返回画师名字
            for l in languages[lang]:
                name = re.search(f'- (.*?){l}', re_txt)
                if name:
                    return name.group(1)
        else:
            logging.info("不支持该网站的语言，仅支持简体中文、繁体中文、韩语及日语。")
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

        response = zco.connect(ugoira_url, headers=self.headers)

        data = response.json
        if data['error']:  # 是静态图
            self.download_static_images(img_id)
        else:  # 是动图
            self.download_gifs(data, img_id)

    def download_static_images(self, img_id):
        response = zco.connect(url=f"https://www.pixiv.net/ajax/illust/{img_id}/pages", headers=self.headers)

        # 解析响应以获取所有静态图片的URL
        static_url = response.json['body']
        for urls in static_url:
            # 原始分辨率图片的URL
            url = urls['urls']['original']
            name = os.path.basename(url)
            file_path = os.path.join(self.dirs, f"@{self.artist} {name}")
            file_handler.touch(file_path)

            self.add_download_queue(url, file_path)

    def download_gifs(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.dirs, name)
        file_handler.touch(file_path)
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
        response = zco.connect(id_url, headers=self.headers)
        return re.findall(r'"(\d+)":null', response.text)

    def pre_download(self):
        if self.type == TYPE_ARTWORKS:
            logging.info(f"正在通过插画ID({self.id})检索图片...")
            self.download_images([self.id], self.type)
        elif self.type == TYPE_WORKER:
            logging.info(f"正在通过画师ID({self.id})检索图片...")
            img_ids = self.get_img_ids()
            self.download_images(img_ids, self.type)


# 应用界面框
@log_it()
class PixivApp:
    def __init__(self, root_app):
        self.root = root_app
        self.root.geometry('700x750')
        self.root.title('pixiv下载器')
        img_path = file_handler.resource_path('img\\92260993.png')
        self.root.img = PhotoImage(file=img_path)

        # 组件
        self.label_img = None
        self.browser_frame = None
        self.browser_label = None
        self.browser_input = None
        self.browser_choose = None
        self.browser_button = None
        self.browser_alarm = None
        self.login_frame = None
        self.login_btn = None
        self.login_welcome = None
        self.input_frame = None
        self.label_input = None
        self.entry = None
        self.type_btn1 = None
        self.type_btn2 = None
        self.label_type = None
        self.choose_frame = None
        self.label = None
        self.space_btn1 = None
        self.space_btn2 = None
        self.button_submit = None
        self.process_frame = None
        self.process_text = None
        self.btn_stop = None
        self.btn_pause = None
        self.progress_bar = None
        self.log_text = None

        # 基础变量
        self.total_progress = 0
        self.current_progress = 0
        self.is_stop = False
        self.is_paused = False
        self.isLogin = False
        self.is_closed = False
        self.cookie = ''
        self.username = ''

        # 高级变量
        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.login_btn_text = StringVar()  # 登录按钮文字
        self.login_btn_text.set('登录')
        self.welcome = StringVar()  # 欢迎语
        self.welcome.set('欢迎使用pixiv下载器，请登录')
        self.input_var_UID = StringVar()  # 接受画师id/插画id或者链接
        self.input_var_UID.trace('w', self.update_content)
        self.type = StringVar()  # 选择画师/插画
        self.type.set(TYPE_ARTWORKS)
        self.inputCookie_var = StringVar()  # 接受登陆后的cookie
        self.space_visit = BooleanVar()  # 是否查看画师主页
        self.browser_path = StringVar()  # 浏览器路径
        if config.get('browser_path'):
            self.browser_path.set(config.get('browser_path'))
        self.b_users = BooleanVar()  # 是否查看画师主页
        self.b_artworks = BooleanVar()  # 是否查看作品网页

        # 创建控件
        self.create_widgets()

        self.pack_widgets()

        self.is_login_by_name()

        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

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

        # 登录
        self.login_frame = LabelFrame(self.root)
        self.login_btn = Button(self.login_frame, textvariable=self.login_btn_text, font=('黑体', 15),
                                command=self.login_or_out,
                                width=40, relief='groove',
                                compound='center')
        self.login_welcome = Label(self.login_frame, textvariable=self.welcome, font=('黑体', 12))

        # 键入uid
        self.input_frame = LabelFrame(self.root)
        self.label_input = Label(self.input_frame, text='请输入链接/UID:', font=('黑体', 18))
        self.entry = Entry(self.input_frame, width=40, relief='flat', textvariable=self.input_var_UID)
        self.type_btn1 = Radiobutton(self.input_frame, text='画师', font=('宋体', 10), height=1, variable=self.type,
                                     value=TYPE_WORKER)
        self.type_btn2 = Radiobutton(self.input_frame, text='插画', font=('宋体', 10), height=1, variable=self.type,
                                     value=TYPE_ARTWORKS)
        self.label_type = Label(self.input_frame, text='作品类型:', font=('黑体', 12))

        # 跳转空间
        self.choose_frame = LabelFrame(self.root)
        self.label = Label(self.choose_frame, text='要去空间看看吗？', font=('黑体', 12))

        self.space_btn1 = Radiobutton(self.choose_frame, text='是的，我要康', font=('宋体', 11),
                                      variable=self.space_visit,
                                      value=True, height=2)
        self.space_btn2 = Radiobutton(self.choose_frame, text='不用了，懒得点', font=('宋体', 11),
                                      variable=self.space_visit,
                                      value=False, height=2)
        self.space_visit.set(False)

        # 提交按钮
        self.button_submit = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound='center',
                                    bg='lavender', height=2, command=self.submit_id)

        # 进度条显示区域
        self.process_frame = Frame(self.root)
        # 创建样式对象
        self.style.configure("Custom.Horizontal.TProgressbar", troughcolor='white', background='lightblue',
                             bordercolor='gray')
        self.progress_bar = Progressbar(self.process_frame, orient='horizontal', mode='determinate',
                                        length=550, style="Custom.Horizontal.TProgressbar")
        self.progress_bar.config()
        self.process_text = Label(self.process_frame, text='0%')
        self.btn_stop = Button(self.process_frame, text=' X ', font=('黑体', 11), background="red", foreground="white",
                               command=self.stop_download)
        self.btn_pause = Button(self.process_frame, text=' ▶ ', font=('黑体', 11),
                                command=self.toggle_pause)

        # 日志显示区域
        self.log_text = Text(self.root, height=10)
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.insert('1.0',  # 插入默认日志信息
                             f'欢迎使用 Pixiv下载器-直连版 v{version.__version__} ！\n'
                             '登录以下载更多图片，失效时再重新登录。\n'
                             f'本下载器由zco v{zco.__version__}提供网络服务。\n'
                             '---------------------------------------------------------------------------------------------------\n')
        self.log_text.config(state='disabled')  # 禁用编辑功能

    def pack_widgets(self):
        self.label_img.pack(fill='both')

        self.browser_label.pack(side='left')
        self.browser_input.pack(side='left')
        self.browser_choose.pack(side='left')
        self.browser_button.pack(side='left')
        self.browser_alarm.pack(side='left')
        self.browser_frame.pack(fill='both', anchor='n')

        self.login_welcome.pack(side='left', padx=5)
        self.login_btn.pack(side='right')
        self.login_frame.pack(fill='both', pady=(0, 5))

        self.type_btn2.pack(side='right', padx=5)
        self.type_btn1.pack(side='right', padx=5)
        self.label_input.pack(side='left')
        self.entry.pack(side='left', fill='both')
        self.label_type.pack(side='right', padx=10)
        self.input_frame.pack(fill='both', pady=(0, 5))

        self.label.pack(side='left')
        self.space_btn2.pack(side='left', padx=20)
        self.space_btn1.pack(side='left', padx=20)

        self.choose_frame.pack(fill='both', pady=(0, 5))

        self.button_submit.pack(fill='both', anchor="n")

        self.btn_stop.config(state='disabled')
        self.btn_pause.config(state='disabled')
        self.process_frame.pack(fill='both')
        self.btn_pause.pack(side='right')
        self.btn_stop.pack(side='right', padx=5)
        self.process_text.pack(side='left', padx=10)
        self.progress_bar.pack(side='left', padx=2)

        self.log_text.pack(fill='both', expand=True)

    def login_or_out(self):
        try:
            if not self.isLogin:
                service = Service(executable_path=ChromeDriverManagerAliMirror().install())
                options = webdriver.ChromeOptions()
                options.add_argument(
                    '--host-rules="MAP api.fanbox.cc api.fanbox.cc,MAP *pixiv.net pixivision.net,MAP *fanbox.cc pixivision.net,MAP *pximg.net U4,MAP *pinterest.com U5,MAP *pinimg.com U5"')
                options.add_argument(
                    '--host-resolver-rules="MAP api.fanbox.cc 172.64.146.116,MAP pixivision.net 210.140.139.155,MAP U4 210.140.139.133,MAP U5 151.101.0.84"')
                options.add_argument('--test-type')
                options.add_argument('--ignore-certificate-errors')
                prefs = {
                    "profile.managed_default_content_settings.images": 2,  # 禁止加载图片
                }
                options.add_experimental_option("prefs", prefs)
                driver = webdriver.Chrome(options=options, service=service)
                driver.get('https://accounts.pixiv.net/login')
                WebDriverWait(driver, 300).until(
                    EC.url_contains("www.pixiv.net")  # 检查目标URL包含的关键字
                )
                # 获取最终跳转后的URL
                for cookie in driver.get_cookies():
                    if cookie['name'] == 'PHPSESSID':
                        self.cookie = f'PHPSESSID={cookie['value']}'
                        logging.debug(f'用户登录获得的cookie: {self.cookie}')
                        div_text = driver.find_element(By.CSS_SELECTOR, 'div.jePfsr').get_attribute('outerHTML')
                        self.username = re.search(r'<div class="sc-4bc73760-3 jePfsr">(.*?)</div>', div_text).group(1)
                        logging.info(f"用户{self.username}已登录~")
                        self.welcome.set(f'你好，{self.username}！')
                        self.login_btn_text.set("退出登录")
                        self.isLogin = True
                        driver.close()
                        break
                cookie_temp = self.cookie if self.cookie else config['cookie']

                # 更新cookie
                if cookie_temp != config['cookie'] and cookie_temp:
                    config['cookie'] = cookie_temp
                    file_handler.update_json(config)
                    logging.debug(f"cookie已更新为：{cookie_temp}")

            else:
                logging.info(f"已成功退出")
                self.isLogin = False
                config['cookie'] = ''
                file_handler.update_json(config)
                self.login_btn_text.set("登录")
                self.welcome.set("欢迎，登录可以下载更多图片！")
        except Exception as e:
            logging.debug(f"登录失败，错误信息：{e}")
            logging.info("已取消登录")

    def update_content(self, *_):
        content = self.input_var_UID.get()
        artwork_content = re.search('www.pixiv.net/artworks/(\\d+)', content)
        if artwork_content:
            self.type.set(TYPE_ARTWORKS)
            self.input_var_UID.set(artwork_content.group(1))
            return
        worker_content = re.search('www.pixiv.net/users/(\\d+)', content)
        if worker_content:
            self.type.set(TYPE_WORKER)
            self.input_var_UID.set(worker_content.group(1))
            return

    def on_closing(self):
        self.stop_download()
        self.is_closed = True
        self.root.destroy()
        exit(0)

    @thread_it
    def is_login_by_name(self):
        name = self.get_username()
        if name:
            self.login_btn_text.set("退出登录")
            self.welcome.set(f"你好，{name}！")
            self.isLogin = True
        else:
            self.isLogin = False

    def get_username(self):
        try:
            self.cookie = config['cookie']
            headers = {'Referer': "https://www.pixiv.net/",
                       'User-agent': config['user_agent'],
                       'Cookie': self.cookie,
                       'Accept-Transfer-Encoding': 'identity'}
            res = zco.connect('https://www.pixiv.net/', headers=headers)
            username = re.search(r'<div class="sc-4bc73760-3 jePfsr">(.*?)</div>', res.text).group(1)
            return username
        except Exception as e:
            logging.debug(f"获取用户名失败: {str(e)}")
            logging.warning(f"获取用户名失败,请重新登录")
            return None

    def choose_browser_path(self):
        self.browser_path.set(filedialog.askopenfilename(title="选择浏览器", filetypes=[("exe文件", "*.exe")]))

    def open_browser(self):
        result = messagebox.askokcancel("警告", "打开浏览器时会将正在运行的浏览器关闭！")
        if result:
            if (zco.open_pixiv(self.browser_path.get()) and
                    (not config.get('browser_path') or config.get('browser_path') != self.browser_path.get())):
                config['browser_path'] = self.browser_path.get()
                file_handler.update_json(config)

    # 提交id
    @thread_it
    def submit_id(self):
        # 防止用户在处理期间进行交互
        self.button_submit.config(state=DISABLED)

        self.btn_pause.config(text=' ⏸ ')

        # 允许点击暂停和停止按钮
        self.btn_pause.config(state=NORMAL)
        self.btn_stop.config(state=NORMAL)

        input_id = self.input_var_UID.get()
        if input_id == '':
            logging.warning('输入的id不能为空~~')
            return
        try:
            cookie_id = self.inputCookie_var.get()
            if self.type.get() == TYPE_WORKER:  # 画师
                if self.space_visit.get():
                    webbrowser.open(f"https://www.pixiv.net/users/{input_id}")
                PixivDownloader(cookie_id, input_id, app, TYPE_WORKER).pre_download()
            elif self.type.get() == TYPE_ARTWORKS:  # 插画
                if self.space_visit.get():
                    webbrowser.open(f"https://www.pixiv.net/artworks/{input_id}")
                PixivDownloader(cookie_id, input_id, app, TYPE_ARTWORKS).pre_download()
        except Exception as e:
            logging.error(e)
        finally:
            if self.is_closed:
                return
            self.is_stop = False
            self.is_paused = False
            self.btn_pause.config(text=' ⏸ ')

            self.button_submit.config(state=NORMAL)

            self.btn_pause.config(state=DISABLED)
            self.btn_stop.config(state=DISABLED)

    @exclude_log
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
    config = file_handler.read_json()

    root = Tk()
    app = PixivApp(root)

    log_handler.log_init(app)  # 日志初始化

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
        app.type.set(TYPE_WORKER if args.w else TYPE_ARTWORKS)  # 切换类型
        app.input_var_UID.set(target_id)
        # 更新cookie
        if args.cookie != config['cookie'] and args.cookie:
            file_handler.update_json(config)
            logging.debug(f"PHPSESSID已更新为：{args.cookie}")

        if is_start_now:
            app.button_submit.invoke()

    root.mainloop()
