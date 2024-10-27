import re
import time
from logging.handlers import TimedRotatingFileHandler
from tkinter.ttk import Progressbar
import requests
import urllib3
import json
import random
from bs4 import BeautifulSoup
import os
from tkinter import *
import webbrowser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

urllib3.disable_warnings()


def thread_it(func):
    thread = threading.Thread(target=func)
    thread.daemon = True
    thread.start()


# 通过作品id下载
class ThroughArtWorkerId:
    def __init__(self, cookie_id, img_id, pixiv_app):
        self.img_id = img_id
        self.app = pixiv_app
        self.cookie = cookie_id if cookie_id != "" else cookie
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}

    # 获取画师名字
    def getWorkerName(self):
        artworks_id = f"https://www.pixiv.net/artworks/{self.img_id}"
        requests_worker = requests.get(artworks_id, verify=False, headers=self.headers)
        requests_worker.raise_for_status()
        soup = BeautifulSoup(requests_worker.text, 'html.parser')
        meta_tag = str(soup.find_all('meta')[-1])
        try:
            username = re.findall(f'"userName":"(.*?)"', meta_tag)[0]
            username = re.sub(r'[/\\| ]', '_', username)
        except IndexError:
            logging.error("未找到该作品的画师~")
        else:
            return username

    def downLoad(self):
        logging.info(f"开始下载图片:{self.img_id}")
        try:
            session = requests.Session()
            response = session.get(url=f"https://www.pixiv.net/ajax/illust/{self.img_id}/pages?lang=zh",
                                   verify=False, headers=self.headers)
            if response.status_code != 200:
                logging.error(f"请求失败，状态码: {response.status_code}\n")
                return
            url = json.loads(response.text)['body']
            if len(url) == 0:
                logging.error("未找到该插画~")
                return
        except json.decoder.JSONDecodeError:
            logging.error("你的cookie信息已过期")
        else:
            mkdirs = os.path.join(os.getcwd(), "artworks_IMG")
            os.makedirs(mkdirs, exist_ok=True)
            logging.info("初始化中~")
            logging.info(f"一共{len(url)}张插画，正在下载中~")

            # 计算文件总大小，更新进度条最大值
            total_size = sum(
                int(requests.head(url['urls']['original'], headers=self.headers, verify=False).headers.get(
                    'content-length', 0)) for url in url)
            self.app.update_progress_bar(0, total_size)  # 初始化进度条
            # 使用多线程下载图片
            with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                futures = []
                for ID in url:
                    href1 = ID['urls']['original']
                    futures.append(executor.submit(self.download_image, href1, mkdirs))

                # 等待所有任务完成
                for future in as_completed(futures):
                    future.result()

            logging.info("图片下载完成~\n*---------------------------------*")

    def download_image(self, url, mkdirs):
        session = requests.Session()
        download_response = session.get(url=url, headers=self.headers, verify=False, stream=True)
        if download_response.status_code != 200:
            logging.error(f"下载失败，状态码: {download_response.status_code}\n")
        else:
            file_path = os.path.join(mkdirs, f"@{self.getWorkerName()} {os.path.basename(url)}")
            with open(file_path, "wb") as f:
                for data in download_response.iter_content(chunk_size=1024):
                    f.write(data)
                    self.app.update_progress_bar(len(data))  # 更新进度条


