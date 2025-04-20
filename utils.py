import logging
import threading
from functools import wraps

def thread_it(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper

def exclude_log(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    wrapper._exclude_log = True  # 添加排除标记
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

    def decorator(target):
        if isinstance(target, type):
            for name in dir(target):
                attr = getattr(target, name)
                # 添加排除条件：检查是否存在排除标记
                if (callable(attr)
                        and not getattr(attr, '_exclude_log', False)  # 新增排除检查
                        and (not name.startswith('__') or name == '__init__')
                        and hasattr(attr, '__code__')):
                    setattr(target, name, log_wrapper(attr))
            return target
        else:
            return log_wrapper(target) if not getattr(target, '_exclude_log', False) else target

    return decorator
