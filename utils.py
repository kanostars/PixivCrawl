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
            logging.log(log_level, f'{func.__name__} start')
            re = func(*args, **kwargs)
            logging.log(log_level, f'{func.__name__} end')
            return re
        return wrapper
    return log_wrapper

