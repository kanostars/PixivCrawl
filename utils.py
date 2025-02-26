import logging
import threading
import time
from functools import wraps

def thread_it(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper

def log_it(log_level=logging.DEBUG):
    def log_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取参数签名信息
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # 构建带参数名的参数字符串
            param_pairs = []
            for name, value in bound_args.arguments.items():
                param_pairs.append(f"{name}={value!r}")

            logging.log(log_level, f'{func.__name__} start - params: ({", ".join(param_pairs)})')
            re = func(*args, **kwargs)
            logging.log(log_level, f'{func.__name__} end')
            return re
        return wrapper
    return log_wrapper

