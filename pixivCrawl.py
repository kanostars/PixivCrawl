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
import io
import zipfile
from PIL import Image

urllib3.disable_warnings()


def thread_it(func):
    thread = threading.Thread(target=func)
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
    mkdir = os.path.join(os.getcwd(), *base_dir)
    os.makedirs(mkdir, exist_ok=True)
    return mkdir


# 通过作品id下载
class ThroughArtWorkerId:
    def __init__(self, cookie_id, img_id, pixiv_app):
        self.img_id = img_id
        self.app = pixiv_app
        self.cookie = cookie_id if cookie_id != "" else cookie
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}
        self.url_illust = f"https://www.pixiv.net/ajax/illust/{img_id}"

    # 获取画师名字
    def getWorkerName(self):
        artworks_id = f"https://www.pixiv.net/artworks/{self.img_id}"
        requests_worker = requests.get(artworks_id, verify=False, headers=self.headers)
        request_if_error(requests_worker)
        soup = BeautifulSoup(requests_worker.text, 'html.parser')
        meta_tag = str(soup.find_all('meta')[-1])
        try:
            username = re.findall(f'"userName":"(.*?)"', meta_tag)[0]
            username = re.sub(r'[/\\| ]', '_', username)
        except IndexError:
            logging.warning("未找到该作品的画师~")
            return None
        return username

    def preDownLoad(self):
        logging.info(f"开始下载图片:{self.img_id}")
        # 如果没有文件夹，那就创建一个
        mkdir_artworks = create_directory("artworks_IMG")
        try:
            # 判断是否是动图
            session = requests.Session()
            response = session.get(url=f"{self.url_illust}/ugoira_meta",
                                   verify=False, headers=self.headers)
            data = response.json()
            if len(data['body']) == 0 and data["message"] != "您所指定的ID不是动图":
                logging.warning("未找到该插画~")
                return
            if data['error']:
                # 是静态图片
                self.download_static_images(session, mkdir_artworks)
            else:
                # 是动图
                self.download_ugoira(data, mkdir_artworks)
            logging.info("插画下载完成~")

        except json.decoder.JSONDecodeError:
            logging.warning("你的cookie信息已过期")

    # 下载静态图片
    def download_static_images(self, session, mkdir_static):
        response = session.get(url=self.url_illust + "/pages", verify=False, headers=self.headers)
        request_if_error(response)
        static_url = json.loads(response.text)['body']  # 静态图的url
        if len(static_url) > 1:
            mkdir_static = create_directory("artworks_IMG", self.img_id)
        logging.info(f"一共{len(static_url)}张插画，正在下载~")

        # 计算文件总大小，更新进度条最大值
        total_size = sum(
            int(requests.head(url['urls']['original'], headers=self.headers, verify=False).headers.get(
                'content-length', 0)) for url in static_url)
        self.app.update_progress_bar(0, total_size)  # 初始化进度条
        # 使用多线程下载图片
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = []
            for ID in static_url:
                href1 = ID['urls']['original']
                futures.append(executor.submit(self.download_image, href1, mkdir_static))

            # 等待所有任务完成
            for future in as_completed(futures):
                future.result()

    def download_image(self, url, mkdirs):
        file_path = os.path.join(mkdirs, f"@{self.getWorkerName()} {os.path.basename(url)}")
        session = requests.Session()
        download_response = session.get(url=url, headers=self.headers, verify=False, stream=True)
        request_if_error(download_response)
        with open(file_path, "wb") as f:
            for data in download_response.iter_content(chunk_size=1024):
                f.write(data)
                self.app.update_progress_bar(len(data))  # 更新进度条

    # 下载动图
    def download_ugoira(self, data, mkdirs):
        logging.info("该作品为gif，正在下载~")
        delays = [frame['delay'] for frame in data['body']['frames']]  # 动图每张图片的帧延迟时间
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = [executor.submit(self.download_gif, data['body']['originalSrc'], mkdirs, delays)]
            for future in as_completed(futures):
                future.result()

    def download_gif(self, url, mkdirGif, delays):
        file_path = os.path.join(mkdirGif, f"@{self.getWorkerName()} {self.img_id}.gif")
        response = requests.get(url, headers=self.headers, verify=False)
        request_if_error(response)
        zip_content = io.BytesIO(response.content)
        total_size = len(response.content)
        self.app.update_progress_bar(0, total_size)
        # 在内存中解压ZIP文件
        with zipfile.ZipFile(zip_content, 'r') as zip_ref:
            image_files = [f for f in zip_ref.namelist() if f.endswith(('.png', '.jpg', '.jpeg'))]
            image_files.sort()

            # 设置更新阈值，每下载或处理1MB就更新一次进度条
            update_threshold = 1024 * 1024

            # 读取图片并合成GIF
            images = []
            for image_file in image_files:
                with zip_ref.open(image_file) as image_file_obj:
                    image = Image.open(image_file_obj)
                    image.load()
                    images.append(image)
                    processed_size = len(image_file_obj.read())
                    # 如果处理的字节数超过阈值，则更新进度条
                    if processed_size >= update_threshold:
                        self.app.update_progress_bar(processed_size)

        # 合成GIF
        if images:
            images[0].save(
                file_path,
                save_all=True,
                append_images=images[1:],
                duration=delays,  # 帧延迟时间（毫秒）
                loop=0  # 循环次数，0表示无限循环
            )
        self.app.update_progress_bar(total_size)


