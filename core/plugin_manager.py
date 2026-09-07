"""插件管理器:发现、校验、依赖排序、加载插件

两个插件源:
- 内置:开发态 = 项目根/plugins;frozen 态 = sys._MEIPASS/plugins(默认加载)
- 第三方:get_user_data_dir()/plugins/(本期默认不加载,标记 pending,待阶段 4 做启用流程)

故障隔离:任何插件加载失败只标记自身 failed,不影响其余插件。
"""
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

from core import registry as _entity_registry
from core.database import get_conn, get_user_data_dir
from core.plugin_api import PluginAPI

log = logging.getLogger("plugin_manager")

API_VERSION = 1
REQUIRED_FIELDS = ("id", "name", "version", "api_version", "entry")
MIGRATION_FILE_RE = re.compile(r"^(\d+)_.*\.sql$")

# id(或坏插件的目录名) -> {manifest, dir, source, status, error, instance}
# status: discovered(待加载) / loaded / failed / pending(第三方待启用)
_plugins = {}
_load_order = []
_legacy_db = None


def builtin_plugins_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "plugins"
    return Path(__file__).resolve().parent.parent / "plugins"


def _reset():
    """清空全部状态(供测试复用)"""
    global _legacy_db
    _plugins.clear()
    _load_order.clear()
    _legacy_db = None
    _entity_registry._reset()


def discover(builtin_dir=None, user_dir=None):
    """扫描插件目录并校验 manifest,然后拓扑排序。幂等:重复调用不重来"""
    if _plugins:
        return
    builtin_dir = Path(builtin_dir) if builtin_dir else builtin_plugins_dir()
    user_dir = Path(user_dir) if user_dir else get_user_data_dir() / "plugins"
    user_dir.mkdir(parents=True, exist_ok=True)
    # 内置先扫:用户目录插件与之 id 冲突时跳过用户目录那个
    for source, base in (("builtin", builtin_dir), ("user", user_dir)):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or not (child / "plugin.json").is_file():
                continue
            info = _read_manifest(child, source)
            pid = info["manifest"]["id"] if info["manifest"] else child.name
            if pid in _plugins:
                log.error("插件 id 冲突: %s(%s)已存在,跳过 %s", pid, _plugins[pid]["dir"], child)
                continue
            _plugins[pid] = info
    _topo_sort()


def _read_manifest(plugin_dir, source):
    info = {
        "manifest": None,
        "dir": str(plugin_dir),
        "source": source,
        # 第三方插件本期默认不加载,只记录为待启用
        "status": "pending" if source == "user" else "discovered",
        "error": None,
        "instance": None,
    }
    try:
        manifest = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
        missing = [f for f in REQUIRED_FIELDS if f not in manifest]
        if missing:
            raise ValueError(f"plugin.json 缺少必填字段: {', '.join(missing)}")
        if manifest["id"] != plugin_dir.name:
            raise ValueError(f"插件 id({manifest['id']})与目录名({plugin_dir.name})不一致")
        if not isinstance(manifest["api_version"], int) or manifest["api_version"] > API_VERSION:
            raise ValueError(f"api_version {manifest['api_version']} 不兼容(内核支持 <= {API_VERSION})")
        if not (plugin_dir / manifest["entry"]).is_file():
            raise ValueError(f"入口文件不存在: {manifest['entry']}")
        info["manifest"] = manifest
    except Exception as e:
        info["status"] = "failed"
        info["error"] = str(e)
        log.error("插件 manifest 校验失败: %s: %s", plugin_dir, e)
    return info


