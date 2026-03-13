import json
import logging
import os
import random
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from urllib3.util.retry import Retry
from PIL import Image
from requests.adapters import HTTPAdapter

from FileHandlerManager import FileHandlerManager
from DownloadHistoryManager import DownloadHistoryManager
from config import TYPE_WORKER, TYPE_ARTWORKS, user_agent, cookies, languages, TYPE_COLLECTION, TYPE_NOVEL


def get_page_content():
    headers = {
        'Cookie': cookies,
        'Referer': 'https://www.pixiv.net/',
        'User-Agent': user_agent,
    }

    return requests.get(
        'https://www.pixiv.net/',
        headers=headers,
        verify=False
    )


def get_username(res):
    try:
        page_content = res if isinstance(res, str) else res.text
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                          page_content, re.DOTALL)
        if not match:
            raise ValueError("未找到页面中的__NEXT_DATA__脚本")

        next_data = json.loads(match.group(1))
        user_data = json.loads(next_data['props']['pageProps']['serverSerializedPreloadedState'])
        if not (user_data.get('userData') and user_data['userData'].get('self')):
            raise ValueError("响应中缺少userData或self字段")
        return user_data['userData']['self']['name']

    except requests.exceptions.Timeout:
        logging.debug("请求超时：请检查网络连接")
        logging.warning("获取用户名超时，请确认网络正常后重试")
        return None
    except requests.exceptions.RequestException as e:
        logging.debug(f"网络请求失败: {str(e)}")
        logging.warning("获取用户名失败，请检查网络连接后重新登录")
        return None
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logging.debug(f"数据解析错误: {type(e).__name__} - {str(e)}")
        logging.warning("解析用户数据失败，请重新登录")
        return None
    except Exception as e:
        logging.debug(f"未预期错误: {type(e).__name__} - {str(e)}")
        logging.warning("获取用户名时发生未知错误")
        return None


# 令牌桶限速器，控制每秒最大请求数
class RateLimiter:
    def __init__(self, rate_per_second=3):
        self.rate = rate_per_second
        self.tokens = rate_per_second
        self.last_time = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            # 补充令牌
            self.tokens += (now - self.last_time) * self.rate
            self.tokens = min(self.tokens, self.rate)  # 最多存rate个令牌
            self.last_time = now

            if self.tokens >= 1:
                self.tokens -= 1
                return
            # 令牌不足，等待
            wait_time = (1 - self.tokens) / self.rate
        time.sleep(wait_time)
        self.acquire()


