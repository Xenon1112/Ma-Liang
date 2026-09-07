"""graph 插件:统一块级线性节点模型地基

内容层的公共地基:project 下挂一片「块级节点」森林,层级与顺序用
parent_id + sort_order 表达(已确认不做分支边)。节点内容全部放进
payload(JSON 文本),形状由节点类型决定;类型须先由消费方插件经
register_node_type 注册进进程内类型注册表,create_node 才接受。

本期只立地基,不迁移任何现有内容,也不调用 api.register_entity:
graph_nodes 是通用容器,回收站/JSON 导出的实体语义是「节点类型」级而非
表级——一行数据是否进回收站、如何导出,取决于它的 type。G2(script 接入
节点)时需要设计「按节点类型的回收站/导出」方案(可能扩展实体注册表支持
虚拟实体),这是已知设计债,届时连同 payload_schema 校验一起补。
"""
import inspect
import json
import logging

log = logging.getLogger("graph")

_api = None  # activate 时注入的 PluginAPI

# 节点类型注册表(进程内存):type -> {"type", "label", "plugin_id", "payload_schema"}
# 消费方插件经 api.require("graph") 取得注册函数后登记;不持久化,随进程生命周期
_node_types = {}


# ====== 节点类型注册表 ======

def _caller_plugin_id():
    """从调用栈推断注册方插件 id(插件模块由 plugin_manager 以 nw_plugin_<id> 名加载)"""
    for frame in inspect.stack()[2:]:
        mod = frame.frame.f_globals.get("__name__", "")
        if mod.startswith("nw_plugin_"):
            return mod[len("nw_plugin_"):]
    return None


def register_node_type(type, meta):
    """注册节点类型。meta 含 label(必填)、可选 payload_schema(本期只存不校验);
    plugin_id 优先取 meta 自带,否则从调用栈自动推断。重复注册抛 ValueError"""
    if type in _node_types:
        raise ValueError(f"节点类型重复注册: {type}")
    if not meta or not meta.get("label"):
        raise ValueError(f"节点类型 {type} 注册缺少 label")
    _node_types[type] = {
        "type": type,
        "label": meta["label"],
        "plugin_id": meta.get("plugin_id") or _caller_plugin_id(),
        "payload_schema": meta.get("payload_schema"),
    }


def list_node_types():
    """全部已注册节点类型的 meta 列表"""
    return list(_node_types.values())


def get_node_type(type):
    """查单个节点类型的 meta,未注册返回 None"""
    return _node_types.get(type)


# ====== 节点操作(直接操作 graph_nodes 表,供其他插件 require 后调用) ======

def _row_to_node(row):
    """行转 dict,并把 payload 文本解析为 JSON 对象;解析失败原样保留文本"""
    d = _api.row_to_dict(row)
    if d is not None:
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except ValueError:
            pass
    return d


def _next_order(conn, project_id, parent_id):
    """同级末尾的下一个 sort_order(1 起)"""
    if parent_id is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM graph_nodes "
            "WHERE project_id = ? AND parent_id IS NULL AND deleted_at IS NULL",
            (project_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM graph_nodes "
            "WHERE project_id = ? AND parent_id = ? AND deleted_at IS NULL",
            (project_id, parent_id)).fetchone()
    return row["n"]


def create_node(data):
    """创建节点。data: project_id/type 必填,parent_id/payload/sort_order 可选。
    type 必须是已注册节点类型,未注册抛 ValueError;未给 sort_order 排到同级末尾"""
    if data.get("type") not in _node_types:
        raise ValueError(f"未注册的节点类型: {data.get('type')}")
    payload = data.get("payload") or {}
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)
    conn = _api.db()
    order = data.get("sort_order") or _next_order(conn, data["project_id"], data.get("parent_id"))
    cur = conn.execute(
        "INSERT INTO graph_nodes (project_id, type, parent_id, sort_order, payload) VALUES (?, ?, ?, ?, ?)",
        (data["project_id"], data["type"], data.get("parent_id"), order, payload))
    conn.commit()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _row_to_node(row)


def get_node(id):
    """取单个未删节点,不存在返回 None"""
    conn = _api.db()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _row_to_node(row)


