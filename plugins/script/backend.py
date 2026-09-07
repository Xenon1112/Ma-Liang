"""剧本插件:幕/场/剧作元素(卡片)数据访问 + 路由注册(原 services/script_service.py 与 app.py Script 路由迁移而来)

存储格局(G2a):
- acts/scenes/scene_characters/element_characters/script_config 仍是普通表(结构容器与关联表),
- script_elements(剧作元素)已迁入 graph_nodes:节点 type 即 element_type,内容字段在 payload;
  迁移保留原 id(见 migrations/001_init.sql),element_characters 等关联表无需重映射。
- script_elements 旧表保留不删,仅作回滚底牌,本插件不再读写。

graph_nodes 上剧本元素的「异构父」约定(重要):
- 顶层元素的 parent_id 列 = 场景 id(scenes 是表不是节点,不在 graph_nodes 里);
- 嵌套元素(歌曲内唱词/叠白内对白等)的 parent_id 列 = 父元素节点 id;
- 节点 id 与场景 id 分属两张表的自增序列,数值可能相撞,所以按场/按父元素取元素时
  必须同时过 payload 条件:payload.scene_id = 元素所属场(恒有),
  payload.parent_id = 元素父节点 id(顶层为 NULL)。本模块查询一律走 payload 条件。

payload 形状(scene_id/parent_id/character_id/content/song_title/score_file/version_number),
与旧 script_elements 列一一对应;对外 HTTP API 形状不变(G2b 前端改造前仍用旧 API),
元素 dict 按旧表列序组装,sort_order 按旧 REAL 列语义一律转 float。

元素 CRUD 直写 graph_nodes 而不走 graph 插件的节点操作,原因:
create_node 的同级排序按 parent_id 列分组,在异构父约定下会混入「父节点 id 与场景 id
数值相撞」的节点;且元素创建/删除是多语句事务(节点 + element_characters + 场字数),
需要同一连接。graph 插件对本插件的意义是节点类型注册表(activate 时登记六种类型)。
"""
import json

_api = None  # activate 时注入的 PluginAPI

# 剧作元素类型全集(注册进 graph 类型注册表;song/ensemble/dual 为可嵌套容器)
ELEMENT_TYPES = ("action", "dialogue", "lyric", "song", "ensemble", "dual")
CONTAINER_TYPES = ("song", "ensemble", "dual")

_NODE_TYPE_META = {
    "action": "动作",
    "dialogue": "对白",
    "lyric": "唱词",
    "song": "歌曲",
    "ensemble": "重唱",
    "dual": "叠白",
}


def _get(data, snake_key, camel_key=None):
    """从 data 中取值，先找 snake_case，再找 camelCase"""
    if snake_key in data:
        return data[snake_key]
    if camel_key and camel_key in data:
        return data[camel_key]
    # auto-generate camelCase from snake_case
    parts = snake_key.split('_')
    camel = parts[0] + ''.join(p.capitalize() for p in parts[1:])
    if camel in data:
        return data[camel]
    return None

# ====== Script Config ======

