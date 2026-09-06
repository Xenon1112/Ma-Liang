"""miniframe - 纯标准库实现的 Flask API 子集 shim

仅实现 app.py 用到的接口：
- Flask(name, static_folder, static_url_path, template_folder)
  .route(path, methods=[...]) 装饰器（支持 <int:name> / <path:name> / 精确路径）
  .errorhandler(code_or_exception) 装饰器
  .run(host, port, debug=False) / .shutdown()
- request：threading.local 请求上下文（.path / .args.get(k, type=int) / .get_json(silent=True)）
- jsonify(obj)：返回 Response，支持 (jsonify(...), 201) 元组返回值
- send_from_directory(dir, filename)：静态文件，防目录穿越

基于 http.server.ThreadingHTTPServer + BaseHTTPRequestHandler。
"""
import json
import logging
import mimetypes
import os
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

log = logging.getLogger("miniframe")

# Windows 注册表里的 MIME 经常不可靠（如 .js 被映射成 text/plain），显式覆盖
MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
}

_CONVERTERS = {
    "int": (r"\d+", int),
    "path": (r".+", str),
    "string": (r"[^/]+", str),
}


class _HTTPError(Exception):
    """内部用：中断视图处理并以指定状态码走错误处理流程"""

    def __init__(self, code, description="", headers=None):
        super().__init__(description or f"HTTP {code}")
        self.code = code
        self.headers = dict(headers or {})


class _MethodNotAllowed(_HTTPError):
    """路径匹配但方法不允许（Flask 语义：405 + Allow 头；OPTIONS 自动应答）"""

    def __init__(self, allowed):
        allowed = sorted(set(allowed) | {"OPTIONS"})
        super().__init__(405, "Method Not Allowed", {"Allow": ", ".join(allowed)})
        self.allowed = allowed