def update_node(id, data):
    """改节点内容。本期只允许改 payload;节点不存在或已删返回 None"""
    conn = _api.db()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if row is None:
        conn.close()
        return None
    if "payload" in data:
        payload = data["payload"]
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        conn.execute(
            "UPDATE graph_nodes SET payload = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (payload, id))
        conn.commit()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _row_to_node(row)


def list_children(project_id, parent_id=None, type=None):
    """列出 project 下某父节点的未删子节点(parent_id=None 为根级),
    可按 type 过滤,按 sort_order 排序"""
    conn = _api.db()
    sql = "SELECT * FROM graph_nodes WHERE project_id = ? AND deleted_at IS NULL"
    params = [project_id]
    if parent_id is None:
        sql += " AND parent_id IS NULL"
    else:
        sql += " AND parent_id = ?"
        params.append(parent_id)
    if type:
        sql += " AND type = ?"
        params.append(type)
    sql += " ORDER BY sort_order"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_node(r) for r in rows]


def reorder(project_id, parent_id, ordered_ids):
    """按 ordered_ids 重排同级顺序(1 起);只动本 project 的行"""
    conn = _api.db()
    for i, nid in enumerate(ordered_ids):
        conn.execute(
            "UPDATE graph_nodes SET sort_order = ? WHERE id = ? AND project_id = ?",
            (i + 1, nid, project_id))
    conn.commit()
    conn.close()


def soft_delete_node(id):
    """软删节点及其全部后代(子孙一并软删,避免孤儿悬空);返回软删行数

    注意:parent_id 是异构父约定(可能是章节/场景等外部表 id,与节点 id 同数值空间),
    遍历必须按 visited 集合去重,否则「节点 id 恰等于其 parent_id」会自成环导致死循环。
    """
    conn = _api.db()
    ids = [id]
    visited = {id}
    i = 0
    while i < len(ids):
        rows = conn.execute(
            "SELECT id FROM graph_nodes WHERE parent_id = ? AND deleted_at IS NULL",
            (ids[i],)).fetchall()
        for r in rows:
            if r["id"] not in visited:
                visited.add(r["id"])
                ids.append(r["id"])
        i += 1
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE graph_nodes SET deleted_at = datetime('now','localtime') "
        f"WHERE id IN ({placeholders}) AND deleted_at IS NULL", ids)
    conn.commit()
    conn.close()
    return cur.rowcount


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # 注意:本期不调用 api.register_entity(实体语义在节点类型级而非表级),
        # 理由与后续设计债见模块 docstring

        # 对外提供类型注册表与节点操作;消费方按协议在请求处理时 require,勿缓存
        api.provide("graph", {
            "register_node_type": register_node_type,
            "list_node_types": list_node_types,
            "get_node_type": get_node_type,
            "create_node": create_node,
            "get_node": get_node,
            "update_node": update_node,
            "list_children": list_children,
            "reorder": reorder,
            "soft_delete_node": soft_delete_node,
        })

        @api.route("/api/plugins/graph/nodes", methods=["GET"])
        def api_list_nodes():
            project_id = api.request.args.get("projectId", type=int)
            if not project_id:
                return api.jsonify({"error": "缺少 projectId"}), 400
            # parentId 缺省或 root/null 按根级处理;否则取该父节点的子级
            parent_raw = api.request.args.get("parentId")
            if parent_raw is None or parent_raw in ("", "root", "null"):
                parent_id = None
            else:
                parent_id = int(parent_raw)
            return api.jsonify(list_children(project_id, parent_id, api.request.args.get("type")))

        @api.route("/api/plugins/graph/nodes", methods=["POST"])
        def api_create_node():
            try:
                return api.jsonify(create_node(api.snake_json())), 201
            except ValueError as e:
                return api.jsonify({"error": str(e)}), 400

        @api.route("/api/plugins/graph/nodes/<int:id>", methods=["PUT"])
        def api_update_node(id):
            node = update_node(id, api.snake_json())
            return api.jsonify(node) if node else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/plugins/graph/nodes/reorder", methods=["POST"])
        def api_reorder_nodes():
            data = api.req_json()
            reorder(data["projectId"], data.get("parentId"), data["orderedIds"])
            return api.jsonify({"ok": True})

        @api.route("/api/plugins/graph/nodes/<int:id>", methods=["DELETE"])
        def api_delete_node(id):
            if get_node(id) is None:
                return api.jsonify({"error": "not found"}), 404
            n = soft_delete_node(id)
            return api.jsonify({"ok": True, "deleted": n})