def get_script_config(project_id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM script_config WHERE project_id = ?", (project_id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def set_script_config(project_id, script_type):
    conn = _api.db()
    conn.execute(
        "INSERT OR REPLACE INTO script_config (project_id, script_type) VALUES (?, ?)",
        (project_id, script_type)
    )
    conn.commit()
    conn.close()

# ====== Acts ======

def list_acts(project_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM acts WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_act(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM acts WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_act(data):
    conn = _api.db()
    project_id = _get(data, "project_id")
    title = _get(data, "title")
    order = data.get("sort_order") or data.get("sortOrder") or _api.next_sort_order(conn, "acts", "project_id", project_id)
    cur = conn.execute(
        "INSERT INTO acts (project_id, title, sort_order) VALUES (?, ?, ?)",
        (project_id, title, order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM acts WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_act(id, data):
    conn = _api.db()
    allowed = ["title"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE acts SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM acts WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def reorder_acts(project_id, ordered_ids):
    conn = _api.db()
    for i, aid in enumerate(ordered_ids):
        conn.execute("UPDATE acts SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, aid, project_id))
    conn.commit()
    conn.close()

# ====== Scenes ======

def list_scenes(act_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM scenes WHERE act_id = ? AND deleted_at IS NULL ORDER BY sort_order", (act_id,)
    ).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_scene(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM scenes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if row:
        row = _api.row_to_dict(row)
        chars = conn.execute(
            "SELECT c.id, c.name FROM characters c JOIN scene_characters sc ON c.id = sc.character_id WHERE sc.scene_id = ?", (id,)
        ).fetchall()
        row["characters"] = [_api.row_to_dict(c) for c in chars]
    conn.close()
    return row

def create_scene(data):
    conn = _api.db()
    act_id = _get(data, "act_id")
    project_id = _get(data, "project_id")
    title = _get(data, "title")
    order = data.get("sort_order") or data.get("sortOrder") or _api.next_sort_order(conn, "scenes", "act_id", act_id)
    cur = conn.execute(
        "INSERT INTO scenes (act_id, project_id, title, setting, sort_order) VALUES (?, ?, ?, ?, ?)",
        (act_id, project_id, title, _get(data, "setting") or data.get("setting", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM scenes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_scene(id, data):
    conn = _api.db()
    allowed = ["title", "setting", "status", "act_id"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            if k == "act_id":
                # 传入 act_id 表示「移动到目标幕末尾」：校验目标幕存在且未软删，并排到该幕最后
                target = conn.execute("SELECT id FROM acts WHERE id = ? AND deleted_at IS NULL", (data[k],)).fetchone()
                if not target:
                    conn.close()
                    raise ValueError("目标幕不存在")
                sets.append("act_id = ?"); vals.append(data[k])
                sets.append("sort_order = ?"); vals.append(_api.next_sort_order(conn, "scenes", "act_id", data[k]))
            else:
                sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE scenes SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM scenes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def reorder_scenes(act_id, ordered_ids):
    conn = _api.db()
    for i, sid in enumerate(ordered_ids):
        conn.execute("UPDATE scenes SET sort_order = ? WHERE id = ? AND act_id = ?", (i + 1, sid, act_id))
    conn.commit()
    conn.close()

def set_scene_characters(scene_id, character_ids):
    conn = _api.db()
    conn.execute("DELETE FROM scene_characters WHERE scene_id = ?", (scene_id,))
    for cid in (character_ids or []):
        conn.execute("INSERT OR IGNORE INTO scene_characters (scene_id, character_id) VALUES (?, ?)", (scene_id, cid))
    conn.commit()
    conn.close()

# ====== Script Elements(graph_nodes 存储) ======

def _node_to_element(row):
    """graph_nodes 行转旧 script_elements 形状的 dict(列序与旧表一致,HTTP 形状不变)。
    sort_order 按旧 REAL 列语义转 float;payload 解析失败时内容字段退化为 None"""
    try:
        p = json.loads(row["payload"] or "{}")
    except ValueError:
        p = {}
    return {
        "id": row["id"],
        "scene_id": p.get("scene_id"),
        "parent_id": p.get("parent_id"),
        "element_type": row["type"],
        "character_id": p.get("character_id"),
        "content": p.get("content"),
        "song_title": p.get("song_title"),
        "sort_order": float(row["sort_order"] or 0),
        "version_number": p.get("version_number"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
        "score_file": p.get("score_file"),
    }


def _element_payload(scene_id, parent_id, character_id, content, song_title, score_file, version_number):
    return json.dumps({
        "scene_id": scene_id, "parent_id": parent_id, "character_id": character_id,
        "content": content, "song_title": song_title,
        "score_file": score_file, "version_number": version_number,
    }, ensure_ascii=False)


def _refresh_scene_word_count(conn, scene_id):
    """重算并写回某场字数：统计该场所有未删除元素（含嵌套子元素）的 content 与 song_title。
    只执行 UPDATE，由调用方随同事务一起 commit"""
    if not scene_id:
        return
    rows = conn.execute(
        """SELECT json_extract(payload, '$.content') AS content,
                  json_extract(payload, '$.song_title') AS song_title
           FROM graph_nodes
           WHERE json_extract(payload, '$.scene_id') = ? AND deleted_at IS NULL""",
        (scene_id,)).fetchall()
    total = sum(_api.count_words(r["content"])[1] + _api.count_words(r["song_title"])[1] for r in rows)
    conn.execute("UPDATE scenes SET word_count = ? WHERE id = ?", (total, scene_id))

def _attach_characters(conn, elem):
    """给元素附加合唱者列表（character_ids），character_id 保持兼容（取第一个）"""
    rows = conn.execute(
        "SELECT character_id FROM element_characters WHERE element_id = ? ORDER BY sort_order, id",
        (elem["id"],)
    ).fetchall()
    ids = [r["character_id"] for r in rows]
    if not ids and elem.get("character_id"):
        ids = [elem["character_id"]]
    elem["character_ids"] = ids
    return elem

def _set_element_characters(conn, element_id, character_ids):
    conn.execute("DELETE FROM element_characters WHERE element_id = ?", (element_id,))
    for i, cid in enumerate(character_ids or []):
        conn.execute(
            "INSERT OR IGNORE INTO element_characters (element_id, character_id, sort_order) VALUES (?, ?, ?)",
            (element_id, cid, i + 1)
        )

def _load_children(conn, parent_id, depth=0):
    """递归加载容器子元素（song/ensemble/dual 可嵌套）;按 payload.parent_id 取,见模块 docstring 的异构父约定"""
    rows = conn.execute(
        """SELECT * FROM graph_nodes
           WHERE json_extract(payload, '$.parent_id') = ? AND deleted_at IS NULL
           ORDER BY sort_order""", (parent_id,)
    ).fetchall()
    children = []
    for r in rows:
        child = _attach_characters(conn, _node_to_element(r))
        if child["element_type"] in CONTAINER_TYPES and depth < 4:
            child["children"] = _load_children(conn, child["id"], depth + 1)
        children.append(child)
    return children

def list_elements(scene_id):
    conn = _api.db()
    # 先取顶层元素(属于该场且无元素父)
    rows = conn.execute(
        """SELECT * FROM graph_nodes
           WHERE json_extract(payload, '$.scene_id') = ?
             AND json_extract(payload, '$.parent_id') IS NULL
             AND deleted_at IS NULL
           ORDER BY sort_order""", (scene_id,)
    ).fetchall()
    result = []
    for r in rows:
        elem = _attach_characters(conn, _node_to_element(r))
        if elem["element_type"] in CONTAINER_TYPES:
            elem["children"] = _load_children(conn, elem["id"])
        result.append(elem)
    conn.close()
    return result

def get_element(id):
    conn = _api.db()
    row = conn.execute(
        """SELECT * FROM graph_nodes WHERE id = ? AND deleted_at IS NULL
             AND json_extract(payload, '$.scene_id') IS NOT NULL""", (id,)).fetchone()
    if row:
        elem = _attach_characters(conn, _node_to_element(row))
    else:
        elem = None
    conn.close()
    return elem

def create_element(data):
    conn = _api.db()
    scene_id = _get(data, "scene_id")
    parent_id = _get(data, "parent_id")
    element_type = _get(data, "element_type")
    # 同级末尾排序:按 payload 的 scene_id/parent_id 分组(异构父约定,不能按 parent_id 列分组)
    if parent_id:
        row = conn.execute(
            """SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM graph_nodes
               WHERE json_extract(payload, '$.parent_id') = ? AND deleted_at IS NULL""",
            (parent_id,)).fetchone()
    else:
        row = conn.execute(
            """SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM graph_nodes
               WHERE json_extract(payload, '$.scene_id') = ?
                 AND json_extract(payload, '$.parent_id') IS NULL AND deleted_at IS NULL""",
            (scene_id,)).fetchone()
    order = data.get("sort_order") or data.get("sortOrder") or row["n"]

    character_ids = _get(data, "character_ids") or []
    character_id = _get(data, "character_id") or (character_ids[0] if character_ids else None)

    # graph_nodes.project_id 冗余自 scenes 表;场不存在时 NOT NULL 约束使插入失败(与旧外键报错等价)
    srow = conn.execute("SELECT project_id FROM scenes WHERE id = ?", (scene_id,)).fetchone()
    project_id = srow["project_id"] if srow else None
    cur = conn.execute(
        """INSERT INTO graph_nodes (project_id, type, parent_id, sort_order, payload)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, element_type, parent_id or scene_id, order,
         _element_payload(scene_id, parent_id, character_id,
                          _get(data, "content") or data.get("content", ""),
                          _get(data, "song_title") or data.get("song_title", ""),
                          None, 1))
    )
    if character_ids:
        _set_element_characters(conn, cur.lastrowid, character_ids)
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (cur.lastrowid,)).fetchone()
    elem = _attach_characters(conn, _node_to_element(row))
    conn.close()
    return elem

def update_element(id, data):
    conn = _api.db()
    sets, vals = [], []
    # element_type 是节点 type 列;其余内容字段走 payload
    if "element_type" in data:
        sets.append("type = ?"); vals.append(data["element_type"])
    payload_keys = [k for k in ("character_id", "content", "song_title") if k in data]
    character_ids = _get(data, "character_ids")
    if character_ids is not None and "character_id" not in data:
        payload_keys.append("character_id")
    if payload_keys:
        pairs = []
        for k in payload_keys:
            v = data[k] if k in data else (character_ids[0] if character_ids else None)
            pairs.append(f"'$.{k}'"); pairs.append("?")
            vals.append(v)
        sets.append(f"payload = json_set(payload, {', '.join(pairs)})")
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE graph_nodes SET {', '.join(sets)} WHERE id = ?", vals)
    if character_ids is not None:
        _set_element_characters(conn, id, character_ids)
    row = conn.execute(
        "SELECT json_extract(payload, '$.scene_id') AS scene_id FROM graph_nodes WHERE id = ?", (id,)).fetchone()
    if row:
        _refresh_scene_word_count(conn, row["scene_id"])
    conn.commit()
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (id,)).fetchone()
    elem = _attach_characters(conn, _node_to_element(row))
    conn.close()
    return elem

def _element_descendant_ids(conn, id):
    """元素节点的全部后代 id(按 payload.parent_id 逐层下钻,避开 parent_id 列的异构父歧义)"""
    ids = []
    frontier = [id]
    while frontier:
        rows = conn.execute(
            "SELECT id, json_extract(payload, '$.parent_id') AS pid FROM graph_nodes "
            f"WHERE json_extract(payload, '$.parent_id') IN ({','.join('?' * len(frontier))})",
            frontier).fetchall()
        frontier = [r["id"] for r in rows]
        ids.extend(frontier)
    return ids

def delete_element(id):
    """物理删除元素及其全部后代(与旧行为一致:元素不进回收站),连带清理乐谱文件与合唱者关联"""
    conn = _api.db()
    row = conn.execute(
        """SELECT json_extract(payload, '$.scene_id') AS scene_id,
                  json_extract(payload, '$.score_file') AS score_file, project_id
           FROM graph_nodes WHERE id = ?""", (id,)).fetchone()
    scene_id = row["scene_id"] if row else None
    # 歌曲删除时一并清理挂载的乐谱文件(乐谱文件服务由 score 插件 provide)
    if row and row["score_file"]:
        score_svc = _api.require("score")
        if score_svc:
            score_svc["discard_score_file"](row["project_id"], row["score_file"])
    ids = [id] + _element_descendant_ids(conn, id)
    placeholders = ",".join("?" * len(ids))
    # 旧表靠外键级联清 element_characters,graph_nodes 不是其外键目标,手动清
    conn.execute(f"DELETE FROM element_characters WHERE element_id IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM graph_nodes WHERE id IN ({placeholders})", ids)
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    conn.close()

def reorder_elements(scene_id, parent_id, ordered_ids):
    conn = _api.db()
    for i, eid in enumerate(ordered_ids):
        if parent_id is None:
            # 顶层重排:列 parent_id 置为场景 id(异构父),payload.parent_id 置 null;
            # 旧逻辑作用域为「该场内的元素」,保持同一过滤
            conn.execute(
                """UPDATE graph_nodes SET sort_order = ?, parent_id = ?,
                       payload = json_set(payload, '$.parent_id', NULL)
                   WHERE id = ? AND json_extract(payload, '$.scene_id') = ?""",
                (i + 1, scene_id, eid, scene_id))
        else:
            # 容器内重排:与旧逻辑一致,只动当前已在该父下的元素(不能借 reorder 跨父移动)
            conn.execute(
                """UPDATE graph_nodes SET sort_order = ?
                   WHERE id = ? AND json_extract(payload, '$.parent_id') = ?""",
                (i + 1, eid, parent_id))
    conn.commit()
    conn.close()

def move_element(element_id, new_parent_id):
    """将元素移入/移出歌曲块"""
    conn = _api.db()
    row = conn.execute(
        "SELECT json_extract(payload, '$.scene_id') AS scene_id FROM graph_nodes WHERE id = ?",
        (element_id,)).fetchone()
    old_scene_id = row["scene_id"] if row else None
    if new_parent_id:
        conn.execute(
            """UPDATE graph_nodes SET parent_id = ?, payload = json_set(payload, '$.parent_id', ?)
               WHERE id = ?""", (new_parent_id, new_parent_id, element_id))
    else:
        # 移回顶层:列 parent_id 回到场景 id(异构父),payload.parent_id 置 null
        conn.execute(
            """UPDATE graph_nodes SET parent_id = ?, payload = json_set(payload, '$.parent_id', NULL)
               WHERE id = ?""", (old_scene_id, element_id))
    # 正常只换父容器、场不变;若跨场挂到别场容器下,新旧两个场景都要刷新
    _refresh_scene_word_count(conn, old_scene_id)
    if new_parent_id:
        prow = conn.execute(
            "SELECT json_extract(payload, '$.scene_id') AS scene_id FROM graph_nodes WHERE id = ?",
            (new_parent_id,)).fetchone()
        if prow and prow["scene_id"] != old_scene_id:
            _refresh_scene_word_count(conn, prow["scene_id"])
    conn.commit()
    conn.close()


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # 登记剧作元素节点类型(类型注册表由 graph 插件提供;依赖在 manifest 声明,先加载)
        graph = api.require("graph")
        if graph is None:
            raise RuntimeError("graph 插件未加载,无法注册剧本节点类型")
        for t in ELEMENT_TYPES:
            graph["register_node_type"](t, {
                "label": _NODE_TYPE_META[t],
                "payload_schema": {
                    "scene_id": "int 所属场(异构父,scenes 是表不是节点)",
                    "parent_id": "int|null 父元素节点 id(嵌套时)",
                    "character_id": "int|null 主角色(合唱者见 element_characters 表)",
                    "content": "str", "song_title": "str",
                    "score_file": "str|null 乐谱文件名", "version_number": "int",
                },
            })

        # 幕/场进回收站(原 recycle 插件 LEGACY_ENTITY_TABLES 过渡映射转正);
        # 不进 JSON 声明式导出(acts/scenes 仍走 json_transfer 的定制段,见该插件 docstring)
        api.register_entity(entity="act", table="acts", label="幕")
        api.register_entity(entity="scene", table="scenes", label="场")

        # ====== Script: Act API ======

        @api.route("/api/acts", methods=["GET"])
        def api_list_acts():
            return api.jsonify(list_acts(api.request.args.get("projectId", type=int)))

        @api.route("/api/acts/<int:id>", methods=["GET"])
        def api_get_act(id):
            a = get_act(id)
            return api.jsonify(a) if a else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/acts", methods=["POST"])
        def api_create_act():
            return api.jsonify(create_act(api.snake_json())), 201

        @api.route("/api/acts/<int:id>", methods=["PUT"])
        def api_update_act(id):
            return api.jsonify(update_act(id, api.snake_json()))

        @api.route("/api/acts/<int:id>", methods=["DELETE"])
        def api_delete_act(id):
            conn = _api.db()
            _api.soft_delete(conn, "acts", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/acts/reorder", methods=["POST"])
        def api_reorder_acts():
            data = api.req_json()
            reorder_acts(data["projectId"], data["orderedIds"])
            return api.jsonify({"ok": True})

        # ====== Script: Scene API ======

        @api.route("/api/scenes", methods=["GET"])
        def api_list_scenes():
            return api.jsonify(list_scenes(api.request.args.get("actId", type=int)))

        @api.route("/api/scenes/<int:id>", methods=["GET"])
        def api_get_scene(id):
            s = get_scene(id)
            return api.jsonify(s) if s else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/scenes", methods=["POST"])
        def api_create_scene():
            return api.jsonify(create_scene(api.snake_json())), 201

        @api.route("/api/scenes/<int:id>", methods=["PUT"])
        def api_update_scene(id):
            return api.jsonify(update_scene(id, api.snake_json()))

        @api.route("/api/scenes/<int:id>", methods=["DELETE"])
        def api_delete_scene(id):
            conn = _api.db()
            _api.soft_delete(conn, "scenes", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/scenes/reorder", methods=["POST"])
        def api_reorder_scenes():
            data = api.req_json()
            reorder_scenes(data["actId"], data["orderedIds"])
            return api.jsonify({"ok": True})

        @api.route("/api/scenes/<int:id>/characters", methods=["PUT"])
        def api_set_scene_characters(id):
            set_scene_characters(id, api.req_json().get("characterIds", []))
            return api.jsonify({"ok": True})

        # ====== Script: Element API ======

        @api.route("/api/elements", methods=["GET"])
        def api_list_elements():
            return api.jsonify(list_elements(api.request.args.get("sceneId", type=int)))

        @api.route("/api/elements/<int:id>", methods=["GET"])
        def api_get_element(id):
            e = get_element(id)
            return api.jsonify(e) if e else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/elements", methods=["POST"])
        def api_create_element():
            return api.jsonify(create_element(api.snake_json())), 201

        @api.route("/api/elements/<int:id>", methods=["PUT"])
        def api_update_element(id):
            return api.jsonify(update_element(id, api.snake_json()))

        @api.route("/api/elements/<int:id>", methods=["DELETE"])
        def api_delete_element(id):
            delete_element(id)
            return api.jsonify({"ok": True})

        @api.route("/api/elements/reorder", methods=["POST"])
        def api_reorder_elements():
            data = api.req_json()
            reorder_elements(data["sceneId"], data.get("parentId"), data["orderedIds"])
            return api.jsonify({"ok": True})

        @api.route("/api/elements/<int:id>/move", methods=["POST"])
        def api_move_element(id):
            data = api.req_json()
            move_element(id, data.get("parentId"))
            return api.jsonify({"ok": True})
