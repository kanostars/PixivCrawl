import logging
import os
import threading
import time
import webbrowser
from tkinter import *
from tkinter import font as tkFont
from tkinter import ttk
from tkinter.ttk import Progressbar

from urllib3 import disable_warnings

from api.pixiv_api import PixivAPI
from auth import LoginManager, SessionManager
from config.settings import (
    TYPE_NOVEL, TYPE_USER, TYPE_COLLECTION, TYPE_ARTWORK,
    ensure_directories
)
from download.download_manager import DownloadManager
from download.content_downloader import ContentDownloader
from storage.file_manager import FileManager
from storage.history_manager import HistoryManager
from utils.helpers import extract_id, analysis_id, open_directory
from utils.logger import TkinterLogHandler

disable_warnings()


def thread_it(func, *t_args):
    thread = threading.Thread(target=func, args=t_args)
    thread.daemon = True
    thread.start()


class PixivApp:
    def __init__(self, root_app) -> None:
        self.root = root_app
        self.root.geometry('450x580+400+50')
        self.root.title('Pixiv下载器')

        img_path = FileManager.create_temp_resource('img\\cover.png')
        github_icon_path = FileManager.create_temp_resource('img\\github.png')
        self.root.img = PhotoImage(file=img_path)
        self.github_icon = PhotoImage(file=github_icon_path)

        self.is_stopped_btn = False
        self.is_paused_btn = False

        self.total_progress = 0
        self.current_progress = 0

        # 记录当前下载的路径信息
        self.current_download_path = None
        self.current_user_id = None

        # 认证和会话管理
        self.session_manager = SessionManager()
        self.login_manager = LoginManager(self.session_manager)

        # 其他管理器
        self.api_client = None
        self.download_manager = None
        self.content_downloader = None
        self.file_manager = FileManager()
        self.history_manager = HistoryManager()

        self.input_var_UID = StringVar()
        self.input_var_UID.trace("w", self.update_content)
        self.is_finish_exit = BooleanVar()
        self.is_open_dir = BooleanVar()
        self.is_worker_selected = BooleanVar()
        self.is_artwork_selected = BooleanVar()
        self.is_collection_selected = BooleanVar()
        self.is_novel_selected = BooleanVar()
        self.welcome = StringVar()
        self.login_btn_text = StringVar()

        self.login_btn_text.set("登录")
        self.welcome.set("欢迎，登录可以下载更多图片！")

        self.font_title = tkFont.Font(family='黑体', size=11)
        self.font_normal = tkFont.Font(family='宋体', size=10)
        self.font_large = tkFont.Font(family='黑体', size=15)
        self.font_button = tkFont.Font(family='黑体', size=11)

        # UI 组件引用
        self.log_text = None
        self.button_submit = None
        self.process_text = None
        self.btn_pause = None
        self.btn_stop = None
        self.progress_bar = None
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 初始化
        self.init_logging()
        self.create_widgets()
        self.init_session()
        self.root.after(100, lambda: thread_it(self.init_login))
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.resizable(False, False)

    def init_session(self) -> None:
        try:
            session = self.session_manager.init_session()
            self.api_client = PixivAPI(session)
            self.download_manager = DownloadManager(
                self.api_client,
                progress_callback=self.update_progress_callback,
                task_complete_callback=None  # 将由 content_downloader 处理
            )
            self.content_downloader = ContentDownloader(
                self.api_client,
                self.download_manager,
                self.file_manager,
                self.history_manager
            )
            # 设置下载管理器的任务完成回调
            self.download_manager.task_complete_callback = self.content_downloader.on_task_complete
            logging.info("初始化成功")

        except Exception as e:
            logging.error(f"初始化失败: {e}")

    def init_login(self) -> None:
        try:
            self.button_submit.config(state=DISABLED)

            is_logged_in = self.login_manager.check_login_status()

            if is_logged_in:
                username = self.login_manager.get_username()
                self.login_btn_text.set("退出登录")
                self.welcome.set(f"你好，{username}！")
            else:
                self.login_btn_text.set("登录")
                self.welcome.set("欢迎，登录可以下载更多图片！")

        finally:
            self.button_submit.config(state=NORMAL)

    def init_logging(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        from logging.handlers import TimedRotatingFileHandler
        log_dir = FileManager.create_directory("log")
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            when='midnight', interval=1, backupCount=7, encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    def create_widgets(self) -> None:
        # 图片框
        img_frame = Frame(self.root, bg='#f5f5f5')
        img_frame.pack(fill='both')

        label_img = Label(img_frame, image=self.root.img, width=800, height=120, bg='#f5f5f5', cursor='hand2')
        label_img.pack(fill='both')
        label_img.bind('<Button-1>', lambda e: self.open_pixiv())

        github_btn = Button(
            img_frame, image=self.github_icon,
            relief='flat', bg='#f5f5f5', activebackground='#f5f5f5',
            bd=0, cursor='hand2', command=self.open_github
        )
        github_btn.place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-5)

        # 登录框
        login_frame = LabelFrame(self.root)
        login_btn = Button(
            login_frame, textvariable=self.login_btn_text,
            font=self.font_title, command=self.login_or_out,
            width=15, relief='groove'
        )
        login_welcome = Label(login_frame, textvariable=self.welcome, font=self.font_title)
        login_welcome.pack(side='left', padx=5)
        login_btn.pack(side='right')
        login_frame.pack(fill='both', pady=(0, 5))

        # 输入框
        input_frame = LabelFrame(self.root)
        label_input = Label(input_frame, text='请输入链接/UID:', font=self.font_normal)
        entry = Entry(input_frame, width=43, relief='flat', textvariable=self.input_var_UID)
        btn_jump = Button(
            input_frame, text='→', font=self.font_button,
            width=5, relief='groove',
            command=lambda: thread_it(self.open_space)
        )
        label_input.pack(side='left')
        entry.pack(side='left', fill='both', expand=True)
        btn_jump.pack(side='left', padx=2)
        input_frame.pack(fill='both', pady=(0, 5))

        # 类型选择
        type_frame = LabelFrame(self.root)
        label_type = Label(type_frame, text='下载类型:', font=self.font_normal)
        label_type.pack(side='left', padx=5)

        # 画师选项
        left_frame = Frame(type_frame)
        Checkbutton(
            left_frame, text='画师', font=self.font_normal, height=2,
            variable=self.is_worker_selected, command=self.on_worker_toggle
        ).pack(side='left')
        left_frame.pack(side='left', padx=10)

        # 分隔线
        Frame(type_frame, width=1, bg='gray', relief='sunken').pack(side='left', fill='y', padx=10)

        # 其他选项
        right_frame = Frame(type_frame)
        Checkbutton(
            right_frame, text='插画', font=self.font_normal, height=2,
            variable=self.is_artwork_selected,
            command=lambda: self.on_right_option_toggle(TYPE_ARTWORK)
        ).pack(side='left', padx=10)
        Checkbutton(
            right_frame, text='珍藏册', font=self.font_normal, height=2,
            variable=self.is_collection_selected,
            command=lambda: self.on_right_option_toggle(TYPE_COLLECTION)
        ).pack(side='left', padx=10)
        Checkbutton(
            right_frame, text='小说', font=self.font_normal, height=2,
            variable=self.is_novel_selected,
            command=lambda: self.on_right_option_toggle(TYPE_NOVEL)
        ).pack(side='left', padx=10)
        right_frame.pack(side='left')
        type_frame.pack(fill='both', pady=(0, 5))

        # 默认选中插画
        self.is_artwork_selected.set(True)

        choose_frame = LabelFrame(self.root)
        Checkbutton(
            choose_frame, text='下载后退出', font=self.font_title, height=2,
            variable=self.is_finish_exit,
            command=lambda: logging.info(f"下载后退出：{'已选中' if self.is_finish_exit.get() else '已取消'}")
        ).pack(side='left', padx=10)
        Checkbutton(
            choose_frame, text='下载后打开', font=self.font_title, height=2,
            variable=self.is_open_dir,
            command=lambda: logging.info(f"下载后打开：{'已选中' if self.is_open_dir.get() else '已取消'}")
        ).pack(side='left', padx=10)

        self.button_submit = Button(
            choose_frame, text='下  载', font=self.font_large,
            relief='groove', bg='lavender', width=15,
            command=lambda: thread_it(self.submit_download)
        )
        self.button_submit.pack(side='right', padx=10)

        choose_frame.pack(fill='both', pady=(0, 5))

        self.is_open_dir.set(True)
        self.is_finish_exit.set(False)

        # 进度条
        process_frame = Frame(self.root)
        self.style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor='white', background='lightblue', bordercolor='gray'
        )
        self.progress_bar = Progressbar(
            process_frame, orient='horizontal', mode='determinate',
            length=550, style="Custom.Horizontal.TProgressbar"
        )
        self.process_text = Label(process_frame, text='0%')
        self.btn_stop = Button(
            process_frame, text=' X ', font=self.font_button,
            background="red", foreground="white",
            command=lambda: thread_it(self.stop_download)
        )
        self.btn_pause = Button(
            process_frame, text=' ▶ ', font=self.font_button,
            command=lambda: thread_it(self.toggle_pause)
        )

        self.btn_stop.config(state='disabled')
        self.btn_pause.config(state='disabled')

        process_frame.pack(fill='both', pady=(0, 5))
        self.btn_pause.pack(side='right')
        self.btn_stop.pack(side='right', padx=5)
        self.process_text.pack(side='left', padx=10)
        self.progress_bar.pack(side='left', padx=2)

        # 日志显示
        self.log_text = Text(self.root, height=10)
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.insert('1.0',
                             '欢迎使用 PIXIV 下载器！\n'
                             '登录以下载更多资源，失效时再重新登录。\n'
                             '==============================================\n'
                             '勾选画师时，右侧为画师的作品类型 (按画师 ID)\n'
                             '不勾选时，右侧为独立搜索的作品类型 (按作品 ID)\n'
                             '==============================================\n'
                             )
        self.log_text.config(state='disabled')
        self.log_text.pack(fill='both', expand=True)

        # 添加 Tkinter 日志处理器
        tkinter_handler = TkinterLogHandler(self.log_text)
        tkinter_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        tkinter_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(tkinter_handler)

    def _do_login(self) -> None:
        def on_success(username):
            self.welcome.set(f'你好，{username}！')
            self.login_btn_text.set("退出登录")

        def on_failure():
            logging.info("已取消登录")

        self.login_manager.login(on_success=on_success, on_failure=on_failure)

    def login_or_out(self) -> None:
        if not self.login_manager.is_authenticated():
            thread_it(self._do_login)
        else:
            def on_success():
                self.login_btn_text.set("登录")
                self.welcome.set("欢迎，登录可以下载更多图片！")

            self.login_manager.logout(on_success=on_success)

    def submit_download(self) -> None:
        try:
            # 重置状态
            self.is_paused_btn = False
            self.is_stopped_btn = False
            self.btn_pause.config(text=' ⏸ ')
            self.button_submit.config(state=DISABLED)
            self.btn_stop.config(state=NORMAL)
            self.btn_pause.config(state=NORMAL)

            # 重置下载管理器状态
            if self.download_manager:
                self.download_manager.is_paused.clear()
                self.download_manager.is_stopped.clear()

            # 重置进度和下载路径
            self.total_progress = 0
            self.current_download_path = None
            self.current_user_id = None
            self.content_downloader.clear_current_works()

            # 获取输入
            input_text = self.input_var_UID.get().strip()
            if not input_text:
                logging.warning('输入的内容不能为空~~')
                return

            # 获取选中的类型
            selected_types = self.get_selected_types()
            if not selected_types:
                logging.warning('请至少选择一种下载类型！')
                return

            is_worker_mode = self.is_worker_selected.get()

            if is_worker_mode:
                # 画师模式
                user_id = extract_id(input_text, TYPE_USER)
                self.current_user_id = user_id

                download_path, total_tasks = self.content_downloader.download_user_works(
                    user_id,
                    selected_types,
                    progress_callback=self._progress_callback,
                    check_stopped=self._check_stopped,
                    check_paused=self._check_paused
                )

                if download_path:
                    self.current_download_path = download_path
                    self.total_progress = total_tasks
            else:
                # 单个作品模式 - 重置历史记录管理器
                self.history_manager.reset()

                # 显示检索进度
                self.process_text.config(text='检索作品信息...')
                self.progress_bar['value'] = 0
                self.root.update()

                # 单个作品模式
                total_types = len(selected_types)
                for i, type_name in enumerate(selected_types):
                    # 检查是否被停止
                    if self.is_stopped_btn or self.download_manager.is_stopped.is_set():
                        logging.info("检索已停止")
                        return

                    # 检查暂停状态
                    while self.is_paused_btn or self.download_manager.is_paused.is_set():
                        time.sleep(0.5)

                    # 更新检索进度
                    progress = (i + 1) / total_types * 100
                    self.process_text.config(text=f'检索 {type_name} 信息...')
                    self.progress_bar['value'] = progress
                    self.root.update()

                    resource_id = extract_id(input_text, type_name)
                    logging.info(f"下载 {type_name}: {resource_id}")

                    if type_name == TYPE_ARTWORK:
                        # 设置插画文件夹路径
                        self.current_download_path = self.file_manager.get_artwork_directory(resource_id)
                        self.content_downloader.download_artwork(resource_id)
                        self.total_progress += 1
                    elif type_name == TYPE_COLLECTION:
                        # 设置珍藏册文件夹路径
                        self.current_download_path = self.file_manager.get_collection_directory(resource_id)
                        self.content_downloader.download_collection(resource_id)
                        self.total_progress += 1
                    elif type_name == TYPE_NOVEL:
                        # 小说没有文件夹，设置为小说目录
                        self.current_download_path = self.file_manager.get_novel_directory()
                        self.content_downloader.download_novel(resource_id)
                        self.total_progress += 1

                # 检索完成，准备下载
                self.process_text.config(text='准备下载...')
                self.progress_bar['value'] = 100
                self.root.update()

            # 检查是否在检索阶段被停止
            if self.is_stopped_btn or self.download_manager.is_stopped.is_set():
                logging.info("下载已取消")
                return

            # 开始下载
            self.start_download(is_worker_mode)

        except Exception as e:
            logging.error(f"提交下载失败: {e}")
        finally:
            self.button_submit.config(state=NORMAL)
            self.btn_stop.config(state='disabled')
            self.btn_pause.config(state='disabled')

    def _progress_callback(self, text: str, percentage: float) -> None:
        """进度回调 - 更新UI"""
        self.process_text.config(text=text)
        self.progress_bar['value'] = percentage
        self.root.update()

    def _check_stopped(self) -> bool:
        return self.is_stopped_btn or self.download_manager.is_stopped.is_set()

    def _check_paused(self) -> None:
        while self.is_paused_btn or self.download_manager.is_paused.is_set():
            time.sleep(0.5)

    def start_download(self, is_worker_mode: bool = False) -> None:
        try:
            # 检查是否有下载任务
            has_image_tasks = len(self.download_manager.download_queue) > 0
            has_tasks = has_image_tasks or self.total_progress > 0

            if not has_tasks:
                logging.warning("没有需要下载的内容")
                return

            # 重置进度，使用下载队列的实际任务数作为总数
            self.current_progress = 0
            if has_image_tasks:
                # 下载阶段：总数 = 下载队列里的实际任务数
                self.total_progress = len(self.download_manager.download_queue)
            self.update_progress_ui()

            if has_image_tasks:
                expected_total = None
                if is_worker_mode:
                    stats = self.content_downloader.get_download_stats()
                    expected_total = stats['expected_tasks']
                
                self.download_manager.start(task_id="main_download", expected_total=expected_total)

            # 只在画师模式下保存历史记录
            if is_worker_mode:
                self.history_manager.save()

            logging.info("所有下载任务完成！")

            # 下载完成后的操作
            if self.is_open_dir.get() and self.current_download_path:
                logging.info(f"打开下载目录: {self.current_download_path}")
                open_directory(self.current_download_path)

            if self.is_finish_exit.get():
                self.root.quit()

        except Exception as e:
            logging.error(f"下载过程出错: {e}")

    def update_progress_callback(self, increment: int) -> None:
        self.current_progress += increment
        self.root.after(0, self.update_progress_ui)

    def update_progress_ui(self) -> None:
        if self.total_progress > 0:
            percentage = (self.current_progress / self.total_progress) * 100
            self.progress_bar['value'] = percentage
            self.process_text.config(text=f'{percentage:.2f}%')

    def toggle_pause(self) -> None:
        if not self.is_paused_btn:
            self.download_manager.pause()
            self.btn_pause.config(text=' ▶ ')
            self.is_paused_btn = True
        else:
            self.download_manager.resume()
            self.btn_pause.config(text=' ⏸ ')
            self.is_paused_btn = False

    def stop_download(self) -> None:
        """停止下载"""
        self.download_manager.stop()
        self.is_stopped_btn = True

    def get_selected_types(self) -> list[str]:
        """获取选中的下载类型"""
        types = []
        if self.is_artwork_selected.get():
            types.append(TYPE_ARTWORK)
        if self.is_collection_selected.get():
            types.append(TYPE_COLLECTION)
        if self.is_novel_selected.get():
            types.append(TYPE_NOVEL)
        return types

    def on_worker_toggle(self) -> None:
        is_worker = self.is_worker_selected.get()

        if is_worker:
            logging.info("选择类型：画师（多选模式）")
            if not (self.is_artwork_selected.get() or
                    self.is_collection_selected.get() or
                    self.is_novel_selected.get()):
                self.is_artwork_selected.set(True)
        else:
            logging.info("取消画师（单选模式）")
            selected_count = sum([
                self.is_artwork_selected.get(),
                self.is_collection_selected.get(),
                self.is_novel_selected.get()
            ])

            if selected_count > 1:
                # 如果多个被选中，只保留第一个，默认选中插画
                if self.is_artwork_selected.get():
                    self.is_collection_selected.set(False)
                    self.is_novel_selected.set(False)
                elif self.is_collection_selected.get():
                    self.is_novel_selected.set(False)
            elif selected_count == 0:
                self.is_artwork_selected.set(True)

    def on_right_option_toggle(self, option_type: str) -> None:
        is_worker = self.is_worker_selected.get()

        if is_worker:
            # 多选模式：至少保证有一个被选中
            selected_count = sum([
                self.is_artwork_selected.get(),
                self.is_collection_selected.get(),
                self.is_novel_selected.get()
            ])

            if selected_count == 0:
                # 如果都被取消了，重新选中插画
                self.is_artwork_selected.set(True)
                logging.warning("至少需要选择一个下载类型")
            else:
                # 记录当前选中的类型
                selected = []
                if self.is_artwork_selected.get():
                    selected.append("插画")
                if self.is_collection_selected.get():
                    selected.append("珍藏册")
                if self.is_novel_selected.get():
                    selected.append("小说")
                logging.info(f"选择类型：画师 + {' + '.join(selected)}")
        else:
            # 单选模式：只能选一个
            if option_type == TYPE_ARTWORK:
                self.is_artwork_selected.set(True)
                self.is_collection_selected.set(False)
                self.is_novel_selected.set(False)
                logging.info("选择类型：插画")
            elif option_type == TYPE_COLLECTION:
                self.is_artwork_selected.set(False)
                self.is_collection_selected.set(True)
                self.is_novel_selected.set(False)
                logging.info("选择类型：珍藏册")
            elif option_type == TYPE_NOVEL:
                self.is_artwork_selected.set(False)
                self.is_collection_selected.set(False)
                self.is_novel_selected.set(True)
                logging.info("选择类型：小说")

    def update_content(self, *args) -> None:
        input_text = self.input_var_UID.get()
        logging.debug(f"update_content, 输入的id为：{input_text}")

        # 根据URL自动设置选项
        if TYPE_USER in input_text:
            self.is_worker_selected.set(True)
            self.is_artwork_selected.set(False)
            self.is_collection_selected.set(False)
            self.is_novel_selected.set(False)
            # 画师模式下默认选中插画
            self.is_artwork_selected.set(True)
            self.on_worker_toggle()
        elif TYPE_ARTWORK in input_text:
            self.is_worker_selected.set(False)
            self.is_artwork_selected.set(True)
            self.is_collection_selected.set(False)
            self.is_novel_selected.set(False)
            self.on_right_option_toggle(TYPE_ARTWORK)
        elif TYPE_COLLECTION in input_text:
            self.is_worker_selected.set(False)
            self.is_artwork_selected.set(False)
            self.is_collection_selected.set(True)
            self.is_novel_selected.set(False)
            self.on_right_option_toggle(TYPE_COLLECTION)
        elif TYPE_NOVEL in input_text:
            self.is_worker_selected.set(False)
            self.is_artwork_selected.set(False)
            self.is_collection_selected.set(False)
            self.is_novel_selected.set(True)
            self.on_right_option_toggle(TYPE_NOVEL)

    def open_pixiv(self) -> None:
        try:
            pixiv_url = "https://www.pixiv.net/"
            logging.info(f"正在打开 Pixiv 网站: {pixiv_url}")
            webbrowser.open(pixiv_url)
        except Exception as e:
            logging.error(f"打开 Pixiv 网站失败: {e}")

    def open_github(self) -> None:
        try:
            github_url = "https://github.com/kanostars/PixivCrawl"
            logging.info(f"正在打开 GitHub 仓库: {github_url}")
            webbrowser.open(github_url)
        except Exception as e:
            logging.error(f"打开 GitHub 失败: {e}")

    def open_space(self) -> None:
        try:
            input_text = self.input_var_UID.get().strip()
            if not input_text:
                logging.warning('请先输入链接或ID')
                return

            is_worker_mode = self.is_worker_selected.get()

            if is_worker_mode:
                url = analysis_id(input_text, TYPE_USER)
                if url and (url.startswith('http://') or url.startswith('https://')):
                    logging.info(f"正在跳转到画师空间: {url}")
                    webbrowser.open(url)
                else:
                    logging.warning('无法识别的画师ID或链接格式')
            else:
                selected_types = self.get_selected_types()
                if not selected_types:
                    logging.warning('请先选择一种类型')
                    return

                type_name = selected_types[0]
                url = analysis_id(input_text, type_name)

                if url and (url.startswith('http://') or url.startswith('https://')):
                    logging.info(f"正在跳转到 {type_name} 页面: {url}")
                    webbrowser.open(url)
                else:
                    logging.warning('无法识别的ID或链接格式')

        except Exception as e:
            logging.error(f"跳转失败: {e}")

    def on_closing(self) -> None:
        try:
            # 停止下载
            if self.download_manager:
                self.download_manager.stop()

            # 保存历史记录
            if self.history_manager:
                self.history_manager.save()

            logging.info("程序退出")
            self.root.destroy()

        except Exception as e:
            logging.error(f"关闭程序时出错: {e}")
            self.root.destroy()


def main():
    ensure_directories()

    root = Tk()
    PixivApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
