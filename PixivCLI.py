import argparse
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)

from FileHandlerManager import FileHandlerManager
from PixivDownloader import ThroughId, get_username, get_page_content
from config import TYPE_WORKER, TYPE_ARTWORKS, TYPE_COLLECTION, TYPE_NOVEL, cookies


class ConsoleProgressBar:
    """控制台进度条"""

    def __init__(self):
        self.total = 0
        self.current = 0
        self.bar_length = 50

    def update_progress_bar(self, increment, total=0):
        """更新进度条"""
        if total:  # 设置总数
            self.total = total
            self.current = 0
        else:  # 增加进度
            self.current += increment

        if self.total > 0:
            percent = self.current / self.total
            filled = int(self.bar_length * percent)
            bar = '█' * filled + '-' * (self.bar_length - filled)
            sys.stdout.write(f'\r进度: |{bar}| {percent * 100:.1f}% ({self.current}/{self.total})')
            sys.stdout.flush()

            if self.current >= self.total:
                print()  # 完成后换行

    def update_progress_bar_color(self, color):
        """兼容 GUI 版本的颜色更新方法（命令行版本忽略）"""
        pass


def setup_logging():
    """初始化日志系统"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # 文件日志
    log_dir = FileHandlerManager.create_directory("log")
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, 'my.log'),
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


def check_login():
    """检查登录状态"""
    try:
        logging.info("正在检查登录状态...")
        username = get_username(get_page_content())
        if username:
            logging.info(f"已登录用户: {username}")
            return True
        else:
            logging.warning("未登录或 Cookie 已失效")
            return False
    except Exception as e:
        logging.warning(f"检查登录状态失败: {e}")
        return False


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

  # 下载珍藏册
  PixivCLI.exe -c 123456
  
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

    # 初始化日志
    setup_logging()

    print("=" * 60)
    print("Pixiv 命令行下载器")
    print("=" * 60)

    # 更新 Cookie
    if args.cookie:
        args.cookie = args.cookie.replace("PHPSESSID=", "")
        cookie_json = cookies.replace('PHPSESSID=', '')
        if args.cookie != cookie_json:
            FileHandlerManager.update_json(args.cookie)
            logging.info("Cookie 已更新")

    # 仅检查登录状态
    if args.check_login:
        check_login()
        return

    # 检查是否提供了有效参数
    if not (args.worker or args.artwork or args.novel or args.collection):
        parser.print_help()
        return

    # 检查登录状态
    check_login()

    # 创建进度条对象
    progress_bar = ConsoleProgressBar()

    # 解析下载类型
    selected_types = []
    work_id = None

    if args.worker:
        # 画师模式
        work_id = args.worker
        selected_types.append(TYPE_WORKER)

        # 根据参数设置下载类型
        has_selection = False
        if args.artwork:
            selected_types.append(TYPE_ARTWORKS)
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
            selected_types.extend([TYPE_ARTWORKS, TYPE_COLLECTION, TYPE_NOVEL])
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
            work_id = args.artwork
            selected_types.append(TYPE_ARTWORKS)
            logging.info(f"独立作品模式 - 插画ID: {work_id}")
        elif args.collection and args.collection != 'flag':
            work_id = args.collection
            selected_types.append(TYPE_COLLECTION)
            logging.info(f"独立作品模式 - 珍藏册ID: {work_id}")
        elif args.novel and args.novel != 'flag':
            work_id = args.novel
            selected_types.append(TYPE_NOVEL)
            logging.info(f"独立作品模式 - 小说ID: {work_id}")

    if not work_id or not selected_types:
        logging.error("无效的参数组合")
        parser.print_help()
        return

    # 开始下载
    try:
        logging.info("开始下载...")
        downloader = ThroughId(work_id, progress_bar, selected_types)
        result_path = downloader.pre_download()

        if result_path:
            logging.info(f"下载完成！文件保存在: {result_path}")
            print("=" * 60)
            print(f"✓ 下载完成")
            print(f"✓ 保存路径: {result_path}")
            print("=" * 60)
        else:
            logging.warning("下载失败或未找到资源")

    except KeyboardInterrupt:
        logging.info("\n用户中断下载")
        print("\n下载已取消")
    except Exception as e:
        logging.error(f"下载过程中发生错误: {e}", exc_info=True)
        print(f"\n错误: {e}")


if __name__ == '__main__':
    main()
