class PixivException(Exception):
    """Pixiv 下载器基础异常"""
    pass


class NetworkException(PixivException):
    """网络请求异常"""
    pass


class AuthenticationException(PixivException):
    """认证失败异常"""
    pass


class ResourceNotFoundException(PixivException):
    """资源不存在异常"""
    pass


class DownloadException(PixivException):
    """下载失败异常"""
    pass


class FileOperationException(PixivException):
    """文件操作异常"""
    pass


class ConfigurationException(PixivException):
    """配置错误异常"""
    pass
