import time
import threading


class RateLimiter:
    """请求限速器，控制 API 请求频率"""

    def __init__(self, rate_per_second: float = 4.0) -> None:
        """
        初始化限速器
        
        Args:
            rate_per_second: 每秒允许的请求数
        """
        self.rate_per_second = rate_per_second
        self.min_interval = 1.0 / rate_per_second
        self.last_request_time = 0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        """获取请求许可，如果超过速率限制则等待"""
        with self.lock:
            current_time = time.time()
            time_since_last_request = current_time - self.last_request_time

            if time_since_last_request < self.min_interval:
                sleep_time = self.min_interval - time_since_last_request
                time.sleep(sleep_time)

            self.last_request_time = time.time()
