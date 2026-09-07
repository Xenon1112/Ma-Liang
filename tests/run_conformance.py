"""插件协议符合性测试(纯标准库,直接 python tests/run_conformance.py 运行)

- 在临时目录构造 fixture 插件,验证:
  合法插件:路由注册、迁移建表、plugin_migrations 记录、provide/require、事件总线;
  坏插件(manifest 缺字段):标记 failed,不影响好插件(故障隔离)
- 总验收插件 tests/fixtures/km_counter/(第三方形态,不用 legacy_routes):
  拷入临时插件目录经 plugin_manager 加载,验证实体注册表/list_entities、
  json_transfer 导出导入回环(fk 重映射)、路由前缀强制、manifest web 字段返回
- graph 地基插件(内置形态拷入):加载/迁移、/api/plugins/graph/ 前缀路由、
  类型注册表(重复注册抛错)、create_node 拒绝未注册类型、
  创建→list_children→reorder→级联软删全链路
- G4a chapter 插件正文 text 节点化(连带依赖链 json_transfer/project 拷入):
  预置老库种子数据(空章/长文/软删章,正文存 drafts 当前版本)后加载,
  验证 text 类型注册、002 迁移内容与软删携带、SQL 重放幂等、
  新建章节自动建空节点/删除章节级联软删节点的读写回环、get/list 返回形状不变
- 前端扩展点(sidebar.tabs/toolbar.actions/事件订阅/graph 渲染器注册表):子进程跑
  tests/web_stub_test.js(node),node 不可用时跳过并提示
"""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
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
                            export=True, export_order=42,
                            fk={"project_id": "project"})
        # 附属表:无 project_id,靠 fk 挂靠 item;recycle=False 不进回收站
        api.register_entity(entity="sub", table="fixture_good__subs", label="子条目",
                            recycle=False, export=True, export_order=43,
                            fk={"item_id": "item"})
