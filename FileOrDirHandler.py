import json
import logging
import os
import re
import sys


class FileHandler:

    # 创建文件夹
    @staticmethod
    def create_directory(*base_dir):
        script_path = os.path.abspath(sys.argv[0])  # 获取绝对路径
        parent_dir = os.path.dirname(script_path)
        mkdir = os.path.join(parent_dir, *base_dir)
        os.makedirs(mkdir, exist_ok=True)
        return mkdir

    # 读取json文件
    @staticmethod
    def read_json():
        json_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "pixivCrawl.json")
        default_data = {
            "PHPSESSID": "",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
        }
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'PHPSESSID' not in data:
                    data["PHPSESSID"] = ""
                    FileHandler.update_json('')
                return data
        except FileNotFoundError:
            logging.info("未找到配置文件，正在创建默认配置文件。")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
            return default_data

    # 更新json文件
    @staticmethod
    def update_json(data_id):
        json_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "pixivCrawl.json")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data["PHPSESSID"] = data_id.replace("PHPSESSID=", "")

        with open(json_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=4))
        logging.info(f"成功更新配置文件，下次失效时再进行填写。")

    # 创建或更新文件，清空文件内容
    @staticmethod
    def touch(file_path):
        try:
            with open(file_path, 'wb') as f:
                f.truncate(0)
        except OSError as e:
            logging.error(f"无法创建文件 {file_path}，错误原因：{e}")

    # 获取资源文件的绝对路径
    @staticmethod
    def resource_path(relative_path):
        # PyInstaller 创建临时文件夹，所有 pyInstaller 程序运行时解压后的文件都在 _MEIPASS 中
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path is None:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    @staticmethod
    def sanitize_filename(filename):
        # 移除Windows的非法字符
        cleaned = re.sub(r'[\\/*?:"<>|]', "_", filename)
        return cleaned.strip()
