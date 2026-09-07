"""插件协议符合性测试(纯标准库,直接 python tests/run_conformance.py 运行)

在临时目录构造 fixture 插件,验证:
- 合法插件:路由注册、迁移建表、plugin_migrations 记录、provide/require、事件总线
- 坏插件(manifest 缺字段):标记 failed,不影响好插件(故障隔离)
"""
import json
import os
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database, events, plugin_manager
from core.database import set_db_path, get_conn
from core.httpd import Flask
from core.plugin_api import PluginAPI

GOOD_BACKEND = '''
class Plugin:
    def activate(self, api):
        @api.route("/api/plugins/fixture_good/ping", methods=["GET"])
        def ping():
            return api.jsonify({"pong": True})

        api.provide("fixture", {"hello": lambda: "world"})
        api.emit("fixture.activated", source="fixture_good")
        api.register_entity(entity="item", table="fixture_good__items", label="条目",
                            export=True, export_order=42)
'''

GOOD_MIGRATION = """
CREATE TABLE IF NOT EXISTS fixture_good__items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
"""


def _write_plugin(base, dirname, manifest, backend=None, migration=None):
    d = Path(base) / dirname
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if backend is not None:
        (d / "backend.py").write_text(backend, encoding="utf-8")
    if migration is not None:
        (d / "migrations").mkdir()
        (d / "migrations" / "001_init.sql").write_text(migration, encoding="utf-8")


_failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="nw_conformance_")
    db_file = os.path.join(tmp, "test.db")
    set_db_path(db_file)  # 全新库:无 db_version,不触发 legacy_bootstrap

    plugins_dir = Path(tmp) / "plugins"
    user_dir = Path(tmp) / "user_plugins"
    _write_plugin(plugins_dir, "fixture_good", {
        "id": "fixture_good", "name": "好插件", "version": "1.0.0",
        "api_version": 1, "entry": "backend.py",
    }, backend=GOOD_BACKEND, migration=GOOD_MIGRATION)
    _write_plugin(plugins_dir, "fixture_bad", {
        # 缺 name / version / api_version / entry
        "id": "fixture_bad",
    }, backend="class Plugin:\n    def activate(self, api):\n        pass\n")

    app = Flask("conformance")

    received = []
    events.on("fixture.activated", lambda **kw: received.append(kw))

    plugin_manager.discover(builtin_dir=plugins_dir, user_dir=user_dir)
    plugin_manager.load_all(app)

    reg = {r["id"]: r for r in plugin_manager.registry()}

    # --- 好插件 ---
    check("好插件加载成功", reg.get("fixture_good", {}).get("status") == "loaded",
          str(reg.get("fixture_good")))
    check("路由已注册到 Flask app",
          any(r.rule == "/api/plugins/fixture_good/ping" for r in app.routes))

    conn = get_conn()
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fixture_good__items'"
    ).fetchone()
    mig = conn.execute(
        "SELECT version FROM plugin_migrations WHERE plugin_id='fixture_good' AND version=1"
    ).fetchone()
    conn.close()
    check("迁移已建表", table is not None)
    check("plugin_migrations 已记录", mig is not None)

    consumer = PluginAPI("consumer", {"id": "consumer"}, app)
    svc = consumer.require("fixture")
    check("服务可 require", svc is not None and svc["hello"]() == "world")
    check("事件可收到", received == [{"source": "fixture_good"}], str(received))

    # --- 实体注册表 ---
    entities = consumer.list_entities()
    fixture_entity = next((e for e in entities
                           if e["plugin_id"] == "fixture_good" and e["entity"] == "item"), None)
    check("fixture 注册的实体可 list_entities 查到", fixture_entity is not None, str(entities))
    check("实体注册信息字段完整", fixture_entity == {
        "plugin_id": "fixture_good", "entity": "item",
        "table": "fixture_good__items", "label": "条目",
        "name_column": "title", "export": True, "export_order": 42,
    }, str(fixture_entity))

    dup_error = None
    try:
        consumer.register_entity(entity="item2", table="t", label="x")
        consumer.register_entity(entity="item2", table="t", label="x")
    except ValueError as e:
        dup_error = str(e)
    check("同一插件重复注册同一实体抛错", dup_error is not None and "重复注册实体" in dup_error,
          str(dup_error))

    # 模拟 recycle 的消费方式:按 list_entities() 构建 entity -> (table, name_column) 映射
    entity_tables = {e["entity"]: (e["table"], e["name_column"]) for e in consumer.list_entities()}
    check("recycle 式消费可见 fixture 实体",
          entity_tables.get("item") == ("fixture_good__items", "title"), str(entity_tables))

    # --- 坏插件 ---
    check("坏插件标记 failed", reg.get("fixture_bad", {}).get("status") == "failed",
          str(reg.get("fixture_bad")))
    check("坏插件错误信息含缺字段说明",
          "缺少必填字段" in (reg.get("fixture_bad", {}).get("error") or ""))

    # --- 迁移幂等:重跑不重复执行 ---
    plugin_manager._reset()
    set_db_path(db_file)
    app2 = Flask("conformance2")
    plugin_manager.discover(builtin_dir=plugins_dir, user_dir=user_dir)
    plugin_manager.load_all(app2)
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM plugin_migrations WHERE plugin_id='fixture_good'"
    ).fetchone()["c"]
    conn.close()
    check("迁移幂等(重复加载不重复记录)", count == 1, f"count={count}")

    database.set_db_path(None)
    if _failures:
        print(f"\n{len(_failures)} 项失败")
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