def _topo_sort():
    """按 dependencies(缺失则不加载)/ optional_dependencies(有则排前)排序;循环依赖整环跳过"""
    global _load_order
    candidates = {pid: info for pid, info in _plugins.items() if info["status"] == "discovered"}
    # 硬依赖缺失的插件不加载(可能级联,迭代剔除)
    changed = True
    while changed:
        changed = False
        for pid, info in list(candidates.items()):
            for dep in info["manifest"].get("dependencies", []):
                if dep not in candidates:
                    info["status"] = "failed"
                    info["error"] = f"依赖缺失: {dep}"
                    log.error("插件 %s 依赖缺失: %s,不加载", pid, dep)
                    del candidates[pid]
                    changed = True
                    break
    # Kahn 拓扑排序
    edges = {}
    indegree = {pid: 0 for pid in candidates}
    for pid, info in candidates.items():
        m = info["manifest"]
        deps = list(m.get("dependencies", []))
        deps += [d for d in m.get("optional_dependencies", []) if d in candidates]
        for dep in deps:
            edges.setdefault(dep, []).append(pid)
            indegree[pid] += 1
    queue = sorted(pid for pid, d in indegree.items() if d == 0)
    order = []
    while queue:
        pid = queue.pop(0)
        order.append(pid)
        for nxt in sorted(edges.get(pid, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    for pid, d in indegree.items():
        if d > 0:
            candidates[pid]["status"] = "failed"
            candidates[pid]["error"] = "存在循环依赖"
            log.error("插件 %s 存在循环依赖,整环跳过", pid)
    _load_order = order


def _is_legacy_db():
    """存量用户库:db_version 表存在且 >= 6,说明各内置插件的表已由全局 V1..V6 建好"""
    global _legacy_db
    if _legacy_db is None:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'"
            ).fetchone()
            v = conn.execute("SELECT MAX(version) AS v FROM db_version").fetchone()["v"] if row else 0
            _legacy_db = (v or 0) >= 6
        finally:
            conn.close()
    return _legacy_db


def _apply_migrations(pid, info, legacy):
    """应用插件 migrations/*.sql(NNN_描述.sql,按 NNN 排序),已应用的跳过,事务执行"""
    mdir = Path(info["dir"]) / "migrations"
    conn = get_conn()
    try:
        # init_db() 之外独立兜底(import 时插件加载早于 init_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_migrations (
                plugin_id   TEXT NOT NULL,
                version     INTEGER NOT NULL,
                applied_at  TEXT NOT NULL,
                PRIMARY KEY (plugin_id, version)
            )
        """)
        conn.commit()
        if not mdir.is_dir():
            return
        files = []
        for f in mdir.iterdir():
            m = MIGRATION_FILE_RE.match(f.name)
            if m:
                files.append((int(m.group(1)), f))
        files.sort(key=lambda t: t[0])
        applied = {r["version"] for r in conn.execute(
            "SELECT version FROM plugin_migrations WHERE plugin_id = ?", (pid,))}
        for ver, f in files:
            if ver in applied:
                continue
            if legacy and info["source"] == "builtin":
                # 老库:内置插件的表大多已由全局 V1..V6 建好,但后加的内置插件(如 graph)
                # 在存量库上还没有表;迁移 SQL 一律 CREATE TABLE IF NOT EXISTS 幂等,
                # 照常执行(已有表是 no-op),不能只标记跳过
                log.info("插件 %s 迁移 %03d 在存量库上按幂等 SQL 照常执行", pid, ver)
            sql = f.read_text(encoding="utf-8")
            try:
                conn.execute("BEGIN")
                for stmt in sql.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
                conn.execute(
                    "INSERT INTO plugin_migrations (plugin_id, version, applied_at) VALUES (?, ?, datetime('now','localtime'))",
                    (pid, ver))
                conn.commit()
                log.info("插件 %s 迁移 %03d 已应用", pid, ver)
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()


def load_all(flask_app):
    """按拓扑序加载全部待加载插件;单个失败只标记 failed,继续其余(故障隔离)"""
    if not _plugins:
        discover()
    legacy = _is_legacy_db()
    for pid in _load_order:
        info = _plugins[pid]
        if info["status"] != "discovered":
            continue
        try:
            _apply_migrations(pid, info, legacy)
            entry = Path(info["dir"]) / info["manifest"]["entry"]
            spec = importlib.util.spec_from_file_location(f"nw_plugin_{pid}", str(entry))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            instance = module.create_plugin() if hasattr(module, "create_plugin") else module.Plugin()
            instance.activate(PluginAPI(pid, info["manifest"], flask_app))
            info["instance"] = instance
            info["status"] = "loaded"
            log.info("插件已加载: %s v%s", pid, info["manifest"].get("version"))
        except Exception as e:
            info["status"] = "failed"
            info["error"] = str(e)
            log.exception("插件加载失败: %s", pid)


def get_plugin_dir(pid):
    """已加载插件的目录(供内核 serve 插件前端资源);未加载/不存在返回 None"""
    info = _plugins.get(pid)
    if not info or info["status"] != "loaded":
        return None
    return info["dir"]


def registry():
    """各插件 manifest 与状态清单(供前端插件管理界面使用)"""
    return [
        {
            "id": pid,
            "manifest": info["manifest"],
            "source": info["source"],
            "status": info["status"],
            "error": info["error"],
        }
        for pid, info in _plugins.items()
    ]