# p站资源下载器
class PixivDownloader:
    def __init__(self, pixiv_app, id):
        self.app = pixiv_app
        self.id = id
        self.type = ""  # 输入的id类型
        self.artist = ""  # 画师名字
        self.mkdirs = ""  # 存放图片的文件夹
        self.numbers = 0  # 图片数量
        self.cookie = cookies
        self.headers = {'referer': "https://www.pixiv.net/", 'user-agent': user_agent, 'cookie': self.cookie}
        self.download_queue = []  # 下载队列
        self.download_size = 1024 * 1024  # 每次下载的大小
        self.need_com_gif = {}  # 需要合成的动图
        self.s = requests.Session()
        self.futures = []

        # 暂停与终止事件
        self.is_paused = threading.Event()
        self.is_stopped = threading.Event()

        # 文件写入锁，防止多线程写入同一文件时数据错乱
        self.file_locks = {}
        self.file_locks_lock = threading.Lock()

        # 追踪每个作品的下载完成状态
        self.artwork_download_status = {}  # {artwork_id: {"total": n, "completed": 0}}
        self.artwork_status_lock = threading.Lock()

        # 追踪文件分块下载状态
        self.file_chunk_status = {}  # {file_path: {"total_chunks": n, "completed_chunks": set()}}
        self.file_chunk_lock = threading.Lock()

        # 追踪已完成下载的作品ID
        self.completed_artworks = []  # 存储已完整下载的作品ID
        self.completed_artworks_lock = threading.Lock()

        self.api_limiter = RateLimiter(rate_per_second=4)

        self._configure_session_adapter()

        self.history_manager = None

    def _init_artwork_status(self, artwork_id, total_files):
        """初始化作品的下载状态追踪"""
        with self.artwork_status_lock:
            self.artwork_download_status[artwork_id] = {
                "total": total_files,
                "completed": 0,
                "files_completed": set()  # 追踪已完成的文件路径
            }

    def _mark_file_completed(self, artwork_id, file_path):
        """标记一个文件下载完成，如果作品所有文件都完成则保存到历史记录"""
        # 画师模式下才记录历史
        if artwork_id is None or not self.history_manager:
            return

        with self.artwork_status_lock:
            if artwork_id in self.artwork_download_status:
                status = self.artwork_download_status[artwork_id]

                # 如果这个文件还没有被标记为完成
                if file_path not in status["files_completed"]:
                    status["files_completed"].add(file_path)
                    status["completed"] += 1

                    # 检查该作品是否完全下载完成
                    if status["completed"] >= status["total"]:
                        # 检查是否是GIF动图（需要合成）
                        if artwork_id in self.need_com_gif:
                            # 是GIF动图，标记为等待合成，不立即保存历史记录
                            status["waiting_for_gif_composition"] = True
                            logging.debug(f"作品 {artwork_id} ZIP下载完成，等待GIF合成")
                        else:
                            # 普通静态图片，直接保存到历史记录
                            self.history_manager.add_artwork(artwork_id)
                            logging.debug(f"作品 {artwork_id} 下载完成，已保存到历史记录")
                            # 清理状态追踪
                            del self.artwork_download_status[artwork_id]

    def _mark_gif_composition_completed(self, artwork_id):
        """标记GIF合成完成，保存到历史记录"""
        # 画师模式下才记录历史
        if artwork_id is None or not self.history_manager:
            return

        with self.artwork_status_lock:
            if artwork_id in self.artwork_download_status:
                status = self.artwork_download_status[artwork_id]
                if status.get("waiting_for_gif_composition", False):
                    # GIF合成完成，现在可以保存到历史记录了
                    self.history_manager.add_artwork(artwork_id)
                    logging.debug(f"作品 {artwork_id} GIF合成完成，已保存到历史记录")
                    # 清理状态追踪
                    del self.artwork_download_status[artwork_id]

    def _check_file_completion(self, artwork_id, file_path, start_size, end_size):
        """检查文件的分块下载是否完成"""
        # 画师模式下才记录历史
        if artwork_id is None or not self.history_manager:
            return

        with self.file_chunk_lock:
            if file_path not in self.file_chunk_status:
                return  # 文件状态未初始化，可能是完整下载

            # 记录这个分块已完成
            chunk_key = f"{start_size}-{end_size}"
            self.file_chunk_status[file_path]["completed_chunks"].add(chunk_key)

            # 检查是否所有分块都完成了
            status = self.file_chunk_status[file_path]
            if len(status["completed_chunks"]) >= status["total_chunks"]:
                # 文件的所有分块都下载完成
                self._mark_file_completed(artwork_id, file_path)
                # 清理文件分块状态
                del self.file_chunk_status[file_path]

    def _configure_session_adapter(self):
        """配置Session的重试策略和连接池"""
        retry_strategy = Retry(
            total=5,
            backoff_factor=5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['HEAD', 'GET', 'OPTIONS'],
            respect_retry_after_header=True
        )
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=retry_strategy)
        self.s.mount('http://', adapter)
        self.s.mount('https://', adapter)

    def get_file_lock(self, save_path):
        """获取指定文件的锁，确保同一文件的写入操作是线程安全的"""
        with self.file_locks_lock:
            if save_path not in self.file_locks:
                self.file_locks[save_path] = threading.Lock()
            return self.file_locks[save_path]

    def download_and_save_image(self, url, save_path, start_size, end_size, artwork_id=None):
        time.sleep(random.uniform(0.5, 1.5))
        if not self.check_status():
            return

        file_lock = self.get_file_lock(save_path)

        # 处理完整下载
        if start_size == 0 and end_size == 0:
            try:
                resp = self.s.get(url, headers={'User-Agent': user_agent, 'referer': 'https://www.pixiv.net/'},
                                  stream=True)
                resp.raise_for_status()
                with file_lock:
                    with open(save_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                if not self.check_status():
                    return

                self.app.update_progress_bar(1)
                # 完整下载完成，标记文件完成
                self._mark_file_completed(artwork_id, save_path)
                return
            except Exception as e:
                logging.error(f"完整下载失败: {str(e)}")
                return

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

        if not self.check_status():
            return

        # 使用文件锁保护写入操作，确保分块按正确位置写入
        with file_lock:
            # 服务器不支持Range请求，返回了完整文件
            if type(start_size) == int and length > end_size - start_size + 1:
                with open(save_path, 'rb+') as f:
                    f.seek(0, 0)
                    f.write(resp.content)
                self.app.update_progress_bar(1)
                # 完整文件下载完成，标记文件完成
                self._mark_file_completed(artwork_id, save_path)
                return

            with open(save_path, 'rb+') as f:
                if start_size == '':
                    f.seek(0, 0)
                else:
                    f.seek(int(start_size), 0)
                f.write(resp.content)

        self.app.update_progress_bar(1)

        # 检查是否是该文件的最后一个分块
        self._check_file_completion(artwork_id, save_path, start_size, end_size)

    def download_resources(self, img_ids, t, sub_folder=None):
        try:
            self.type = t

            # 只在非收藏册类型和非小说时获取画师名字
            if self.type != TYPE_COLLECTION and self.type != TYPE_NOVEL:
                helper = MessageGetHelper(self.app, img_ids[0])
                self.artist = helper.get_worker_name_from_illusts(img_ids[0])
                self.artist = FileHandlerManager.sanitize_filename(self.artist)
                if self.artist is None:
                    return None
                logging.info(f"画师名字: {self.artist}")
            else:
                self.artist = ""  # 其他类型不需要画师名字

            if self.type == TYPE_WORKER:
                logging.info(f"正在查找图片总数，图片id集为{len(img_ids)}个...")
                # 如果指定了子文件夹，则在画师文件夹下创建子文件夹
                if sub_folder:
                    base_dir = FileHandlerManager.create_directory("workers_IMG", f'{self.artist}({self.id})')
                    self.mkdirs = FileHandlerManager.create_directory(base_dir, sub_folder)
                else:
                    self.mkdirs = FileHandlerManager.create_directory("workers_IMG", f'{self.artist}({self.id})')

                # 初始化历史记录管理器（使用画师根目录）
                base_dir = FileHandlerManager.create_directory("workers_IMG", f'{self.artist}({self.id})')
                self.history_manager = DownloadHistoryManager(base_dir)
                self.history_manager.update_metadata(self.id, self.artist)

                # 过滤已下载的作品
                downloaded_ids = self.history_manager.get_downloaded_ids()
                original_count = len(img_ids)
                img_ids = [img_id for img_id in img_ids if img_id not in downloaded_ids]
                skipped_count = original_count - len(img_ids)

                if skipped_count > 0:
                    logging.info(f"检测到已下载 {skipped_count} 个作品，将跳过")

                if len(img_ids) == 0:
                    logging.info("所有作品均已下载，无需重复下载")
                    return self.mkdirs
            elif self.type == TYPE_ARTWORKS:  # 类型是通过插画id
                self.mkdirs = FileHandlerManager.create_directory("artworks_IMG", img_ids[0])
                self.history_manager = None
            elif self.type == TYPE_COLLECTION:  # 类型是通过收藏册id
                if sub_folder:
                    self.mkdirs = sub_folder
                else:
                    self.mkdirs = FileHandlerManager.create_directory("collections_IMG", self.id)
                # 画师模式下保留历史记录管理器
                if not hasattr(self, 'history_manager') or self.history_manager is None:
                    self.history_manager = None
            elif self.type == TYPE_NOVEL:  # 如果类型是小说，则调用下载小说的逻辑
                if sub_folder:
                    self.mkdirs = sub_folder
                else:
                    self.mkdirs = FileHandlerManager.create_directory("novels")
                
                logging.info(f"正在下载 {len(img_ids)} 篇小说...")
                self.download_novel(img_ids)
                logging.info(f"小说下载完成~")
                
                # 画师模式下保留历史记录管理器
                if not hasattr(self, 'history_manager') or self.history_manager is None:
                    self.history_manager = None
                
                return self.mkdirs

            if self.type != TYPE_NOVEL:
                self.app.update_progress_bar(0, len(img_ids))
                self.download_by_art_worker_ids(img_ids)
                self.app.update_progress_bar(0, len(self.download_queue))  # 初始化进度条

                logging.info(f"检索结束...")

                if self.numbers == 0:
                    logging.warning("PHPSESSID已失效，请重新填写!")
                    return None

                logging.info(f"正在开始下载... 共{self.numbers}张图片...")
                self.app.update_progress_bar_color("green")

                with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 4)) as executor:
                    for (url, save_path, start_size, end_size, artwork_id) in self.download_queue:
                        if not self.check_status():
                            break
                        logging.debug(f"{url} {save_path} {start_size} {end_size} artwork_id={artwork_id}")
                        f = executor.submit(self.download_and_save_image, url, save_path, start_size, end_size,
                                            artwork_id)
                        self.futures.append(f)
                    for future in as_completed(self.futures):
                        try:
                            future.result()
                        except Exception as e:
                            logging.error(f"下载任务异常: {e}")

                if len(self.need_com_gif) > 0:
                    logging.info(f"开始合成动图，数量:{len(self.need_com_gif)}")
                    self.app.update_progress_bar_color("yellow")
                    self.app.update_progress_bar(0, len(self.need_com_gif))
                    for img_id in self.need_com_gif:
                        if not self.check_status():
                            break
                        self.comp_gif(img_id)
                        self.app.update_progress_bar(1)

                total_files = len(os.listdir(self.mkdirs))
                logging.info(f"下载完成，文件夹内共有{total_files}张图片~")

            if self.type == TYPE_WORKER and hasattr(self, 'history_manager') and self.history_manager:
                total_downloaded = self.history_manager.history_data["total_count"]
                newly_downloaded = len(img_ids)
                logging.info(f"本次新增: {newly_downloaded} 张，历史累计: {total_downloaded} 张")
            return self.mkdirs
        except IndexError:
            logging.warning("未找到该画师,请重新输入~")
            return None

    def download_by_art_worker_ids(self, img_ids):
        with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 6)) as executor:
            for img_id in img_ids:
                if not self.check_status():
                    break
                f = executor.submit(self.download_by_art_worker_id, img_id)
                self.futures.append(f)
            for future in as_completed(self.futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"检索任务异常: {e}")

    def download_by_art_worker_id(self, img_id):
        if not self.check_status():
            return
        self.api_limiter.acquire()
        ugoira_url = f"https://www.pixiv.net/ajax/illust/{img_id}/ugoira_meta"
        response = self.s.get(url=ugoira_url, headers=self.headers, verify=False)
        data = response.json()
        if data['error']:  # 是静态图
            self.download_static_images(img_id)
        else:  # 是动图
            self.download_gifs(data, img_id)

        if not self.check_status():
            return

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

        # 初始化该作品的下载状态追踪
        self._init_artwork_status(img_id, len(static_url))

        for urls in static_url:
            # 原始分辨率图片的URL
            url = urls['urls']['original']
            name = os.path.basename(url)
            # 收藏册类型不需要添加画师名字
            if self.type == TYPE_COLLECTION:
                file_path = os.path.join(self.mkdirs, name)
            else:
                file_path = os.path.join(self.mkdirs, f"@{self.artist} {name}")
            FileHandlerManager.touch(file_path)
            resp = self.s.get(url=url, headers=self.headers, verify=False)

            self.add_download_queue(url, file_path, resp, img_id)

    def download_gifs(self, data, img_id):
        delays = [frame['delay'] for frame in data['body']['frames']]  # 帧延迟信息
        url = data['body']['originalSrc']  # GIF图像的原始URL
        # 收藏册类型不需要添加画师名字
        if self.type == TYPE_COLLECTION:
            name = f"{img_id}.zip"
        else:
            name = f"@{self.artist} {img_id}.zip"
        file_path = os.path.join(self.mkdirs, name)
        FileHandlerManager.touch(file_path)
        self.need_com_gif[img_id] = delays

        # 初始化该作品的下载状态追踪（动图只有1个文件）
        self._init_artwork_status(img_id, 1)

        resp = self.s.get(url, headers=self.headers, verify=False)
        self.add_download_queue(url, file_path, resp, img_id)

    def comp_gif(self, img_id):
        delays = self.need_com_gif[img_id]
        if self.type == TYPE_COLLECTION:
            name = f"{img_id}.gif"
            o_name = f"{img_id}.zip"
        else:
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

        # GIF合成完成，现在可以保存历史记录了
        self._mark_gif_composition_completed(img_id)

    def download_novel(self, ids):
        self.app.update_progress_bar(0, len(ids))
        self.app.update_progress_bar_color("green")
        
        for i, id in enumerate(ids, 1):
            if not self.check_status():
                break
                
            try:
                response = self.s.get(url=f"https://www.pixiv.net/ajax/novel/{id}?lang=zh", headers=self.headers,
                                      verify=False)
                response.raise_for_status()
                datas = response.json()['body']
                title = datas['title']
                username = datas['userName']
                content = datas['content']

                # 清理文件名中的非法字符
                safe_title = FileHandlerManager.sanitize_filename(title)
                safe_username = FileHandlerManager.sanitize_filename(username)
                
                filename = f"《{safe_title}》- {safe_username}.txt"
                filepath = os.path.join(self.mkdirs, filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # 更新进度条
                self.app.update_progress_bar(1)
                logging.info(f'小说 {i}/{len(ids)}：《{title}》下载完毕。')
                
            except Exception as e:
                logging.error(f'下载小说 {id} 失败: {str(e)}')
                # 即使失败也要更新进度条
                self.app.update_progress_bar(1)

    def add_download_queue(self, url, file_path, response, artwork_id=None):
        self.numbers += 1
        try:
            length = int(response.headers.get('Content-Length', 0))

            if length == 0:
                self.download_queue.append((url, file_path, 0, 0, artwork_id))
                logging.debug(f"未获取到有效文件大小，直接下载整个文件: {url}")
                return

            # 计算分块数量并初始化文件分块状态
            chunk_count = 0
            i = 0
            while i < length:
                end = min(i + self.download_size - 1, length - 1)
                self.download_queue.append((url, file_path, i, end, artwork_id))
                chunk_count += 1
                i += self.download_size

            # 初始化文件分块状态追踪（画师模式下）
            if artwork_id and self.history_manager:
                with self.file_chunk_lock:
                    self.file_chunk_status[file_path] = {
                        "total_chunks": chunk_count,
                        "completed_chunks": set()
                    }

        except KeyError:
            # 如果无法获取文件大小，则对整个文件不分块下载
            logging.debug(f"无法获取文件大小，将使用整个文件下载,url:{url}")
            self.download_queue.append((url, file_path, 0, 0, artwork_id))

    def stop_all_tasks(self):
        logging.info("正在停止所有下载任务...")
        self.is_stopped.set()
        # 取消所有未完成任务
        for future in self.futures:
            future.cancel()
        # 关闭网络会话
        self.s.close()
        logging.debug("所有下载线程已强制终止")

    def reset_session(self):
        logging.info("会话已重置")
        self.s.close()
        self.s = requests.Session()
        self._configure_session_adapter()

    def check_status(self):
        if self.is_stopped.is_set():
            logging.debug("检测到停止信号，终止下载")
            return False
        while self.is_paused.is_set():
            time.sleep(1)
        return True


# 通过输入框获取id并准备下载图片
class ThroughId(PixivDownloader):
    def __init__(self, id, pixiv_app, t):
        super().__init__(pixiv_app, id)
        self.id = id
        self.types = t if isinstance(t, list) else [t]  # 支持类型列表
        self.type = self.types[0] if self.types else ""  # 保持兼容性，主类型

    def pre_download(self):
        is_worker_mode = TYPE_WORKER in self.types

        if is_worker_mode:
            # 画师模式：下载画师的多种类型作品
            logging.info(f"画师模式 - ID: {self.id}")
            path = self._download_worker_with_types()
            logging.info("存放路径：" + path)
            return path
        else:
            # 独立作品模式：下载单个作品
            path = self._download_single_work()
            logging.info("存放路径：" + path)
            return path

    def _download_worker_with_types(self):
        """画师模式：下载画师的指定类型作品"""
        logging.info(f"正在通过画师ID({self.id})检索作品...")

        helper = MessageGetHelper(self.app, self.id)
        all_ids = helper.get_img_ids_user()

        if not all_ids:
            logging.warning("未找到该画师的作品")
            return None

        # 根据选中的类型过滤作品
        selected_types = [t for t in self.types if t != TYPE_WORKER]

        # 收集要下载的作品ID
        illusts_to_download = []
        novels_to_download = []
        collections_to_download = []
        type_names = []

        if TYPE_ARTWORKS in selected_types:
            illusts = all_ids.get("illusts", [])
            illusts_to_download = illusts
            if illusts:
                type_names.append(f"插画({len(illusts)})")
                logging.info(f"找到 {len(illusts)} 个插画作品")
            else:
                logging.warning("该画师没有插画作品")

        if TYPE_NOVEL in selected_types:
            novels = all_ids.get("novels", [])
            novels_to_download = novels
            if novels:
                type_names.append(f"小说({len(novels)})")
                logging.info(f"找到 {len(novels)} 个小说作品")
            else:
                logging.warning("该画师没有小说作品")

        if TYPE_COLLECTION in selected_types:
            collections = all_ids.get("collections", [])
            collections_to_download = collections
            if collections:
                type_names.append(f"珍藏册({len(collections)})")
                logging.info(f"找到 {len(collections)} 个珍藏册")
            else:
                logging.warning("该画师没有珍藏册")

        if not illusts_to_download and not novels_to_download and not collections_to_download:
            logging.warning("没有找到符合条件的作品")
            return None

        # 用于存储最终返回的路径
        final_path = None

        # 下载插画作品
        if illusts_to_download:
            logging.info(f"开始下载插画作品...")
            result_path = self.download_resources(illusts_to_download, TYPE_WORKER, sub_folder="artworks")
            if result_path:
                final_path = os.path.dirname(result_path) if os.path.basename(
                    result_path) == "artworks" else result_path

        # 下载珍藏册
        if collections_to_download:
            logging.info(f"开始下载珍藏册...")
            # 获取画师名字（如果还没有）
            if not self.artist:
                if len(collections_to_download) > 0:
                    helper = MessageGetHelper(self.app, collections_to_download[0])
                    self.artist = helper.get_artist_name_from_collection(collections_to_download[0])
                else:
                    self.artist = 'Unknown'
                self.artist = FileHandlerManager.sanitize_filename(self.artist)

            if self.artist:
                base_dir = FileHandlerManager.create_directory("workers_IMG", f'{self.artist}({self.id})')

                # 初始化历史记录管理器（如果还没有）
                if not self.history_manager:
                    self.history_manager = DownloadHistoryManager(base_dir)
                    self.history_manager.update_metadata(self.id, self.artist)

                # 为每个珍藏册创建子文件夹并下载
                for collection_id in collections_to_download:
                    # 检查是否已下载
                    if collection_id in self.history_manager.get_downloaded_ids():
                        logging.info(f"珍藏册 {collection_id} 已下载，跳过")
                        continue

                    # 获取珍藏册中的作品ID
                    helper = MessageGetHelper(self.app, collection_id)
                    collection_artworks = helper.get_img_ids_collection_by_id(collection_id)
                    if collection_artworks:
                        collection_folder = FileHandlerManager.create_directory(base_dir,
                                                                                f"collections/{collection_id}")

                        # 临时保存当前类型和目录
                        original_type = self.type
                        original_mkdirs = self.mkdirs

                        # 下载珍藏册中的作品
                        self.mkdirs = collection_folder
                        self.type = TYPE_COLLECTION

                        # 下载珍藏册中的图片
                        self.app.update_progress_bar(0, len(collection_artworks))
                        self.download_by_art_worker_ids(collection_artworks)
                        self.app.update_progress_bar(0, len(self.download_queue))

                        if self.numbers > 0:
                            logging.info(f"正在下载珍藏册 {collection_id}，共{self.numbers}张图片...")
                            self.app.update_progress_bar_color("green")

                            # 用于追踪本次下载的futures和成功计数
                            collection_futures = []
                            successful_downloads = 0
                            expected_downloads = len(self.download_queue)
                            
                            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), 4)) as executor:
                                for (url, save_path, start_size, end_size, artwork_id) in self.download_queue:
                                    if not self.check_status():
                                        break
                                    f = executor.submit(self.download_and_save_image, url, save_path, start_size,
                                                        end_size, None)
                                    self.futures.append(f)
                                    collection_futures.append(f)
                                
                                # 等待所有下载任务完成并统计成功数量
                                for future in as_completed(collection_futures):
                                    try:
                                        future.result()
                                        successful_downloads += 1
                                    except Exception as e:
                                        logging.error(f"下载任务异常: {e}")

                            # 处理动图合成
                            gif_success = True
                            if len(self.need_com_gif) > 0:
                                logging.info(f"开始合成动图，数量:{len(self.need_com_gif)}")
                                self.app.update_progress_bar_color("yellow")
                                self.app.update_progress_bar(0, len(self.need_com_gif))
                                for img_id in self.need_com_gif:
                                    if not self.check_status():
                                        gif_success = False
                                        break
                                    try:
                                        self.comp_gif(img_id)
                                        self.app.update_progress_bar(1)
                                    except Exception as e:
                                        logging.error(f"合成动图 {img_id} 失败: {e}")
                                        gif_success = False

                            # 验证下载完成情况
                            download_complete = (
                                successful_downloads == expected_downloads and 
                                gif_success and 
                                not self.is_stopped.is_set()
                            )
                            
                            logging.info(f"珍藏册 {collection_id} 下载统计: 成功 {successful_downloads}/{expected_downloads}, GIF合成: {'成功' if gif_success else '失败'}")

                        else:
                            # 没有图片需要下载，认为是完成的
                            download_complete = True
                            logging.info(f"珍藏册 {collection_id} 没有新图片需要下载")

                        # 恢复原始类型和目录
                        self.type = original_type
                        self.mkdirs = original_mkdirs

                        # 只有在完全下载成功的情况下才记录珍藏册到历史
                        if download_complete:
                            self.history_manager.add_collection(collection_id)
                            logging.info(f"珍藏册 {collection_id} 完全下载完成，已记录到历史")
                        else:
                            logging.warning(f"珍藏册 {collection_id} 下载不完整，不记录到历史")

                        # 清空下载队列和动图列表
                        self.download_queue = []
                        self.need_com_gif = {}
                        self.numbers = 0

                if not final_path:
                    final_path = base_dir

        # 下载小说
        if novels_to_download:
            logging.info(f"开始下载小说...")

            # 获取画师名字（如果还没有）
            if not self.artist:
                if novels_to_download:
                    helper = MessageGetHelper(self.app, novels_to_download[0])
                    self.artist = helper.get_worker_name_from_novel(novels_to_download[0])
                    self.artist = FileHandlerManager.sanitize_filename(self.artist)
            if self.artist:
                base_dir = FileHandlerManager.create_directory("workers_IMG", f'{self.artist}({self.id})')

                # 初始化历史记录管理器（如果还没有）
                if not self.history_manager:
                    self.history_manager = DownloadHistoryManager(base_dir)
                    self.history_manager.update_metadata(self.id, self.artist)

                # 过滤已下载的小说
                downloaded_ids = self.history_manager.get_downloaded_ids()
                novels_to_download = [novel_id for novel_id in novels_to_download if novel_id not in downloaded_ids]

                if novels_to_download:
                    novel_folder = FileHandlerManager.create_directory(base_dir, "novels")
                    self.download_resources(novels_to_download, TYPE_NOVEL, sub_folder=novel_folder)

                    # 记录小说到历史
                    for novel_id in novels_to_download:
                        self.history_manager.add_novel(novel_id)

                    if not final_path:
                        final_path = base_dir
                else:
                    logging.info("所有小说均已下载，无需重复下载")

        return final_path

    def _download_single_work(self):
        """独立作品模式：下载单个作品"""
        work_type = self.types[0]

        if work_type == TYPE_ARTWORKS:
            log_msg = f"正在通过插画ID({self.id})检索图片..."
            img_ids = [self.id]
        elif work_type == TYPE_COLLECTION:
            log_msg = f"正在通过珍藏册ID({self.id})检索图片..."
            helper = MessageGetHelper(self.app, self.id)
            img_ids = helper.get_img_ids_collection() or []
        elif work_type == TYPE_NOVEL:
            log_msg = f"正在下载小说,id为：{self.id}"
            img_ids = [self.id]
        else:
            logging.critical(f"程序内部错误，无效的资源类型: {work_type}")
            raise ValueError(f"无效的资源类型: {work_type}")

        logging.info(log_msg)
        return self.download_resources(img_ids, work_type)