# 通过画师id下载
class ThroughWorkerId:
    def __init__(self, cookie_id, users_id, pixiv_app):
        self.users_id = users_id
        self.app = pixiv_app
        self.cookie = cookie_id if cookie_id != "" else cookie
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}

    # 获取画师名字
    def getWorkerName(self):
        worker_url = f'https://www.pixiv.net/users/{self.users_id}'
        try:
            response = requests.get(worker_url, headers=self.headers, verify=False)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"网络请求失败: {e}")
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        title = str(soup.title.string)
        try:
            name = re.findall(r'(.*?) - pixiv', title)[0]
            name = re.sub(r'[/\\| ]', '_', name)
        except IndexError:
            logging.error("未找到该画师,请重新输入~")
            return None
        else:
            return name

    # 获取图片全部id(是个列表)
    def getImgId(self):
        id_url = f"https://www.pixiv.net/ajax/user/{self.users_id}/profile/all?lang=zh"
        try:
            response = requests.get(id_url, headers=self.headers, verify=False)
            response.raise_for_status()  # 检查 HTTP 请求是否成功
            artworks = re.findall(r'"(\d+)":null', response.text)
        except requests.RequestException as e:
            logging.error(f"网络请求错误: {e}")
            artworks = []
        return artworks

    # 找到下载链接,开爬
    def download(self, ids):
        # 随机等待时间，防止被ban
        second = random.randint(1, 4)
        mkdirs = os.path.join(os.getcwd(), "workers_IMG", self.getWorkerName())
        illust_url = f"https://www.pixiv.net/ajax/illust/{ids}/pages?lang=zh"
        try:
            res_json = requests.get(url=illust_url, headers=self.headers, verify=False).text
        except requests.RequestException as e:
            logging.error(f"请求失败: {e}")
            return
        # 解析JSON响应
        try:
            url_list = json.loads(res_json)['body']
        except (json.JSONDecodeError, KeyError) as e:
            logging.error(f"解析JSON失败: {e}")
            return
        # 遍历图片URL列表
        for ID in url_list:
            href1 = ID['urls']['original']
            # 发送请求获取图片内容
            try:
                response = requests.get(url=href1, headers=self.headers, verify=False)
                response.raise_for_status()
            except requests.RequestException as e:
                logging.error(f"下载失败: {e}")
                continue
            filename = f"@{self.getWorkerName()} {os.path.basename(href1)}"
            filepath = os.path.join(mkdirs, filename)
            if not os.path.exists(filepath):
                with open(filepath, "wb") as f:
                    f.write(response.content)
                time.sleep(second)

    def preDownload(self):
        try:
            listId = self.getImgId()
            logging.info(f"大概下载图片数: {len(listId)}+")

            mkdirs = os.path.join(os.getcwd(), "workers_IMG", self.getWorkerName())
            os.makedirs(mkdirs, exist_ok=True)

            # 开始下载
            logging.info("正在检索并下载中，请稍后(进度条会有点延迟)。。。")
            self.app.update_progress_bar(0, len(listId))  # 初始化进度条
            with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                futures = [executor.submit(self.download, img_id) for img_id in listId]
                for future in as_completed(futures):
                    future.result()
                    self.app.update_progress_bar(1)  # 更新进度条
            logging.info(f"下载完成，共有{len(os.listdir(mkdirs))}张图片~")
            logging.info("*---------------------------------*")
        except TypeError:
            logging.error("输入的画师id有误或不存在，也可能是你cookie失效了，换一个吧~")
        except Exception as e:
            logging.critical(f"发生了一个错误: {e}\n")


class TkinterLogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state='normal')
        self.text_widget.insert('end', msg + '\n')
        self.text_widget.see('end')
        self.text_widget.configure(state='disabled')


class PixivApp:
    def __init__(self, root_app):
        self.root = root_app
        self.root.geometry('700x700+400+5')
        self.root.title('pixiv爬虫')
        self.root.img = PhotoImage(file='img//92260993.png')
        self.log_text = ''
        self.progress_bar = {}
        self.total_progress = 0
        self.current_progress = 0
        self.button1 = None
        self.button2 = None
        self.input_var = StringVar()  # 接受画师uid
        self.id_input_var = StringVar()  # 接受作品uid
        self.inputCookie_var = StringVar()  # 接受登陆后的cookie
        self.b_users = BooleanVar()  # 是否查看画师主页
        self.b_artworks = BooleanVar()  # 是否查看作品网页

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
        self.button1 = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                              bg='lavender', height=2, command=lambda: thread_it(self.WorkerId))
        self.button1.pack(fill='both', pady=(0, 10), anchor="n")
        label_input1 = Label(input_frame1, text='请输入画师uid:', font=('黑体', 20))
        label_input1.pack(side=LEFT)
        entry1 = Entry(input_frame1, width=95, relief='flat', textvariable=self.input_var)
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
        self.button2 = Button(self.root, text='提交', font=('黑体', 15), relief='groove', compound=CENTER,
                              bg='lavender', height=2, command=lambda: thread_it(self.ArtWorkerId))
        self.button2.pack(fill='both', pady=(0, 0), anchor="n")
        label_input2 = Label(input_frame2, text='请输入图片uid:', font=('黑体', 20))
        label_input2.pack(side=LEFT)
        entry2 = Entry(input_frame2, width=95, relief='flat', textvariable=self.id_input_var)
        entry2.pack(side=LEFT, fill='both')

        # 日志显示区域
        self.progress_bar = Progressbar(self.root, orient='horizontal', mode='determinate')
        self.progress_bar.pack(fill='both')
        self.log_text = Text(self.root, height=10, state='disabled')
        self.log_text.pack(fill='both', expand=True)

    def isWorkers(self):
        return self.b_users.get()

    def isArtworks(self):
        return self.b_artworks.get()

    def WorkerId(self):
        try:
            self.button1.config(state=DISABLED)
            self.button2.config(state=DISABLED)
            cookieID = self.inputCookie_var.get()
            workerId = self.input_var.get()
            if workerId == '':
                logging.error('输入的画师id不能为空~~')
                return
            if self.isWorkers():
                webbrowser.open(f"https://www.pixiv.net/users/{workerId}")
            ThroughWorkerId(cookieID, workerId, app).preDownload()
        except requests.exceptions.ConnectTimeout:
            logging.error("网络请求失败，用加速器试试，提个醒，别用代理工具~")
        except requests.exceptions.RequestException as e:
            logging.error(f"网络请求失败: {e}")
        finally:
            self.button1.config(state=NORMAL)
            self.button2.config(state=NORMAL)

    def ArtWorkerId(self):
        try:
            self.button1.config(state=DISABLED)
            self.button2.config(state=DISABLED)
            cookieID = self.inputCookie_var.get()
            ImgId = self.id_input_var.get()
            if ImgId == '':
                logging.error('输入的插画id不能为空~~')
                return
            if self.isArtworks():
                webbrowser.open(f"https://www.pixiv.net/artworks/{ImgId}")
            ThroughArtWorkerId(cookieID, ImgId, app).downLoad()
        except requests.exceptions.ConnectTimeout:
            logging.error("网络请求失败，用加速器试试，提个醒，别用代理工具~")
        except requests.exceptions.RequestException as e:
            logging.error(f"网络请求失败: {e}")
        finally:
            self.button1.config(state=NORMAL)
            self.button2.config(state=NORMAL)

    def update_progress_bar(self, increment, total=0):
        if total:  # 设置进度条最大值
            self.total_progress = total
            self.progress_bar["maximum"] = total
        else:  # 更新进度条值
            self.current_progress += increment
            self.progress_bar["value"] = self.current_progress
            self.progress_bar.update()  # 刷新UI显示