class Response:
    """可直接作为路由返回值的响应对象"""

    def __init__(self, body=b"", status=200, content_type="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.status = status
        self.content_type = content_type
        self.headers = dict(headers or {})


def jsonify(obj):
    """等价 flask.jsonify：JSON 响应，ensure_ascii=False 保留中文"""
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return Response(body, 200, "application/json; charset=utf-8")


class _Args:
    """GET 参数。get(key, default=None, type=None)：type 转换失败返回 default（Flask 语义）"""

    def __init__(self, query_string):
        self._data = {}
        for k, v in parse_qsl(query_string, keep_blank_values=True):
            if k not in self._data:
                self._data[k] = v

    def get(self, key, default=None, type=None):
        if key not in self._data:
            return default
        value = self._data[key]
        if type is None:
            return value
        try:
            return type(value)
        except (ValueError, TypeError):
            return default


class _Request:
    def __init__(self, method, path, args, body, headers):
        self.method = method
        self.path = path
        self.args = args
        self._body = body
        self.headers = headers
        self._json_cache = ...

    def get_json(self, silent=False):
        if self._json_cache is ...:
            try:
                self._json_cache = json.loads(self._body.decode("utf-8")) if self._body else None
            except (ValueError, UnicodeDecodeError):
                self._json_cache = None
        if self._json_cache is None and not silent:
            raise _HTTPError(400, "请求体不是合法 JSON")
        return self._json_cache


_local = threading.local()


class _RequestProxy:
    """模块级 request 对象，转发到当前线程的请求上下文"""

    def __getattr__(self, name):
        req = getattr(_local, "request", None)
        if req is None:
            raise RuntimeError("miniframe: 当前线程没有活动的请求上下文")
        return getattr(req, name)


request = _RequestProxy()


# ====== camelCase → snake_case 转换(请求 JSON 工具) ======

def camel_to_snake(name):
    """projectId → project_id"""
    s = re.sub(r'([A-Z])', r'_\1', name)
    return s.lower().lstrip('_')


def convert_keys(obj):
    """递归转换 dict 的所有 key 从 camelCase 到 snake_case"""
    if isinstance(obj, dict):
        return {camel_to_snake(k): convert_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_keys(item) for item in obj]
    return obj


def req_json():
    """获取请求 JSON(保留原始 camelCase key)"""
    return request.get_json(silent=True) or {}


def snake_json():
    """获取请求 JSON(转换 key 为 snake_case,供 service 调用)"""
    return convert_keys(req_json())


def _guess_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def send_from_directory(directory, filename):
    """发送静态文件；防目录穿越；不存在抛 404"""
    directory = os.path.abspath(directory)
    # 拒绝绝对路径与 .. 穿越
    full = os.path.abspath(os.path.join(directory, filename))
    if full != directory and not full.startswith(directory + os.sep):
        raise _HTTPError(404)
    if not os.path.isfile(full):
        raise _HTTPError(404)
    with open(full, "rb") as f:
        body = f.read()
    # 本地桌面应用禁用缓存，避免内置浏览器缓存旧 CSS/JS/HTML 导致界面更新不生效
    return Response(body, 200, _guess_type(full), headers={"Cache-Control": "no-store"})


class _Route:
    def __init__(self, rule, methods, func):
        self.rule = rule  # 保留原始规则串,供插件路由冲突检测
        self.methods = {m.upper() for m in (methods or ["GET"])}
        if "GET" in self.methods:
            self.methods.add("HEAD")
        self.func = func
        self.converters = {}
        pattern = re.sub(
            r"<(?:(\w+):)?(\w+)>",
            lambda m: self._converter_group(m),
            rule,
        )
        self.regex = re.compile("^" + pattern + "$")

    def _converter_group(self, m):
        kind, name = m.group(1) or "string", m.group(2)
        pat, conv = _CONVERTERS.get(kind, _CONVERTERS["string"])
        self.converters[name] = conv
        return f"(?P<{name}>{pat})"

    def match(self, path):
        m = self.regex.match(path)
        if not m:
            return None
        return {k: self.converters[k](v) for k, v in m.groupdict().items()}


class Flask:
    def __init__(self, import_name, static_folder=None, static_url_path=None, template_folder=None):
        self.import_name = import_name
        self.static_folder = static_folder
        self.template_folder = template_folder
        self.debug = False
        self.routes = []
        self.error_handlers = {}  # int 状态码 或 Exception 子类 -> func
        self._server = None
        if static_folder and static_url_path:
            folder = static_folder
            self.route(static_url_path.rstrip("/") + "/<path:filename>")(
                lambda filename: send_from_directory(folder, filename)
            )

    def route(self, rule, methods=None):
        def decorator(func):
            self.routes.append(_Route(rule, methods, func))
            return func
        return decorator

    def errorhandler(self, code_or_exception):
        def decorator(func):
            self.error_handlers[code_or_exception] = func
            return func
        return decorator

    # ====== 请求分发 ======

    def _find_route(self, path, method):
        allowed = set()
        for route in self.routes:
            kwargs = route.match(path)
            if kwargs is None:
                continue
            allowed |= route.methods
            if method in route.methods:
                return route.func, kwargs
        if allowed:
            raise _MethodNotAllowed(allowed)
        return None

    def _exception_handler(self, exc):
        for key, func in self.error_handlers.items():
            if isinstance(key, type) and issubclass(key, Exception) and isinstance(exc, key):
                return func
        return None

    def _normalize(self, result):
        status = None
        if isinstance(result, tuple):
            result, status = result[0], result[1]
        if isinstance(result, Response):
            resp = result
        elif isinstance(result, (dict, list)):
            resp = jsonify(result)
        elif isinstance(result, (str, bytes)):
            resp = Response(result, 200, "text/html; charset=utf-8")
        elif result is None:
            resp = Response(b"", 200, "text/html; charset=utf-8")
        else:
            resp = jsonify(result)
        if status is not None:
            resp.status = status
        return resp

    def _error_response(self, code, exc):
        handler = self.error_handlers.get(code)
        try:
            if handler:
                resp = self._normalize(handler(exc))
                resp.headers.update(getattr(exc, "headers", {}))
                return resp
        except Exception:
            log.exception("错误处理函数本身抛出异常")
            return Response(f"500 Internal Server Error", 500, "text/plain; charset=utf-8")
        return Response(f"{code} {exc}", code, "text/plain; charset=utf-8",
                        headers=getattr(exc, "headers", None))

    def dispatch(self, req):
        try:
            found = self._find_route(req.path, req.method)
            if not found:
                raise _HTTPError(404)
            func, kwargs = found
            return self._normalize(func(**kwargs))
        except _MethodNotAllowed as e:
            if req.method == "OPTIONS":
                # Flask 自动应答 OPTIONS：200 空 body + Allow 头
                return Response(b"", 200, "text/html; charset=utf-8", headers=e.headers)
            return self._error_response(405, e)
        except _HTTPError as e:
            return self._error_response(e.code, e)
        except Exception as e:
            handler = self._exception_handler(e)
            if handler:
                try:
                    return self._normalize(handler(e))
                except Exception as e2:
                    log.exception("异常处理函数本身抛出异常")
                    return self._error_response(500, e2)
            if self.debug:
                traceback.print_exc()
            return self._error_response(500, e)

    # ====== 服务启动/停止 ======

    def run(self, host="127.0.0.1", port=5000, debug=False):
        self.debug = debug
        app = self

        class Handler(_RequestHandler):
            flask_app = app

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        log.info("miniframe 监听 http://%s:%s", host, port)
        try:
            self._server.serve_forever(poll_interval=0.2)
        finally:
            self._server.server_close()

    def shutdown(self):
        """优雅停止 HTTPServer（serve_forever 返回），可从任意线程调用"""
        srv = self._server
        if srv is not None:
            threading.Thread(target=srv.shutdown, daemon=True).start()


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    flask_app = None  # 由 Flask.run 注入

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()

    def _handle(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""

        parts = urlsplit(self.path)
        req = _Request(
            method=self.command,
            path=unquote(parts.path),
            args=_Args(parts.query),
            body=body,
            headers=self.headers,
        )
        _local.request = req
        try:
            resp = self.flask_app.dispatch(req)
        except Exception:
            # dispatch 内部已兜底，这里是最后保险
            log.exception("请求处理出现未兜底异常")
            resp = Response("500 Internal Server Error", 500, "text/plain; charset=utf-8")
        finally:
            _local.request = None

        try:
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(resp.body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端提前断开，忽略