# 资源获取辅助类
class MessageGetHelper(PixivDownloader):
    def __init__(self, pixiv_app, id=None):
        super().__init__(pixiv_app, id)

    # 获取用户的所有作品id
    def get_img_ids_user(self):
        if not self.check_status():
            return {}
        id_url = f"https://www.pixiv.net/ajax/user/{self.id}/profile/all?lang=zh"
        try:
            response = requests.get(id_url, headers=self.headers, verify=False)
            if not self.check_status():
                return {}
            illusts_data = json.loads(response.text)['body']['illusts']
            novels_data = json.loads(response.text)['body']['novels']
            collections_data = json.loads(response.text)['body']['collections']

            return {
                "illusts": list(illusts_data.keys()) if illusts_data else [],
                "novels": list(novels_data.keys()) if novels_data else [],
                "collections": list(collections_data.keys()) if collections_data else []
            }
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return {}

    # 获取收藏册中的作品id
    def get_img_ids_collection(self):
        if not self.check_status():
            return []
        id_url = f"https://www.pixiv.net/ajax/collection/{self.id}?lang=zh"
        try:
            response = requests.get(id_url, headers=self.headers, verify=False)
            if not self.check_status():
                return []
            return [data['id'] for data in response.json()['body']['thumbnails']['illust']]
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return []

    # 根据珍藏册ID获取其中的作品ID列表
    def get_img_ids_collection_by_id(self, collection_id):
        if not self.check_status():
            return []
        id_url = f"https://www.pixiv.net/ajax/collection/{collection_id}?lang=zh"
        try:
            response = requests.get(id_url, headers=self.headers, verify=False)
            if not self.check_status():
                return []
            return [data['id'] for data in response.json()['body']['thumbnails']['illust']]
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            logging.debug(f"获取珍藏册 {collection_id} 失败: {e}")
            return []

    # 从珍藏册中获取画师名字
    def get_artist_name_from_collection(self, collection_id):
        if not self.check_status():
            return None
        id_url = f"https://www.pixiv.net/ajax/collection/{collection_id}?lang=zh"
        try:
            response = requests.get(id_url, headers=self.headers, verify=False)
            if not self.check_status():
                return None
            data = response.json()
            # 从收藏册的第一个作品中获取画师名字
            collections = data.get('body', {}).get('thumbnails', {}).get('collection', [])
            if collections and len(collections) > 0:
                artist_name = collections[0].get('userName')
                if artist_name:
                    logging.debug(f"从珍藏册 {collection_id} 获取到画师名字: {artist_name}")
                    return artist_name
            logging.warning(f"珍藏册 {collection_id} 中未找到画师名字")
            return None
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            logging.debug(f"从珍藏册 {collection_id} 获取画师名字失败: {e}")
            return None

    # 从插画中获取画师名字
    def get_worker_name_from_illusts(self, img_id):
        if not self.check_status():
            return None
        artworks_id = f"https://www.pixiv.net/artworks/{img_id}"
        requests_worker = self.s.get(artworks_id, headers=self.headers, verify=False)
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

    # 从小说中获取画师名字
    def get_worker_name_from_novel(self, novel_id):
        if not self.check_status():
            return None
        novel_id = f"https://www.pixiv.net/ajax/novel/{novel_id}?lang=zh"
        res = self.s.get(novel_id, headers=self.headers, verify=False)
        return res.json().get('body', {}).get('userName', None)
