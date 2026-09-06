"""插件 API:暴露给插件的稳定、版本化边界

插件唯一允许接触的入口是 activate(api) 拿到的 PluginAPI 实例,
实例绑定具体插件 id,负责路由前缀校验、配置键前缀强制等命名空间约束。
"""
import logging

from core import events
from core.config import DEFAULTS as _CONFIG_DEFAULTS
from core.database import (
    count_words,
    get_conn,
    get_db_path,
    get_user_data_dir,
    hash_content,
    next_sort_order,
    restore_soft_delete,
    row_to_dict,
    soft_delete,
)
from core.httpd import convert_keys, jsonify, req_json, request, snake_json

log = logging.getLogger("plugin_api")

# 服务注册表(全局):插件间只允许通过 provide/require 交互,禁止 import 彼此的内部模块
_services = {}


class PluginAPI:
    def __init__(self, plugin_id, manifest, flask_app):
        self.plugin_id = plugin_id
        self.manifest = manifest
        self._app = flask_app
        # 常用 helper 直接透出,插件无需 import core 内部
        self.jsonify = jsonify
        self.request = request
        self.req_json = req_json
        self.snake_json = snake_json
        self.convert_keys = convert_keys

    # ====== HTTP ======

    def route(self, rule, **opts):
        """注册路由。manifest 声明 legacy_routes: true 时允许任意路径(迁移期逃生门,
        做冲突检测);否则强制 /api/plugins/<id>/ 前缀,违反则抛错使插件加载失败"""
        if self.manifest.get("legacy_routes"):
            methods = {m.upper() for m in (opts.get("methods") or ["GET"])}
            if "GET" in methods:
                methods.add("HEAD")
            for r in self._app.routes:
                if r.rule == rule and r.methods & methods:
                    raise ValueError(f"插件 {self.plugin_id} 路由与已有路由冲突: {rule} {sorted(methods)}")
        else:
            prefix = f"/api/plugins/{self.plugin_id}/"
            if not rule.startswith(prefix):
                raise ValueError(f"插件 {self.plugin_id} 路由必须以 {prefix} 开头: {rule}")
        return self._app.route(rule, **opts)

    # ====== 数据 ======

    def db(self):
        """每请求新连接,用法与 core.database.get_conn() 相同"""
        return get_conn()

    def db_path(self):
        """当前数据库文件路径(备份/恢复插件需要)"""
        return get_db_path()

    # core.database 通用 helper 透出
    row_to_dict = staticmethod(row_to_dict)
    soft_delete = staticmethod(soft_delete)
    restore_soft_delete = staticmethod(restore_soft_delete)
    next_sort_order = staticmethod(next_sort_order)
    hash_content = staticmethod(hash_content)
    count_words = staticmethod(count_words)

    @property
    def data_dir(self):
        """插件可用的用户数据目录(与数据库同侧)"""
        return get_user_data_dir()

    # ====== 配置 ======

    def get_config(self, key, default=None):
        """读取配置。正常应读 <id>. 前缀的自有键;迁移期允许只读无前缀 legacy 键"""
        if not key.startswith(self.plugin_id + "."):
            log.debug("插件 %s 读取 legacy 配置键(只读兼容): %s", self.plugin_id, key)
        conn = get_conn()
        try:
            row = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,)).fetchone()
        finally:
            conn.close()
        if row is not None:
            return row["value"]
        return _CONFIG_DEFAULTS.get(key, default)

    def set_config(self, key, value):
        """写入配置,键强制 <id>. 前缀"""
        if not key.startswith(self.plugin_id + "."):
            raise ValueError(f"插件 {self.plugin_id} 配置键必须以 {self.plugin_id}. 开头: {key}")
        conn = get_conn()
        try:
            conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
        finally:
            conn.close()

    # ====== 事件 ======

    def on(self, event, handler):
        events.on(event, handler)

    def emit(self, event, **payload):
        events.emit(event, **payload)

    # ====== 服务注册表 ======

    def provide(self, name, service_dict):
        """声明"我对外提供这些函数";同名后者覆盖前者并记日志"""
        if name in _services:
            log.warning("服务 %s 被插件 %s 重复 provide,覆盖原注册", name, self.plugin_id)
        _services[name] = service_dict

    def require(self, name):
        """消费别的插件的服务,缺失返回 None"""
        return _services.get(name)
