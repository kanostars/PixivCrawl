import re
import os
import logging
import webbrowser
from urllib.parse import urlparse
from config.settings import LINK_ENDPOINTS, BASE_URL, TYPE_USER, TYPE_ARTWORK, TYPE_COLLECTION, TYPE_NOVEL
import json
import html
import zipfile
from PIL import Image


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} 分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} 小时"


def validate_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    # 移除非法字符
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')

    # 移除前后空格
    filename = filename.strip()

    # 限制长度
    if len(filename) > max_length:
        filename = filename[:max_length]

    return filename


def extract_id(input_text: str, type_name: str) -> str:
    # 如果是纯数字，直接返回
    if input_text.isdigit():
        return input_text

    # 特殊处理小说
    if 'novel/show.php' in input_text:
        id_match = re.search(r'[?&]id=(\d+)', input_text)
        if id_match:
            return id_match.group(1)

    # 构建正则表达式，匹配 /type_name/数字
    pattern = rf'/{re.escape(type_name)}/(\d+)'
    match = re.search(pattern, input_text)
    if match:
        return match.group(1)

    # 如果没有匹配到，尝试提取URL中的任何数字ID（作为后备）
    clean_url = re.split(r'[?#]', input_text)[0]
    id_match = re.search(r'/(\d+)(?:/|$)', clean_url)
    if id_match:
        return id_match.group(1)

    return input_text


def analysis_id(input_text: str, type_name: str) -> str:
    input_text = input_text.strip()

    # 判断是否已经是完整链接
    if input_text.startswith('http://') or input_text.startswith('https://'):
        return input_text

    # 判断是否是纯数字ID
    if input_text.isdigit():
        # 根据类型拼接链接
        if type_name in LINK_ENDPOINTS:
            endpoint = LINK_ENDPOINTS[type_name]
            if type_name == TYPE_USER:
                link = endpoint.replace('{user_id}', input_text)
            elif type_name == TYPE_ARTWORK:
                link = endpoint.replace('{artwork_id}', input_text)
            elif type_name == TYPE_COLLECTION:
                link = endpoint.replace('{collection_id}', input_text)
            elif type_name == TYPE_NOVEL:
                link = endpoint.replace('{novel_id}', input_text)
            else:
                link = endpoint

            return BASE_URL + link
        else:
            return input_text

    if 'pixiv.net' in input_text:
        if not input_text.startswith('http'):
            return 'https://' + input_text
        return input_text

    return input_text


def extract_username(page_content):
    # 没有二次验证的情况
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        page_content, re.DOTALL
    )
    if match:
        next_data = json.loads(match.group(1))
        user_data = json.loads(next_data['props']['pageProps']['serverSerializedPreloadedState'])
        if user_data.get('userData') and user_data['userData'].get('self'):
            return user_data['userData']['self']['name']

    #  有二次验证的情况 - 从 init-config 提取
    init_config_match = re.search(
        r'<input[^>]*id="init-config"[^>]*value="([^"]*)"',
        page_content
    )
    if init_config_match:
        # 获取 value 属性值并解码 HTML 实体
        config_value = html.unescape(init_config_match.group(1))
        config_data = json.loads(config_value)

        # 提取用户名
        username = config_data.get('pixivAccount.sessionUser.userName')
        if username:
            return username
    return None


def open_directory(directory_path: str) -> None:
    """打开指定目录"""
    try:
        if os.path.exists(directory_path):
            webbrowser.open(directory_path)
        else:
            logging.warning(f"目录不存在: {directory_path}")
    except Exception as e:
        logging.error(f"打开目录失败: {e}")


def compose_ugoira(zip_path: str, gif_path: str, delays: list[int]) -> bool:
    """
    将 Ugoira ZIP 合成为 GIF

    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            image_files = sorted(
                f for f in zip_ref.namelist()
                if f.lower().endswith(('.png', '.jpg', '.jpeg'))
            )
            if not image_files:
                return False

            images = [
                Image.open(zip_ref.open(f)).convert('RGBA')
                for f in image_files
            ]

        images[0].save(
            gif_path,
            save_all=True,
            append_images=images[1:],
            duration=delays,
            loop=0
        )

        os.remove(zip_path)
        logging.info(f"动图合成完成: {gif_path}")
        return True

    except Exception as e:
        logging.error(f"动图合成失败: {zip_path}, 错误: {e}")
        return False