# 通过画师id下载
class ThroughWorkerId:
    def __init__(self, cookie_id, users_id, pixiv_app):
        self.mkdirs_workers = ""
        self.users_id = users_id
        self.app = pixiv_app
        self.cookie = cookie_id if cookie_id != "" else cookie
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}
        self.url_illust = f"https://www.pixiv.net/ajax/illust"

    # 获取画师名字
    def getWorkerName(self):
        worker_url = f'https://www.pixiv.net/users/{self.users_id}'
        response = requests.get(worker_url, headers=self.headers, verify=False)
        request_if_error(response)
        soup = BeautifulSoup(response.text, 'html.parser')
        title = str(soup.title.string)
        try:
            name = re.findall(r'(.*?) - pixiv', title)[0]
            name = re.sub(r'[/\\| ]', '_', name)
            return name
        except IndexError:
            logging.warning("未找到该画师,请重新输入~")

    # 获取图片全部id(是个列表)
    def getImgId(self):
        id_url = f"https://www.pixiv.net/ajax/user/{self.users_id}/profile/all?lang=zh"
        response = requests.get(id_url, headers=self.headers, verify=False)
        request_if_error(response)
        return re.findall(r'"(\d+)":null', response.text)

    # 找到下载链接,开爬
    def preDownload(self):
        try:
            # 如果没有文件夹，那就创建一个
            self.mkdirs_workers = create_directory("workers_IMG", self.getWorkerName())
            # self.mkdirs_workers = os.path.join(os.getcwd(), "workers_IMG", self.getWorkerName())
            # os.makedirs(self.mkdirs_workers, exist_ok=True)

            listId = self.getImgId()
            logging.info(f"大概下载图片数: {len(listId)}+")

            # 开始下载
            logging.info("正在检索并下载中，请稍后(进度条会有点延迟)。。。")
            self.app.update_progress_bar(0, len(listId))  # 初始化进度条
            with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                futures = [executor.submit(self.download_image_or_gif, img_id) for img_id in listId]
                for future in as_completed(futures):
                    future.result()
                    self.app.update_progress_bar(1)  # 更新进度条
            logging.info(f"下载完成，共有{len(os.listdir(self.mkdirs_workers))}张图片~")
        except TypeError:
            logging.warning("输入的画师id有误或不存在，也可能是你cookie失效了，换一个吧~")
        except Exception as e:
            logging.critical(f"发生了一个错误: {e}")

    # 下载静态图片或动图
    def download_image_or_gif(self, img_id):
        time.sleep(random.uniform(1, 5))
        ugoira_url = f"{self.url_illust}/{img_id}/ugoira_meta"
        session = requests.Session()
        response = session.get(url=ugoira_url, headers=self.headers, verify=False)
        data = response.json()

        # 判断是否为动图
        if data['error']:
            self.download_static_images(session, img_id)
        else:
            self.download_ugoira(data, img_id)

    # 下载静态图片
    def download_static_images(self, session, img_id):
        response = session.get(url=f"{self.url_illust}/{img_id}/pages", verify=False, headers=self.headers)
        request_if_error(response)
        static_url = json.loads(response.text)['body']

        # 使用多线程下载图片
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = []
            for ID in static_url:
                href1 = ID['urls']['original']
                futures.append(executor.submit(self.download_image, href1))

            # 等待所有任务完成
            for future in as_completed(futures):
                future.result()

    def download_image(self, url):
        file_path = os.path.join(self.mkdirs_workers, f"@{self.getWorkerName()} {os.path.basename(url)}")
        session = requests.Session()
        download_response = session.get(url=url, headers=self.headers, verify=False, stream=True)
        request_if_error(download_response)
        with open(file_path, "wb") as f:
            for data in download_response.iter_content(chunk_size=1024):
                f.write(data)

    # 下载动图
    def download_ugoira(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = [executor.submit(self.download_gif, data['body']['originalSrc'], img_id, delays)]
            for future in as_completed(futures):
                future.result()

    def download_gif(self, url, img_id, delays):
        file_path = os.path.join(self.mkdirs_workers, f"@{self.getWorkerName()} {img_id}.gif")
        response = requests.get(url, headers=self.headers, verify=False)
        request_if_error(response)
        zip_content = io.BytesIO(response.content)

        with zipfile.ZipFile(zip_content, 'r') as zip_ref:
            image_files = [f for f in zip_ref.namelist() if f.endswith(('.png', '.jpg', '.jpeg'))]
            image_files.sort()

            images = []
            for image_file in image_files:
                with zip_ref.open(image_file) as image_file_obj:
                    image = Image.open(image_file_obj)
                    image.load()
                    images.append(image)


        if images:
            images[0].save(
                file_path,
                save_all=True,
                append_images=images[1:],
                duration=delays,
                loop=0
            )


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
                logging.warning('输入的画师id不能为空~~')
                return
            if self.isWorkers():
                webbrowser.open(f"https://www.pixiv.net/users/{workerId}")
            ThroughWorkerId(cookieID, workerId, app).preDownload()
        except requests.exceptions.ConnectTimeout:
            logging.warning("网络请求失败，用加速器试试，提个醒，别用代理工具~")
        except requests.exceptions.RequestException as e:
            logging.warning(f"网络请求失败: {e}")
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
                logging.warning('输入的插画id不能为空~~')
                return
            if self.isArtworks():
                webbrowser.open(f"https://www.pixiv.net/artworks/{ImgId}")
            ThroughArtWorkerId(cookieID, ImgId, app).preDownLoad()
        except requests.exceptions.ConnectTimeout:
            logging.warning("网络请求失败，用加速器试试，提个醒，别用代理工具~")
        except requests.exceptions.RequestException as e:
            logging.warning(f"网络请求失败: {e}")
        finally:
            self.button1.config(state=NORMAL)
            self.button2.config(state=NORMAL)

    def update_progress_bar(self, increment, total=0):
        if total:  # 设置进度条最大值
            self.total_progress = total
            self.progress_bar["maximum"] = total
            self.current_progress = 0
            self.progress_bar.update()
        else:  # 更新进度条值
            self.current_progress += increment
            self.progress_bar.update()  # 刷新UI显示
        self.progress_bar["value"] = self.current_progress


if __name__ == '__main__':
    cookie = "first_visit_datetime_pc=2024-10-28%2015%3A47%3A50; cc1=2024-10-28%2015%3A47%3A50; yuid_b=MDhIaSQ; p_ab_id=0; p_ab_id_2=5; p_ab_d_id=1010825385; _gid=GA1.2.304787948.1730098076; __cf_bm=fZzbZtN_g0ZDTf9n52iWLMFU1WEmnH81VoV8Wd0rEDc-1730098595-1.0.1.1-Xl9cDP.mcn0FfInILgvhzFksOEa9XkK1y.8aRkk9Q17sX3wOkYRaZVYa.zMZyrSqEqSLMdPG_JuZ6drTARrK8SZAIoSmfnz7q3MC5bo5OcI; cf_clearance=ItF6dTW2176VOIpbIzYu7nsHOq3SvOKTrhUwMLVxIkw-1730098596-1.2.1.1-NT_Me9C2T7ME8DKrqu27..qbQVeH07eHpdrfJV.Rgl0wTK9QWA2x2vf.sfSa8VTTzj1yaeQeEFt1LwNNg1_EtMhQndt7p_Lfc6yeuLOROXhLref_.iHu.xKJ19NQe7ziH0sJXQyHDhnGKNdkV6TooYGK8MtVIfIpz1DKovd6jQBtGDS1PAC4G.hNugmNSF0vB6zcMvuUvQ2RztdZIAYHGTK2X1Eu2PVUoS6AP_ee01M..q2NH49wfDO.m6pJZgvHwvvdbLa5AxGwRuXvRt5_QZT2zWy5R5sF7.B59W8.JBekKbBHVZxazp11erzDwmmeuvKr_xtDFVscXQRNfxjs38T9FFumAchzGA_catoR8xRErCL4YEi5pmo3aFSnmXYq8p2SOY2WowQwGv7ePWtd4A; PHPSESSID=55796473_fl4Q8QxUzGAGEZPTJTTZBGlHp9S52OVF; device_token=f8e45aad75360f69b925b28a89135872; privacy_policy_agreement=7; _ga_MZ1NL4PHH0=GS1.1.1730098551.1.1.1730098603.0.0.0; c_type=31; privacy_policy_notification=0; a_type=0; b_type=1; login_ever=yes; _ga=GA1.1.1043447830.1730098071; _ga_75BBYNYN9J=GS1.1.1730098070.1.1.1730099005.0.0.0"
    # cookie = "first_visit_datetime_pc=2024-03-25%2023%3A22%3A07; p_ab_id=7; p_ab_id_2=4; p_ab_d_id=170919518; yuid_b=NWcCYEc; c_type=31; privacy_policy_notification=0; a_type=0; b_type=1; login_ever=yes; __utmv=235335808.|2=login%20ever=yes=1^3=plan=normal=1^6=user_id=55796473=1^9=p_ab_id=7=1^10=p_ab_id_2=4=1^11=lang=zh=1; privacy_policy_agreement=7; first_visit_datetime=2024-09-28%2022%3A53%3A28; webp_available=1; _ga_3WKBFJLFCP=GS1.1.1727531608.1.0.1727531610.0.0.0; _gid=GA1.2.259876661.1729870123; __utma=235335808.2067325330.1711376549.1712414350.1730007067.2; __utmz=235335808.1730007067.2.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); _gcl_au=1.1.1599279373.1730037390; device_token=cfd3583f48fcd27e771de19dda7cc785; __cf_bm=1A.CeFXLk6V.UymC4pAK0u4fWeZ7u3Rct4DbvzS4egY-1730037583-1.0.1.1-s3YCP0aq658h6dAczfwGJU6LOM5xvRdy5nueuJ_dGx4WH7LoQ9ccbEDKetl9zSSNa7QfW889l_c.Zo.KYBw_jxWBnd2r7bG0NWAYCW7hSMA; cf_clearance=ls8LDfx_yN8ubL7X.RHHELyEyKtMxE_N42rsJ8MK40k-1730037584-1.2.1.1-XYaeLESjNYukegE6QpScxSizjcAy0Qj_gpui6oXC.pr8NaLyPqZGVyKo9ZQcTq4TzJrn7UL4uOPGPsvUpO3636dKYwqRHXygAfkgrrPwce91sF0V7HXBf1IsYC.2bg0SIfiFuxuDEI04Miu0ILJ8h1i9ZCJrBuVJC3da8oaE24IocjlYLanscJndzjSeuwWa_IJqtycXiVdBXO4Q6_e4RNOFM_kVoe23qNHT5Y7gRZKNe0v0YXaaGC2rTKHkKoVCsSJ0Z14jp5m1FsfGgFubxM1A3S1zWg.NEJCTAnpuWHHjTaFhXAbMfqg7KmdrvLVOFapXaA5SSLzdszt0xdB8LFDzposXH_qLB3NThtmk6o.bT.tNtjJARTwoFOiX2LTVDeH8b0pNiMtxBzsG_NFsIQ; cc1=2024-10-27%2023%3A05%3A51; PHPSESSID=55796473_m3c9lT52U2ZCgamnHWBCOdXUDVfKRGYS; _ga_MZ1NL4PHH0=GS1.1.1730037393.10.1.1730037965.0.0.0; _ga=GA1.2.2067325330.1711376549; _gat_UA-1830249-3=1; _ga_75BBYNYN9J=GS1.1.1730035841.61.1.1730038499.0.0.0"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    root = Tk()
    app = PixivApp(root)

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

    root.mainloop()
