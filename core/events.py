"""后端事件总线:插件间解耦的极简 publish/subscribe

事件名约定 <plugin_id>.<动作>(如 chapter.deleted),内核不做注册限制。
处理器异常只记日志,不影响其他订阅者和发送方。
"""
import logging
import threading

log = logging.getLogger("events")

_lock = threading.RLock()
_handlers = {}


def on(event, handler):
    """订阅事件;handler 以 **payload 形式被调用"""
    with _lock:
        _handlers.setdefault(event, []).append(handler)


def off(event, handler):
    """取消订阅;不存在时静默忽略"""
    with _lock:
        handlers = _handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)


def emit(event, **payload):
    """发布事件;拷贝订阅者快照后逐个调用,允许处理器内增删订阅"""
    with _lock:
        handlers = list(_handlers.get(event, []))
    for handler in handlers:
        try:
            handler(**payload)
        except Exception:
            log.exception("事件 %s 的处理器异常", event)
