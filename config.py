from FileHandlerManager import FileHandlerManager

# 类型常量
TYPE_WORKER = "users"  # 类型是画师
TYPE_ARTWORKS = "artworks"  # 类型是插画
TYPE_COLLECTION = "collection"  # 类型是收藏册
TYPE_NOVEL = "novel"  # 类型是小说

# 类型配置映射
type_config = {
    0: TYPE_WORKER,  # 画师
    1: TYPE_ARTWORKS,  # 插画
    2: TYPE_COLLECTION,  # 收藏册
    3: TYPE_NOVEL  # 小说
}

# 读取配置
_config = FileHandlerManager.read_json()
user_agent = _config["user_agent"]
cookies = f'PHPSESSID={_config["PHPSESSID"]}'

# 支持的语言
languages = {
    "zh_tw": ["的插畫", "的漫畫", "的動畫"],
    "zh": ["的插画", "的漫画", "的动图"],
    "ja": ["のイラスト", "のマンガ", "のうごイラ"],
    "ko": ["의 일러스트", "의 만화", "의 우고이라"]
}
