import logging
import os
from typing import Optional, Callable, Any

from config.settings import TYPE_ARTWORK, TYPE_COLLECTION, TYPE_NOVEL, BATCH_SIZE, BATCH_INTERVAL
from api.models import UserProfile, UgoiraMeta


class ContentDownloader:
    """内容下载器 - 处理插画、小说、珍藏册等内容的下载"""

    def __init__(self, api_client, download_manager, file_manager, history_manager):
        """
        初始化内容下载器
        
        Args:
            api_client: API 客户端
            download_manager: 下载管理器
            file_manager: 文件管理器
            history_manager: 历史记录管理器
        """
        self.api_client = api_client
        self.download_manager = download_manager
        self.file_manager = file_manager
        self.history_manager = history_manager
        self.logger = logging.getLogger(__name__)

        # 跟踪当前下载的作品（用于完成后记录历史）
        self.current_downloading_works = {}  # {artwork_id: total_pages}

        # 统计信息
        self.expected_tasks = 0  # 预期任务数
        self.actually_added_tasks = 0  # 实际添加的任务数
        self.failed_to_add_tasks = 0  # 添加失败的任务数

    def download_user_works(self, user_id: str, work_types: list[str],
                            progress_callback: Optional[Callable] = None,
                            check_stopped: Optional[Callable] = None,
                            check_paused: Optional[Callable] = None) -> tuple[None, int] | tuple[Any, int | Any]:
        """
        下载用户作品
        
        Args:
            user_id: 用户ID
            work_types: 作品类型列表
            progress_callback: 进度回调函数 (text, percentage) -> None
            check_stopped: 检查是否停止的回调函数 () -> bool
            check_paused: 检查暂停状态的回调函数 () -> None
            
        Returns:
            (download_path, total_tasks): 下载路径和总任务数
        """
        try:
            # 重置统计信息
            self.expected_tasks = 0
            self.actually_added_tasks = 0
            self.failed_to_add_tasks = 0

            self.logger.info(f"开始检索用户id： {user_id} 的作品...")

            if progress_callback:
                progress_callback('检索中...', 0)

            # 检查是否被停止
            if check_stopped and check_stopped():
                self.logger.info("检索已停止")
                return None, 0

            user_works = self.api_client.get_user_works(user_id)
            artist_name = self._get_artist_name(user_works, progress_callback, check_stopped)
            download_path = self.file_manager.get_user_directory(user_id, artist_name)
            history_file = os.path.join(download_path, 'download_history.json')

            self.history_manager.set_history_file(history_file, artist_id=user_id)

            if progress_callback:
                progress_callback('检索作品数量...', 0)

            total_tasks = 0

            # 根据类型筛选和添加任务
            for work_type in work_types:
                if check_stopped and check_stopped():
                    self.logger.info("检索已停止")
                    return download_path, total_tasks

                if work_type == TYPE_ARTWORK:
                    tasks = self._process_user_artworks(
                        user_works, user_id, artist_name,
                        progress_callback, check_stopped, check_paused
                    )
                    total_tasks += tasks

                elif work_type == TYPE_NOVEL:
                    tasks = self._process_user_novels(
                        user_works, user_id, artist_name,
                        progress_callback, check_stopped, check_paused
                    )
                    total_tasks += tasks

                elif work_type == TYPE_COLLECTION:
                    tasks = self._process_user_collections(
                        user_works, user_id, artist_name,
                        progress_callback, check_stopped, check_paused
                    )
                    total_tasks += tasks

            # 检索完成
            if progress_callback:
                progress_callback('准备下载...', 100)

            return download_path, total_tasks

        except Exception as e:
            self.logger.error(f"下载用户作品失败: {e}")
            raise

    def _get_artist_name(self, user_works: UserProfile, progress_callback: Optional[Callable] = None,
                         check_stopped: Optional[Callable] = None) -> Optional[str]:
        """获取画师名称"""
        self.logger.info("正在获取画师信息...")
        if progress_callback:
            progress_callback('获取画师信息...', 0)

        if check_stopped and check_stopped():
            return None

        # 从 UserProfile 中获取画师名称
        if user_works.name:
            self.history_manager.artist_name = user_works.name
            self.logger.info(f"画师名称: {user_works.name}")
            return user_works.name

        # 如果 UserProfile 没有名称，尝试从第一个作品获取
        all_work_ids = user_works.get_all_artwork_ids()
        if not all_work_ids:
            all_work_ids = user_works.novels

        if all_work_ids:
            first_work_id = all_work_ids[0]
            try:
                # 尝试从插画获取
                if user_works.illusts or user_works.manga:
                    work_info = self.api_client.get_artwork_info(first_work_id)
                    artist_name = work_info.user_name
                # 尝试从小说获取
                elif user_works.novels:
                    novel_info = self.api_client.get_novel_content(first_work_id)
                    artist_name = novel_info.user_name
                else:
                    return None

                if artist_name:
                    self.history_manager.artist_name = artist_name
                    self.logger.info(f"画师名称: {artist_name}")
                    return artist_name
            except Exception as e:
                self.logger.warning(f"获取画师名称失败: {e}")

        return None

    def _process_user_artworks(self, user_works: UserProfile, user_id: str, artist_name: Optional[str],
                               progress_callback: Optional[Callable], check_stopped: Optional[Callable],
                               check_paused: Optional[Callable]) -> int:
        """处理用户的插画作品"""
        # 获取所有插画ID（包括插画和漫画）
        all_artwork_ids = user_works.get_all_artwork_ids()

        self.logger.info(f"找到 {len(all_artwork_ids)} 个插画作品")

        # 统计未下载的作品数量
        not_downloaded_ids = [aid for aid in all_artwork_ids if
                              not self.history_manager.is_downloaded(aid, TYPE_ARTWORK)]
        not_downloaded_count = len(not_downloaded_ids)

        self.logger.info(f"其中 {not_downloaded_count} 个作品未下载")

        artwork_count = 0
        total_tasks = 0
        artwork_info_cache = {}  # 缓存作品信息，避免重复请求
        failed_artworks = []  # 记录检索失败的作品

        for i, artwork_id in enumerate(not_downloaded_ids):
            if check_stopped and check_stopped():
                self.logger.info("检索已停止")
                return total_tasks

            if check_paused:
                check_paused()

            try:
                if progress_callback:
                    progress = (i + 1) / not_downloaded_count * 100
                    progress_callback(f'检索插画 {i + 1}/{not_downloaded_count}', progress)

                # 只获取基本信息，不获取页面详情（减少API调用）
                artwork_info = self.api_client.get_artwork_info(artwork_id)
                artwork_info_cache[artwork_id] = artwork_info

                if artwork_info.is_ugoira():
                    # 动图只有1个文件
                    total_tasks += 1
                else:
                    # 静态图根据 page_count 计算，不需要调用 get_artwork_pages()
                    total_tasks += artwork_info.page_count
                artwork_count += 1

                if artwork_count > 0 and artwork_count % BATCH_SIZE == 0:
                    self.logger.debug(f"已检索 {artwork_count} 个作品，休息 {BATCH_INTERVAL} 秒...")
                    import time
                    time.sleep(BATCH_INTERVAL)

            except Exception as e:
                self.logger.error(f"获取插画 {artwork_id} 信息失败: {e}")
                # 记录失败的作品，假设为单页作品
                failed_artworks.append(artwork_id)
                total_tasks += 1

        # 计算检索失败的任务数
        failed_to_retrieve = len(failed_artworks)

        self.logger.info(f"需要下载 {artwork_count} 个插画作品，共 {total_tasks} 个文件")
        if failed_to_retrieve > 0:
            self.logger.warning(f"检索失败 {failed_to_retrieve} 个作品（已计入预期任务数）")

        self.expected_tasks += total_tasks  # 记录预期任务数

        self.logger.info("检索完成，即将开始添加下载任务...")
        import time
        time.sleep(3)

        self.logger.info("初始化下载任务中，请稍后...")

        if progress_callback:
            progress_callback('准备下载...', 100)

        # 添加下载任务，使用缓存的作品信息
        added_count = 0
        for artwork_id in not_downloaded_ids:
            if check_stopped and check_stopped():
                self.logger.info("添加任务已停止")
                return total_tasks

            # 检查暂停状态
            if check_paused:
                check_paused()

            # 跳过检索失败的作品
            if artwork_id in failed_artworks:
                self.logger.debug(f"插画 {artwork_id} 检索失败，跳过添加任务")
                self.failed_to_add_tasks += 1
                continue

            # 传递缓存的作品信息，避免重复请求
            cached_info = artwork_info_cache.get(artwork_id)
            self.download_artwork(artwork_id, user_id=user_id, artist_name=artist_name,
                                  artwork_info=cached_info)
            added_count += 1

            # 添加任务阶段也需要批次休息，因为会调用 get_artwork_pages API
            if added_count > 0 and added_count % BATCH_SIZE == 0:
                self.logger.debug(f"已添加 {added_count} 个任务，休息 {BATCH_INTERVAL} 秒...")
                import time
                time.sleep(BATCH_INTERVAL)

        return total_tasks

    def _process_user_novels(self, user_works: UserProfile, user_id: str, artist_name: Optional[str],
                             progress_callback: Optional[Callable], check_stopped: Optional[Callable],
                             check_paused: Optional[Callable]) -> int:
        """处理用户的小说作品"""
        novel_ids = user_works.novels

        self.logger.info(f"找到 {len(novel_ids)} 个小说作品")

        # 统计未下载的小说数量
        not_downloaded_ids = [nid for nid in novel_ids if not self.history_manager.is_downloaded(nid, TYPE_NOVEL)]
        not_downloaded_count = len(not_downloaded_ids)

        self.logger.info(f"其中 {not_downloaded_count} 个小说未下载")

        for i, novel_id in enumerate(not_downloaded_ids):
            if check_stopped and check_stopped():
                self.logger.info("检索已停止")
                return not_downloaded_count

            if check_paused:
                check_paused()

            if progress_callback:
                progress = (i + 1) / not_downloaded_count * 100 if not_downloaded_count > 0 else 100
                progress_callback(f'检索小说 {i + 1}/{not_downloaded_count}', progress)

            self.download_novel(novel_id, user_id=user_id, artist_name=artist_name)

        return not_downloaded_count

    def _process_user_collections(self, user_works: UserProfile, user_id: str, artist_name: Optional[str],
                                  progress_callback: Optional[Callable], check_stopped: Optional[Callable],
                                  check_paused: Optional[Callable]) -> int:
        """处理用户的珍藏册"""
        collection_ids = user_works.collections

        self.logger.info(f"找到 {len(collection_ids)} 个珍藏册")

        # 统计未下载的珍藏册数量
        not_downloaded_ids = [cid for cid in collection_ids if
                              not self.history_manager.is_downloaded(cid, TYPE_COLLECTION)]
        not_downloaded_count = len(not_downloaded_ids)

        self.logger.info(f"其中 {not_downloaded_count} 个珍藏册未下载")

        for i, collection_id in enumerate(not_downloaded_ids):
            if check_stopped and check_stopped():
                self.logger.info("检索已停止")
                return not_downloaded_count

            if check_paused:
                check_paused()

            if progress_callback:
                progress = (i + 1) / not_downloaded_count * 100 if not_downloaded_count > 0 else 100
                progress_callback(f'检索珍藏册 {i + 1}/{not_downloaded_count}', progress)

            self.download_collection(collection_id, user_id=user_id, artist_name=artist_name)

        return not_downloaded_count

    def download_artwork(self, artwork_id: str, user_id: str = None,
                         collection_id: str = None, artist_name: str = None,
                         artwork_info: Optional[Any] = None) -> None:
        """
        下载插画（含动图）
        
        Args:
            artwork_id: 插画ID
            user_id: 用户ID（画师模式）
            collection_id: 珍藏册ID
            artist_name: 画师名称
            artwork_info: 缓存的作品信息（可选，避免重复请求）
        """
        try:
            if artwork_info is None:
                artwork_info = self.api_client.get_artwork_info(artwork_id)

            safe_artist_name = self.file_manager.sanitize_filename(artwork_info.user_name)

            # 获取保存目录
            save_dir = self._get_artwork_save_dir(
                artwork_id, user_id, collection_id, artist_name
            )

            if artwork_info.is_ugoira():
                ugoira_meta = self.api_client.get_ugoira_meta(artwork_id)
                if ugoira_meta is not None:
                    self._add_ugoira_task(
                        artwork_id, ugoira_meta, save_dir,
                        safe_artist_name, user_id, collection_id
                    )
                    self.actually_added_tasks += 1
                else:
                    self.logger.warning(f"插画 {artwork_id} 标记为动图但获取元数据失败，尝试作为静态图处理")
                    pages_added = self._add_artwork_tasks(
                        artwork_id, save_dir, safe_artist_name, user_id, artwork_info
                    )
                    self.actually_added_tasks += pages_added
            else:
                # 传递 artwork_info 以便利用缓存的 page_count
                pages_added = self._add_artwork_tasks(
                    artwork_id, save_dir, safe_artist_name, user_id, artwork_info
                )
                self.actually_added_tasks += pages_added

        except Exception as e:
            self.logger.error(f"下载插画 {artwork_id} 失败: {e}")
            # 根据作品信息计算失败的任务数
            if artwork_info:
                if artwork_info.is_ugoira():
                    self.failed_to_add_tasks += 1
                else:
                    self.failed_to_add_tasks += artwork_info.page_count
            else:
                self.failed_to_add_tasks += 1

    def _get_artwork_save_dir(self, artwork_id: str, user_id: Optional[str],
                              collection_id: Optional[str], artist_name: Optional[str]) -> str:
        """获取插画保存目录"""
        if user_id and collection_id:
            return self.file_manager.get_user_collection_directory(
                user_id, collection_id, artist_name
            )
        elif user_id:
            return self.file_manager.get_user_artwork_directory(
                user_id, artist_name=artist_name
            )
        elif collection_id:
            return self.file_manager.get_collection_directory(collection_id)
        else:
            return self.file_manager.get_artwork_directory(artwork_id)

    def _add_ugoira_task(self, artwork_id: str, ugoira_meta: UgoiraMeta, save_dir: str,
                         safe_artist_name: str, user_id: Optional[str],
                         collection_id: Optional[str]) -> None:
        """添加动图下载任务
        Args:
            artwork_id: 插画ID
            ugoira_meta: 动图元数据
            save_dir: 保存目录
            safe_artist_name: 安全的画师名称
            user_id: 用户ID
            collection_id: 珍藏册ID
        """
        delays = ugoira_meta.get_delays()
        zip_url = ugoira_meta.original_src

        if collection_id and not user_id:
            zip_name = f"{artwork_id}.zip"
        else:
            zip_name = f"@{safe_artist_name} {artwork_id}.zip"

        zip_path = os.path.join(save_dir, zip_name)

        if user_id:
            self.current_downloading_works[artwork_id] = 1

        self.download_manager.add_task(
            url=zip_url,
            save_path=zip_path,
            metadata={
                'artwork_id': artwork_id,
                'user_id': user_id,
                'is_ugoira': True,
                'delays': delays,
                'zip_path': zip_path,
                'gif_path': zip_path.replace('.zip', '.gif'),
            }
        )
        self.logger.debug(f"动图 {artwork_id} 已添加到下载队列")

    def _add_artwork_tasks(self, artwork_id: str, save_dir: str,
                           safe_artist_name: str, user_id: Optional[str],
                           artwork_info: Optional[Any] = None) -> int:
        """
        添加静态图下载任务

        Args:
            artwork_id: 插画ID
            save_dir: 保存目录
            safe_artist_name: 安全的画师名称
            user_id: 用户ID
            artwork_info: 缓存的作品信息（可选，避免重复API调用）
        """
        # 如果没有缓存的作品信息，则获取（单个作品下载模式）
        if artwork_info is None:
            artwork_info = self.api_client.get_artwork_info(artwork_id)

        # 获取页面详情（这是必须的API调用，因为需要获取每页的URL）
        pages = self.api_client.get_artwork_pages(artwork_id)

        if user_id:
            self.current_downloading_works[artwork_id] = len(pages)

        for idx, page in enumerate(pages):
            url = page.urls['original']
            original_filename = os.path.basename(url)
            _, ext = os.path.splitext(original_filename)
            new_filename = f"@{safe_artist_name} {artwork_id}_{idx}{ext}"
            save_path = os.path.join(save_dir, new_filename)

            self.download_manager.add_task(
                url=url,
                save_path=save_path,
                metadata={'artwork_id': artwork_id, 'page': idx, 'user_id': user_id}
            )

        self.logger.debug(f"插画 {artwork_id} 已添加到下载队列 ({len(pages)} 张)")
        return len(pages)

    def download_collection(self, collection_id: str, user_id: str = None,
                            artist_name: str = None) -> None:
        """
        下载珍藏册
        
        Args:
            collection_id: 珍藏册ID
            user_id: 用户ID（画师模式）
            artist_name: 画师名称
        """
        try:
            # 获取珍藏册作品
            artworks = self.api_client.get_collection_artworks(collection_id)
            self.logger.info(f"珍藏册 {collection_id} 包含 {len(artworks)} 个作品")

            # 下载每个作品
            for artwork in artworks:
                artwork_id = str(artwork['id'])
                # 画师模式下才检查历史记录
                if user_id and self.history_manager.is_downloaded(artwork_id):
                    self.logger.debug(f"作品 {artwork_id} 已下载，跳过")
                else:
                    self.download_artwork(
                        artwork_id, user_id=user_id,
                        collection_id=collection_id, artist_name=artist_name
                    )

            # 画师模式下，珍藏册本身也记录到历史
            if user_id:
                self.history_manager.add(collection_id, TYPE_COLLECTION)
                self.logger.info(f"珍藏册 {collection_id} 已记录到历史")

        except Exception as e:
            self.logger.error(f"下载珍藏册 {collection_id} 失败: {e}")

    def download_novel(self, novel_id: str, user_id: str = None,
                       artist_name: str = None) -> None:
        """
        下载小说
        
        Args:
            novel_id: 小说ID
            user_id: 用户ID（画师模式）
            artist_name: 画师名称
        """
        try:
            # 使用数据模型获取小说信息
            novel_info = self.api_client.get_novel_content(novel_id)

            if user_id:
                save_path = self.file_manager.get_user_novel_path(
                    user_id, novel_id, novel_info.title, novel_info.user_name, artist_name
                )
            else:
                save_path = self.file_manager.get_novel_path(novel_info.title, novel_info.user_name)

            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(f"标题: {novel_info.title}\n")
                f.write(f"作者: {novel_info.user_name}\n")
                f.write("=" * 50 + "\n\n")
                f.write(novel_info.content)

            self.logger.info(f"小说 {novel_id} 下载完成: {novel_info.title}")

            if user_id:
                self.history_manager.add(novel_id, TYPE_NOVEL)

        except Exception as e:
            self.logger.error(f"下载小说 {novel_id} 失败: {e}")

    def on_task_complete(self, metadata: dict) -> None:
        """
        单个下载任务完成回调
        用于跟踪作品的完整下载状态，并触发动图合成
        
        Args:
            metadata: 任务元数据
        """
        if not metadata:
            return

        artwork_id = metadata.get('artwork_id')
        user_id = metadata.get('user_id')

        # 动图合成
        if metadata.get('is_ugoira'):
            from utils.helpers import compose_ugoira
            zip_path = metadata.get('zip_path')
            gif_path = metadata.get('gif_path')
            delays = metadata.get('delays', [])
            compose_ugoira(zip_path, gif_path, delays)

        # 只在画师模式下处理历史记录
        if not user_id or not artwork_id:
            return

        if artwork_id not in self.current_downloading_works:
            return

        self.current_downloading_works[artwork_id] -= 1

        if self.current_downloading_works[artwork_id] <= 0:
            self.history_manager.add(artwork_id, TYPE_ARTWORK)
            self.logger.debug(f"插画 {artwork_id} 完整下载完成，已记录到历史")
            del self.current_downloading_works[artwork_id]

    def clear_current_works(self) -> None:
        """清空当前下载作品跟踪"""
        self.current_downloading_works.clear()

    def get_download_stats(self) -> dict:
        """
        获取下载统计信息
        
        Returns:
            包含预期、实际添加、失败等统计的字典
        """
        return {
            'expected_tasks': self.expected_tasks,
            'actually_added_tasks': self.actually_added_tasks,
            'failed_to_add_tasks': self.failed_to_add_tasks
        }
