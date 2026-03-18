import argparse
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)

from api import PixivAPI
from auth import LoginManager, SessionManager
from config.settings import (
    TYPE_USER, TYPE_ARTWORK, TYPE_COLLECTION, TYPE_NOVEL,
    ensure_directories
)
from download import DownloadManager, ContentDownloader
from storage.file_manager import FileManager
from storage.history_manager import HistoryManager
from utils.helpers import extract_id


class ConsoleProgressBar:
    """控制台进度条"""

    def __init__(self):
        self.total = 0
        self.current = 0
        self.bar_length = 50

    def update(self, text: str, percentage: float) -> None:
        """更新进度条（兼容新架构的回调接口）"""
        if self.total > 0:
            self.current = int(self.total * percentage / 100)

        filled = int(self.bar_length * percentage / 100)
        bar = '█' * filled + '-' * (self.bar_length - filled)
        sys.stdout.write(f'\r{text}: |{bar}| {percentage:.1f}%')
        sys.stdout.flush()

        if percentage >= 100:
            print()

    def update_download_progress(self, increment: int) -> None:
        """更新下载进度（用于下载阶段）"""
        self.current += increment
        if self.total > 0:
            percent = self.current / self.total
            filled = int(self.bar_length * percent)
            bar = '█' * filled + '-' * (self.bar_length - filled)
            sys.stdout.write(f'\r下载进度: |{bar}| {percent * 100:.1f}% ({self.current}/{self.total})')
            sys.stdout.flush()

            if self.current >= self.total:
                print()

    def set_total(self, total: int) -> None:
        """设置总任务数"""
        self.total = total
        self.current = 0