'''

GOOD_MIGRATION = """
CREATE TABLE IF NOT EXISTS fixture_good__items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixture_good__subs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
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
    # 总验收插件:静态 fixture(第三方形态,manifest 不含 legacy_routes),
    # 拷入临时插件目录走与内置插件相同的 discover/load_all 路径
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "km_counter",
                    plugins_dir / "km_counter")
    # graph 地基插件(内置形态,同样无 legacy_routes):拷入临时目录验证加载/迁移/服务
    shutil.copytree(Path(__file__).resolve().parent.parent / "plugins" / "graph",
                    plugins_dir / "graph")
    # G4a chapter 插件(内置形态)及其依赖链:chapter → project → json_transfer
    for dep_pid in ("json_transfer", "project", "chapter"):
        shutil.copytree(Path(__file__).resolve().parent.parent / "plugins" / dep_pid,
                        plugins_dir / dep_pid)

    # 模拟老库升级:先建全量内核表(init_db 幂等),预置两卷四章(空章/长文/软删章),
    # 正文存 drafts 当前版本(chapters 表本无 content 列),再由 chapter 002 迁移迁入 graph_nodes
    database.init_db()
    conn = get_conn()
    seed_pid = conn.execute("INSERT INTO projects (title) VALUES ('G4a 种子')").lastrowid
    seed_v1 = conn.execute(
        "INSERT INTO volumes (project_id, title, sort_order) VALUES (?, '卷一', 1)", (seed_pid,)).lastrowid
    seed_v2 = conn.execute(
        "INSERT INTO volumes (project_id, title, sort_order) VALUES (?, '卷二', 2)", (seed_pid,)).lastrowid
    seed_long_text = "长文段落\n" * 3000
    conn.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (?, ?, '第一章', 1)",
                 (seed_v1, seed_pid))
    conn.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (?, ?, '空章', 2)",
                 (seed_v1, seed_pid))
    conn.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (?, ?, '长文章', 1)",
                 (seed_v2, seed_pid))
    conn.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order, deleted_at) "
                 "VALUES (?, ?, '软删章', 2, datetime('now','localtime'))", (seed_v2, seed_pid))
    # 第一章留两个版本,当前为 v2(验证取 is_current 且版本号最大者)
    conn.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (1, '第一章旧版', 1, 0)")
    conn.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (1, '第一章正文v2', 2, 1)")
    conn.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (3, ?, 1, 1)",
                 (seed_long_text,))
    conn.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (4, '软删章正文', 1, 1)")
    conn.commit()
    conn.close()

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

    # --- 总验收插件 km_counter(tests/fixtures,第三方形态) ---
    km_reg = reg.get("km_counter", {})
    check("km_counter 加载成功", km_reg.get("status") == "loaded", str(km_reg))
    check("km_counter 路由已注册(带强制前缀)",
          any(r.rule == "/api/plugins/km_counter/notes" for r in app.routes),
          str([r.rule for r in app.routes]))

    conn = get_conn()
    km_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='km_counter__notes'"
    ).fetchone()
    km_mig = conn.execute(
        "SELECT version FROM plugin_migrations WHERE plugin_id='km_counter' AND version=1"
    ).fetchone()
    conn.close()
    check("km_counter 迁移已建表", km_table is not None)
    check("km_counter 迁移已记录", km_mig is not None)

    km_manifest = km_reg.get("manifest") or {}
    check("km_counter manifest web 字段被 registry 返回",
          km_manifest.get("web") == ["web/km-counter.js"],
          str(km_reg.get("manifest")))

    # manifest 未设 legacy_routes:非前缀路由必须被拒(前缀强制生效)
    prefix_error = None
    if km_manifest:
        km_api = PluginAPI("km_counter", km_manifest, app)
        try:
            km_api.route("/api/km_counter/illegal")(lambda: None)
        except ValueError as e:
            prefix_error = str(e)
    check("未设 legacy_routes 时路由前缀强制生效",
          prefix_error is not None and "/api/plugins/km_counter/" in prefix_error,
          str(prefix_error))

    # --- graph 地基插件(内置形态拷入,无 legacy_routes) ---
    graph_reg = reg.get("graph", {})
    check("graph 插件加载成功", graph_reg.get("status") == "loaded", str(graph_reg))
    graph_routes = {r.rule for r in app.routes if r.rule.startswith("/api/plugins/graph/")}
    check("graph 路由带强制前缀注册",
          graph_routes == {
              "/api/plugins/graph/nodes",
              "/api/plugins/graph/nodes/<int:id>",
              "/api/plugins/graph/nodes/reorder",
          }, str(graph_routes))

    conn = get_conn()
    graph_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes'"
    ).fetchone()
    graph_mig = conn.execute(
        "SELECT version FROM plugin_migrations WHERE plugin_id='graph' AND version=1"
    ).fetchone()
    conn.close()
    check("graph 迁移已建表", graph_table is not None)
    check("graph 迁移已记录", graph_mig is not None)

    # 以 consumer 身份(插件运行时消费方式)require graph 服务,走类型注册 + 节点全链路
    graph_svc = consumer.require("graph")
    check("graph 服务可 require", graph_svc is not None)
    if graph_svc:
        graph_svc["register_node_type"]("km_block",
                                        {"label": "计数块", "plugin_id": "km_counter"})
        types = graph_svc["list_node_types"]()
        check("fixture 注册节点类型成功",
              any(t["type"] == "km_block" and t["label"] == "计数块"
                  and t["plugin_id"] == "km_counter" for t in types), str(types))
        check("get_node_type 可取回",
              (graph_svc["get_node_type"]("km_block") or {}).get("label") == "计数块")

        dup_type_err = None
        try:
            graph_svc["register_node_type"]("km_block", {"label": "重复"})
        except ValueError as e:
            dup_type_err = str(e)
        check("重复注册节点类型抛错",
              dup_type_err is not None and "重复注册" in dup_type_err, str(dup_type_err))

        reject_err = None
        try:
            graph_svc["create_node"]({"project_id": 777, "type": "ghost"})
        except ValueError as e:
            reject_err = str(e)
        check("create_node 拒绝未注册类型",
              reject_err is not None and "未注册" in reject_err, str(reject_err))

        # 全链路:创建(含层级)→ list_children → update → reorder → 级联软删
        n1 = graph_svc["create_node"]({"project_id": 777, "type": "km_block",
                                       "payload": {"text": "一"}})
        n2 = graph_svc["create_node"]({"project_id": 777, "type": "km_block",
                                       "payload": {"text": "二"}})
        n1c = graph_svc["create_node"]({"project_id": 777, "type": "km_block",
                                        "parent_id": n1["id"], "payload": {"text": "一子"}})
        check("创建节点成功(payload 解析为对象、自动排到同级末尾)",
              n1["sort_order"] == 1 and n2["sort_order"] == 2
              and n1["payload"] == {"text": "一"}, str((n1, n2)))
        check("list_children 根级按 sort_order 返回",
              [n["id"] for n in graph_svc["list_children"](777)] == [n1["id"], n2["id"]],
              str(graph_svc["list_children"](777)))
        check("list_children 子级按 parent_id 返回",
              [n["id"] for n in graph_svc["list_children"](777, n1["id"])] == [n1c["id"]],
              str(graph_svc["list_children"](777, n1["id"])))

        updated = graph_svc["update_node"](n1["id"], {"payload": {"text": "一改"}})
        check("update_node 改 payload 生效",
              updated["payload"] == {"text": "一改"}, str(updated))

        graph_svc["reorder"](777, None, [n2["id"], n1["id"]])
        check("reorder 重排同级顺序生效",
              [n["id"] for n in graph_svc["list_children"](777)] == [n2["id"], n1["id"]],
              str(graph_svc["list_children"](777)))

        deleted = graph_svc["soft_delete_node"](n1["id"])
        check("软删节点级联后代", deleted == 2, f"deleted={deleted}")
        check("软删后 get_node 不可见", graph_svc["get_node"](n1["id"]) is None)
        check("软删后 list_children 不含已删节点",
              [n["id"] for n in graph_svc["list_children"](777)] == [n2["id"]]
              and graph_svc["list_children"](777, n1["id"]) == [],
              str(graph_svc["list_children"](777)))

    # graph 同样未设 legacy_routes:非前缀路由必须被拒
    graph_prefix_error = None
    graph_manifest = graph_reg.get("manifest") or {}
    if graph_manifest:
        graph_api = PluginAPI("graph", graph_manifest, app)
        try:
            graph_api.route("/api/graph/illegal")(lambda: None)
        except ValueError as e:
            graph_prefix_error = str(e)
    check("graph 未设 legacy_routes 时路由前缀强制生效",
          graph_prefix_error is not None and "/api/plugins/graph/" in graph_prefix_error,
          str(graph_prefix_error))

    # --- G4a:chapter 插件正文 text 节点化 ---
    chapter_reg = reg.get("chapter", {})
    check("chapter 插件加载成功", chapter_reg.get("status") == "loaded", str(chapter_reg))

    conn = get_conn()
    chapter_mig2 = conn.execute(
        "SELECT version FROM plugin_migrations WHERE plugin_id='chapter' AND version=2"
    ).fetchone()
    text_nodes = [dict(r) for r in conn.execute(
        "SELECT * FROM graph_nodes WHERE type = 'text' ORDER BY id").fetchall()]
    conn.close()
    check("chapter 002 迁移已记录", chapter_mig2 is not None)

    text_meta = graph_svc["get_node_type"]("text") if graph_svc else None
    check("chapter 注册 text 节点类型(label 正文,归属 chapter)",
          text_meta is not None and text_meta["label"] == "正文"
          and text_meta["plugin_id"] == "chapter", str(text_meta))

    by_chapter = {}
    for n in text_nodes:
        p = json.loads(n["payload"] or "{}")
        by_chapter[p.get("chapter_id")] = (n, p)
    check("迁移只迁正文非空章节(空章无节点),软删章也迁",
          sorted(by_chapter.keys()) == [1, 3, 4], str(sorted(by_chapter.keys())))
    n1 = by_chapter.get(1)
    check("第一章节点取当前版本正文(异构父 parent_id=章节 id)",
          n1 is not None and n1[1] == {"chapter_id": 1, "content": "第一章正文v2"}
          and n1[0]["parent_id"] == 1 and n1[0]["project_id"] == seed_pid,
          str(n1))
    n3 = by_chapter.get(3)
    check("长文章节点内容逐字节一致",
          n3 is not None and n3[1]["content"] == seed_long_text,
          str(n3 and len(n3[1]["content"])))
    n4 = by_chapter.get(4)
    check("软删章节点携带 deleted_at",
          n4 is not None and n4[1]["content"] == "软删章正文"
          and n4[0]["deleted_at"] is not None, str(n4))

    # 002 SQL 手动重放:NOT EXISTS 判重保证行数不变(迁移自身幂等)
    mig2_sql = (Path(__file__).resolve().parent.parent
                / "plugins" / "chapter" / "migrations" / "002_content_nodes.sql"
                ).read_text(encoding="utf-8")
    conn = get_conn()
    before_replay = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_nodes WHERE type = 'text'").fetchone()["c"]
    for stmt in mig2_sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    after_replay = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_nodes WHERE type = 'text'").fetchone()["c"]
    conn.close()
    check("002 迁移 SQL 重放幂等(行数不变)",
          before_replay == after_replay, f"{before_replay}->{after_replay}")

    # 读写回环:直接调 chapter 插件模块函数与路由处理函数(不经 HTTP)
    chapter_mod = sys.modules.get("nw_plugin_chapter")
    check("chapter 模块已进入 sys.modules", chapter_mod is not None)
    if chapter_mod and graph_svc:
        new_ch = chapter_mod.create_chapter(
            {"volume_id": seed_v1, "project_id": seed_pid, "title": "新建章"})
        new_node_id = chapter_mod._find_text_node_id(new_ch["id"])
        new_node = graph_svc["get_node"](new_node_id) if new_node_id else None
        check("新建章节自动创建空 text 节点(parent_id=章节 id,sort_order 一致)",
              new_node is not None and new_node["parent_id"] == new_ch["id"]
              and new_node["payload"] == {"chapter_id": new_ch["id"], "content": ""}
              and new_node["sort_order"] == new_ch["sort_order"], str(new_node))

        chapter_keys = {"id", "volume_id", "project_id", "title", "sort_order", "status",
                        "word_count", "created_at", "updated_at", "deleted_at"}
        got = chapter_mod.get_chapter(1)
        listed = chapter_mod.list_chapters(seed_v1)
        check("get_chapter/list_chapters 返回形状不变(无 content 字段)",
              got is not None and set(got.keys()) == chapter_keys
              and all(set(c.keys()) == chapter_keys for c in listed),
              str(got and sorted(got.keys())))

        del_func = next((r.func for r in app.routes
                         if r.rule == "/api/chapters/<int:id>" and "DELETE" in r.methods), None)
        check("chapter 删除路由已注册", del_func is not None)
        if del_func:
            del_func(new_ch["id"])
            check("删除章节后章节软删(get 不可见)",
                  chapter_mod.get_chapter(new_ch["id"]) is None)
            check("删除章节级联软删 text 节点",
                  graph_svc["get_node"](new_node_id) is None
                  and chapter_mod._find_text_node_id(new_ch["id"]) is None)

    # 供下方迁移重跑段对比:text 节点总行数(含软删)
    conn = get_conn()
    text_total_pre_rerun = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_nodes WHERE type = 'text'").fetchone()["c"]
    conn.close()


    # --- 实体注册表 ---
    entities = consumer.list_entities()
    fixture_entity = next((e for e in entities
                           if e["plugin_id"] == "fixture_good" and e["entity"] == "item"), None)
    check("fixture 注册的实体可 list_entities 查到", fixture_entity is not None, str(entities))
    check("实体注册信息字段完整", fixture_entity == {
        "plugin_id": "fixture_good", "entity": "item",
        "table": "fixture_good__items", "label": "条目",
        "name_column": "title", "export": True, "export_order": 42,
        "fk": {"project_id": "project"}, "weak_fk": {},
        "recycle": True, "export_hook": None, "import_hook": None,
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
    # (recycle=False 的附属表实体不进回收站)
    entity_tables = {e["entity"]: (e["table"], e["name_column"])
                     for e in consumer.list_entities() if e.get("recycle", True)}
    check("recycle 式消费可见 fixture 实体",
          entity_tables.get("item") == ("fixture_good__items", "title"), str(entity_tables))
    check("recycle=False 的附属表实体不进回收站消费",
          "sub" not in entity_tables, str(entity_tables))

    # km_counter 的实体:recycle=True,回收站式消费应能看到
    km_entity = next((e for e in entities
                      if e["plugin_id"] == "km_counter" and e["entity"] == "km_note"), None)
    check("km_counter 注册的实体可 list_entities 查到", km_entity is not None, str(entities))
    check("km_counter 实体注册信息字段完整", km_entity == {
        "plugin_id": "km_counter", "entity": "km_note",
        "table": "km_counter__notes", "label": "计数笔记",
        "name_column": "name", "export": True, "export_order": 90,
        "fk": {"project_id": "project"}, "weak_fk": {},
        "recycle": True, "export_hook": None, "import_hook": None,
    }, str(km_entity))
    check("recycle 式消费可见 km_counter 实体(recycle=True)",
          entity_tables.get("km_note") == ("km_counter__notes", "name"), str(entity_tables))

    # --- json_transfer 默认处理器:带 fk 声明的实体随注册表参与导出/导入 ---
    database.init_db()  # 补全 projects 等业务表(导出载荷还引用 acts/floating_songs 等全局 schema 表)
    jt_spec = importlib.util.spec_from_file_location(
        "json_transfer_backend",
        Path(__file__).resolve().parent.parent / "plugins" / "json_transfer" / "backend.py")
    jt = importlib.util.module_from_spec(jt_spec)
    jt_spec.loader.exec_module(jt)
    jt._api = consumer  # 直接注入 PluginAPI,不走路由注册(consumer manifest 无 legacy_routes)

    conn = get_conn()
    pid = conn.execute("INSERT INTO projects (title) VALUES ('回环源')").lastrowid
    item_jia = conn.execute(
        "INSERT INTO fixture_good__items (project_id, name) VALUES (?, '甲')", (pid,)).lastrowid
    conn.execute("INSERT INTO fixture_good__items (project_id, name) VALUES (?, '乙')", (pid,))
    conn.execute("INSERT INTO fixture_good__subs (item_id, name) VALUES (?, '子甲1')", (item_jia,))
    conn.execute("INSERT INTO fixture_good__subs (item_id, name) VALUES (?, '子甲2')", (item_jia,))
    conn.execute("INSERT INTO fixture_good__subs (item_id, name) VALUES (999, '子悬空')")  # 悬空:导出级联剔除
    # km_counter 实体行:随注册表参与导出/导入回环
    conn.execute("INSERT INTO km_counter__notes (project_id, name, content) VALUES (?, '笔记一', '内容一')", (pid,))
    conn.execute("INSERT INTO km_counter__notes (project_id, name, content) VALUES (?, '笔记二', '内容二')", (pid,))
    conn.commit()
    payload = jt._build_export_payload(conn, pid)
    conn.close()

    items = payload.get("fixture_good__items")
    check("默认导出处理器包含带 fk 声明的 fixture 实体表",
          isinstance(items, list) and len(items) == 2, str(list(payload.keys())))
    check("导出行带原 project_id",
          bool(items) and all(r["project_id"] == pid for r in items), str(items))
    subs = payload.get("fixture_good__subs")
    check("附属表按 fk 挂靠导出(悬空行被级联剔除)",
          isinstance(subs, list) and sorted(r["name"] for r in subs) == ["子甲1", "子甲2"],
          str(subs))
    km_notes = payload.get("km_counter__notes")
    check("默认导出处理器包含 km_counter 实体表",
          isinstance(km_notes, list) and sorted(r["name"] for r in km_notes) == ["笔记一", "笔记二"],
          str(list(payload.keys())))

    new_proj = jt.import_project_json(payload)
    check("导入创建副本项目", new_proj["id"] != pid and new_proj["title"] == "回环源（副本）",
          str(new_proj))
    conn = get_conn()
    new_items = [dict(r) for r in conn.execute(
        "SELECT * FROM fixture_good__items WHERE project_id = ?", (new_proj["id"],)).fetchall()]
    new_subs = [dict(r) for r in conn.execute(
        "SELECT s.* FROM fixture_good__subs s JOIN fixture_good__items i ON s.item_id = i.id "
        "WHERE i.project_id = ?", (new_proj["id"],)).fetchall()]
    new_km_notes = [dict(r) for r in conn.execute(
        "SELECT * FROM km_counter__notes WHERE project_id = ?", (new_proj["id"],)).fetchall()]
    conn.close()
    old_item_ids = {r["id"] for r in items} if items else set()
    check("导入后 fixture 行 id 全部重映射",
          len(new_items) == 2 and old_item_ids.isdisjoint(r["id"] for r in new_items),
          str(new_items))
    check("导入后 fk 指向新项目 id",
          all(r["project_id"] == new_proj["id"] for r in new_items), str(new_items))
    check("导入保留业务字段",
          sorted(r["name"] for r in new_items) == sorted(["甲", "乙"]), str(new_items))
    new_jia_id = next((r["id"] for r in new_items if r["name"] == "甲"), None)
    check("附属表导入后 fk 指向重映射后的新 id",
          len(new_subs) == 2 and all(r["item_id"] == new_jia_id for r in new_subs),
          str(new_subs))
    old_km_ids = {r["id"] for r in km_notes} if km_notes else set()
    check("km_counter 导入后行 id 全部重映射",
          len(new_km_notes) == 2 and old_km_ids.isdisjoint(r["id"] for r in new_km_notes),
          str(new_km_notes))
    check("km_counter 导入后 fk 指向重映射后的新项目 id",
          all(r["project_id"] == new_proj["id"] for r in new_km_notes), str(new_km_notes))
    check("km_counter 导入保留业务字段",
          sorted(r["name"] for r in new_km_notes) == ["笔记一", "笔记二"], str(new_km_notes))

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
    km_count = conn.execute(
        "SELECT COUNT(*) AS c FROM plugin_migrations WHERE plugin_id='km_counter'"
    ).fetchone()["c"]
    graph_count = conn.execute(
        "SELECT COUNT(*) AS c FROM plugin_migrations WHERE plugin_id='graph'"
    ).fetchone()["c"]
    chapter_count = conn.execute(
        "SELECT COUNT(*) AS c FROM plugin_migrations WHERE plugin_id='chapter'"
    ).fetchone()["c"]
    text_total_post_rerun = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_nodes WHERE type = 'text'").fetchone()["c"]
    conn.close()
    check("迁移幂等(重复加载不重复记录)", count == 1, f"count={count}")
    check("km_counter 迁移幂等", km_count == 1, f"count={km_count}")
    check("graph 迁移幂等", graph_count == 1, f"count={graph_count}")
    check("chapter 迁移幂等(001/002 各记录一次)", chapter_count == 2, f"count={chapter_count}")
    check("重跑加载后 text 节点数不变", text_total_post_rerun == text_total_pre_rerun,
          f"{text_total_pre_rerun}->{text_total_post_rerun}")

    # --- 前端扩展点桩测试(node,无头环境无法跑真实 DOM) ---
    node = shutil.which("node")
    stub = Path(__file__).resolve().parent / "web_stub_test.js"
    if node is None:
        print("[SKIP] 前端桩测试(未找到 node,跳过;装 node 后可直接 node tests/web_stub_test.js)")
    else:
        r = subprocess.run([node, str(stub)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(r.stdout, end="")
        check("前端桩测试(sidebar.tabs/toolbar.actions/事件订阅)",
              r.returncode == 0, (r.stderr or "").strip())

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
