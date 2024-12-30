import json
import logging
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import *

import requests
from PIL import Image
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from FileOrDirHandler import FileHandler

TYPE_WORKER = "artist"  # 类型是画师
TYPE_ARTWORKS = "artWork"  # 类型是插画
user_agent = FileHandler.read_json()["user_agent"]


# p站图片下载器
class PixivDownloader:
    def __init__(self, cookie_id, pixiv_app):
        self.app = pixiv_app
        self.type = ""  # 输入的id类型
        self.artist = ""  # 画师名字
        self.mkdirs = ""  # 存放图片的文件夹
        self.numbers = 0  # 图片数量
        self.cookie = f'PHPSESSID={cookie_id}'
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}
        self.download_queue = []  # 下载队列
        self.download_size = 1024 * 1024  # 每次下载的大小
        self.need_com_gif = {}  # 需要合成的动图
        self.s = requests.Session()

        # 配置HTTP和HTTPS连接的池和重试策略
        adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=5)
        self.s.mount('http://', adapter)
        self.s.mount('https://', adapter)

    def download_and_save_image(self, url, save_path, start_size, end_size):
        # 根据起始和结束位置构建HTTP请求的Range头
        byte_range = f'bytes={start_size}-{end_size}'
        d_headers = {
            'User-Agent': user_agent,
            'referer': 'https://www.pixiv.net/',
            'Range': byte_range
        }

        if start_size == '':
            logging.debug("Range头删除")
            d_headers.pop('Range', None)

        resp = self.s.get(url, headers=d_headers, verify=False)
        try:
            length = int(resp.headers['Content-Length'])
        except KeyError:
            length = 0
        logging.debug(f'start_size：{start_size}  end_size：{end_size}  length：{length}')

        if type(start_size) == int and length > end_size - start_size + 1:
            with open(save_path, 'rb+') as f:
                f.seek(0, 0)
                f.write(resp.content)
            self.app.update_progress_bar(1)  # 更新进度条
            return

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
                self.mkdirs = FileHandler.create_directory("workers_IMG", self.artist)
            elif self.type == TYPE_ARTWORKS:  # 类型是通过插画id
                self.mkdirs = FileHandler.create_directory("artworks_IMG", img_ids[0])

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
                    logging.debug(f"{url} {save_path} {start_size} {end_size}")
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
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException:
            logging.error(f"请求失败，状态码: {response.status_code}")
        # 解析响应以获取所有静态图片的URL
        static_url = json.loads(response.text)['body']
        for urls in static_url:
            # 原始分辨率图片的URL
            url = urls['urls']['original']
            name = os.path.basename(url)
            file_path = os.path.join(self.mkdirs, f"@{self.artist} {name}")
            FileHandler.touch(file_path)
            resp = self.s.get(url=url, headers=self.headers, verify=False)

            self.add_download_queue(url, file_path, resp)

    def download_gifs(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.mkdirs, name)
        FileHandler.touch(file_path)
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
            self.download_queue.append((url, file_path, i, length - 1))
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


# 通过输入框获取id并准备下载图片
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