def setup_logging():
    """初始化日志系统"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # 文件日志
    log_dir = FileManager.create_directory("log")
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, 'cli.log'),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(logging.DEBUG)

    # 控制台日志
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def check_login(login_manager: LoginManager) -> bool:
    """检查登录状态"""
    return login_manager.check_login_status()


def main():
    parser = argparse.ArgumentParser(
        description='Pixiv 命令行下载器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 下载画师的所有资源（插画、珍藏册、小说）
  PixivCLI.exe -w 123456 
  
  # 下载画师的插画和小说
  PixivCLI.exe -w 123456 -a -n
  
  # 下载小说
  PixivCLI.exe -n 123456
  
  # 使用自定义 Cookie
  PixivCLI.exe -w 123456 -cookie "your_phpsessid_here"
  
  # 登录
  PixivCLI.exe -cookie "your_phpsessid_here"
        """
    )

    parser.add_argument('-w', '--worker', metavar='ID', help='画师ID (可配合 -a/-c/-n 多选下载类型)')
    parser.add_argument('-a', '--artwork', nargs='?', const='flag', metavar='ID',
                        help='插画: 独立模式传ID, 画师模式作为开关')
    parser.add_argument('-n', '--novel', nargs='?', const='flag', metavar='ID',
                        help='小说: 独立模式传ID, 画师模式作为开关')
    parser.add_argument('-c', '--collection', nargs='?', const='flag', metavar='ID',
                        help='珍藏册: 独立模式传ID, 画师模式作为开关')
    parser.add_argument('-cookie', help='PHPSESSID cookie值')
    parser.add_argument('--check-login', action='store_true', help='仅检查登录状态')

    args = parser.parse_args()

    # 确保目录存在
    ensure_directories()

    # 初始化日志
    setup_logging()

    print("=" * 60)
    print("Pixiv 命令行下载器")
    print("=" * 60)

    # 初始化认证管理器
    session_manager = SessionManager()
    login_manager = LoginManager(session_manager)

    # 更新 Cookie
    if args.cookie:
        session_manager.update_cookie(args.cookie)
        logging.info("Cookie 已更新")

    # 仅检查登录状态
    if args.check_login:
        check_login(login_manager)
        return

    # 检查是否提供了有效参数
    if not (args.worker or args.artwork or args.novel or args.collection):
        parser.print_help()
        return

    # 检查登录状态
    check_login(login_manager)

    # 初始化核心组件
    try:
        session = session_manager.init_session()
        api_client = PixivAPI(session)
        file_manager = FileManager()
        history_manager = HistoryManager()

        # 创建进度条
        progress_bar = ConsoleProgressBar()

        # 初始化下载管理器
        download_manager = DownloadManager(
            api_client,
            progress_callback=lambda increment: progress_bar.update_download_progress(increment)
        )

        # 初始化内容下载器
        content_downloader = ContentDownloader(
            api_client,
            download_manager,
            file_manager,
            history_manager
        )

        # 设置任务完成回调
        download_manager.task_complete_callback = content_downloader.on_task_complete

    except Exception as e:
        logging.error(f"初始化失败: {e}")
        return

    # 解析下载类型和ID
    selected_types = []
    work_id = None
    is_worker_mode = False

    if args.worker:
        # 画师模式
        is_worker_mode = True
        work_id = extract_id(args.worker, TYPE_USER)

        # 根据参数设置下载类型
        has_selection = False
        if args.artwork:
            selected_types.append(TYPE_ARTWORK)
            has_selection = True
            logging.info("  - 包含插画")
        if args.collection:
            selected_types.append(TYPE_COLLECTION)
            has_selection = True
            logging.info("  - 包含珍藏册")
        if args.novel:
            selected_types.append(TYPE_NOVEL)
            has_selection = True
            logging.info("  - 包含小说")

        # 如果没有指定类型，默认下载所有资源
        if not has_selection:
            selected_types.extend([TYPE_ARTWORK, TYPE_COLLECTION, TYPE_NOVEL])
            logging.info("  - 默认下载所有资源（插画、珍藏册、小说）")

        logging.info(f"画师模式 - 画师ID: {work_id}")

    elif args.artwork or args.novel or args.collection:
        # 独立作品模式
        type_count = sum([
            bool(args.artwork and args.artwork != 'flag'),
            bool(args.collection and args.collection != 'flag'),
            bool(args.novel and args.novel != 'flag')
        ])

        if type_count > 1:
            logging.warning("独立作品模式只能选择一个类型，已使用第一个参数")

        if args.artwork and args.artwork != 'flag':
            work_id = extract_id(args.artwork, TYPE_ARTWORK)
            selected_types.append(TYPE_ARTWORK)
            logging.info(f"独立作品模式 - 插画ID: {work_id}")
        elif args.collection and args.collection != 'flag':
            work_id = extract_id(args.collection, TYPE_COLLECTION)
            selected_types.append(TYPE_COLLECTION)
            logging.info(f"独立作品模式 - 珍藏册ID: {work_id}")
        elif args.novel and args.novel != 'flag':
            work_id = extract_id(args.novel, TYPE_NOVEL)
            selected_types.append(TYPE_NOVEL)
            logging.info(f"独立作品模式 - 小说ID: {work_id}")

    if not work_id or not selected_types:
        logging.error("无效的参数组合")
        parser.print_help()
        return

    # 开始下载
    try:
        logging.info("开始下载...")
        download_path = None

        if is_worker_mode:
            # 画师模式
            download_path, total_tasks = content_downloader.download_user_works(
                work_id,
                selected_types,
                progress_callback=progress_bar.update
            )

            if download_path and total_tasks > 0:
                # 设置进度条总数
                progress_bar.set_total(total_tasks)

                # 开始下载
                stats = content_downloader.get_download_stats()
                expected_total = stats['expected_tasks']
                download_manager.start(task_id="cli_download", expected_total=expected_total)

                # 保存历史记录
                history_manager.save()
        else:
            # 单个作品模式
            history_manager.reset()

            for type_name in selected_types:
                if type_name == TYPE_ARTWORK:
                    download_path = file_manager.get_artwork_directory(work_id)
                    content_downloader.download_artwork(work_id)
                elif type_name == TYPE_COLLECTION:
                    download_path = file_manager.get_collection_directory(work_id)
                    content_downloader.download_collection(work_id)
                elif type_name == TYPE_NOVEL:
                    download_path = file_manager.get_novel_directory()
                    content_downloader.download_novel(work_id)

            # 设置进度条总数并开始下载
            total_tasks = len(download_manager.download_queue)
            if total_tasks > 0:
                progress_bar.set_total(total_tasks)
                download_manager.start(task_id="cli_download")

        if download_path:
            logging.info(f"下载完成！文件保存在: {download_path}")
            print("=" * 60)
            print(f"✓ 下载完成")
            print(f"✓ 保存路径: {download_path}")
            print("=" * 60)
        else:
            logging.warning("下载失败或未找到资源")

    except KeyboardInterrupt:
        logging.info("\n用户中断下载")
        print("\n下载已取消")
        download_manager.stop()
    except Exception as e:
        logging.error(f"下载过程中发生错误: {e}", exc_info=True)
        print(f"\n错误: {e}")


if __name__ == '__main__':
    main()