if __name__ == '__main__':
    cookie = "first_visit_datetime_pc=2024-03-25%2023%3A22%3A07; p_ab_id=7; p_ab_id_2=4; p_ab_d_id=170919518; yuid_b=NWcCYEc; c_type=31; privacy_policy_notification=0; a_type=0; b_type=1; login_ever=yes; __utma=235335808.2067325330.1711376549.1712414350.1712414350.1; __utmv=235335808.|2=login%20ever=yes=1^3=plan=normal=1^6=user_id=55796473=1^9=p_ab_id=7=1^10=p_ab_id_2=4=1^11=lang=zh=1; privacy_policy_agreement=7; PHPSESSID=55796473_feqzyeC0Xa6RKj7622mzDv6XNiDJUnnJ; _ga_MZ1NL4PHH0=GS1.1.1723516881.9.1.1723521223.0.0.0; cf_clearance=ePCIjhG9_Eql7IyUIkJVyRGwI8W8HmH.SUxTVEiicFE-1724682821-1.2.1.1-2mpH9ATUPM9MCW78KrJ_lrFx6jg0SgSqJ68AOcpru6DftHXKeaTe0B.zmtYRnw95wHNOBoFgBLWuHMuA5eaFIn_H0Q0c7K1eHqx5iBggHrlmvcPQQYiX9wWZFLqPVYcGl72.Zj_gaH_V3i3nl1u9EoAPENA28q3LC.xtDV4IM.CEnxr6lk2kIfuzcJAJBADTeA9sqbNeX2wixt7PpLKYVH9hHVMrm0Q0pIczSSoy0gTMihnxaPKdpxO.h7uE7GETVMZuB0TYEGBE3QRG96m17ex3wgDM_na6pbkLwH1S.ouQamyXx4w_UKf2.YDhvGP0DvghCz8jytxl8_5HOS3sd2oSRg9tXoAnnuo9rtWaE95OB2yIEi3cEMBk0rjxbiuveGHf2jdy1CbpD_sDsKUwyQ; first_visit_datetime=2024-09-28%2022%3A53%3A28; webp_available=1; _ga_3WKBFJLFCP=GS1.1.1727531608.1.0.1727531610.0.0.0; _gid=GA1.2.259876661.1729870123; _ga=GA1.2.2067325330.1711376549; _ga_75BBYNYN9J=GS1.1.1729869688.52.1.1729870957.0.0.0"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    root = Tk()
    app = PixivApp(root)

    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # 创建文件处理器，将日志写入文件
    file_handler = TimedRotatingFileHandler('my.log', when='midnight', interval=1, backupCount=7)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(logging.INFO)

    # 创建Tkinter日志处理器
    tkinter_handler = TkinterLogHandler(app.log_text)
    tkinter_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    tkinter_handler.setLevel(logging.INFO)

    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(tkinter_handler)
    root.mainloop()
