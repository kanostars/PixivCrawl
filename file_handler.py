import json
import logging
import os
import sys

relative_base_path = os.path.dirname(os.path.abspath(sys.argv[0]))

default_data = {
    "cookie": "",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
}


# 创建文件夹
def create_directory(*base_dir):
    mkdir = os.path.join(relative_base_path, *base_dir)
    os.makedirs(mkdir, exist_ok=True)
    return mkdir


# 创建或更新文件，清空文件内容
def touch(file_path):
    with open(file_path, 'wb') as f:
        f.truncate(0)


# 获取资源文件的绝对路径
def resource_path(relative_path):
    # PyInstaller 临时文件夹
    base_path = getattr(sys, '_MEIPASS', None)
    if base_path is None:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# 读取json文件
def read_json():
    json_file = os.path.join(relative_base_path, "pixivCrawl.json")
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'cookie' not in data:
                data['cookie'] = ''
            if 'user_agent' not in data:
                data['user_agent'] = default_data['user_agent']
            return data
    except FileNotFoundError:
        logging.info("未找到配置文件，正在创建默认配置文件。")
        with open(json_file, 'w', encoding='utf-8') as f:
            out = json.dumps(default_data, indent=4, ensure_ascii=False)
            f.write(out)
        return default_data


# 更新json文件
def update_json(data):
    json_file = os.path.join(relative_base_path, "pixivCrawl.json")

    with open(json_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=4))
    logging.info(f"成功更新配置文件")
