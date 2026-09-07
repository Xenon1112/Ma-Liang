"""游离歌曲插件:音乐剧「不挂场、不进正文,仅出现在 JSON 导出」的歌曲(唱词/对白/重唱)

数据访问 + 路由注册(原 services/floating_song_service.py 与 app.py Floating Song 路由迁移而来)。

表:floating_songs/floating_lyrics(见 migrations/001_init.sql,schema 逐列抄自全局
MIGRATION_V4/V5/V6;floating_lyrics 无 deleted_at 列,删除一律物理删除)。

与正文歌曲(graph_nodes 里的 script 元素)互转保留内部 SQL,不走 graph 插件的节点操作,
原因与 script 插件相同(见该插件 docstring 的「异构父」约定):
graph 的 create_node 同级排序按 parent_id 列分组,会混入「父节点 id 与场景 id 数值相撞」
的节点;且互转是多语句事务(节点 + element_characters + 场字数 + 乐谱改名),需要同一连接。
manifest 仍声明依赖 graph,保证加载顺序在节点地基之后。

乐谱文件操作(discard_score_file/transfer_score/read_score_bytes/write_score_file)由
score 插件 provide(G3 并行迁移),消费方一律运行时 _score_svc() 经 api.require("score")
取用,缺失时按「无乐谱数据」降级(与 script/json_transfer 插件同例)。

JSON 导出/导入:嵌套 lyrics 结构与 character_ids JSON 拼接字段,默认处理器表达不了,
故经 register_entity 注册 export_hook/import_hook;json_transfer 在其定制段固定位置
显式调用(export=False 不进声明式主循环),保证导出文件键序逐字节不变。

删除语义:游离歌曲物理删除(唱词由 FK 级联),不进回收站——register_entity 用
recycle=False 保持这一现状语义。
"""
import base64
import json

_api = None  # activate 时注入的 PluginAPI


def _score_svc():
    """score 插件 provide 的乐谱文件服务;未加载返回 None,调用方按「无乐谱数据」降级"""
    return _api.require("score")


def _parse_ids(raw):
    try:
        ids = json.loads(raw or "[]")
        return [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()] if isinstance(ids, list) else []
    except (ValueError, TypeError):
        return []

def _lyric_to_dict(row):
    d = _api.row_to_dict(row)
    d["character_ids"] = _parse_ids(d.get("character_ids"))
    return d

def _load_lyric_children(conn, parent_id, depth=0):
    """递归加载 ensemble 容器的子行（参照剧本元素，限制嵌套深度）"""
    rows = conn.execute(
        "SELECT * FROM floating_lyrics WHERE parent_id = ? ORDER BY sort_order", (parent_id,)).fetchall()
    children = []
    for r in rows:
        child = _lyric_to_dict(r)
        if child.get("element_type") == "ensemble" and depth < 4:
            child["children"] = _load_lyric_children(conn, child["id"], depth + 1)
        children.append(child)
    return children

def list_floating_songs(project_id):
    """歌曲 + 嵌套元素树（顶层 lyrics 为 parent_id 为空的行，ensemble 行带 children）"""
    conn = _api.db()
    songs = [_api.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM floating_songs WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order",
        (project_id,)).fetchall()]
    for s in songs:
        top = conn.execute(
            "SELECT * FROM floating_lyrics WHERE song_id = ? AND parent_id IS NULL ORDER BY sort_order",
            (s["id"],)).fetchall()
        lyrics = []
        for r in top:
            d = _lyric_to_dict(r)
            if d.get("element_type") == "ensemble":
                d["children"] = _load_lyric_children(conn, d["id"])
            lyrics.append(d)
        s["lyrics"] = lyrics
    conn.close()
    return songs

def create_floating_song(data):
    conn = _api.db()
    order = _api.next_sort_order(conn, "floating_songs", "project_id", data["project_id"])
    cur = conn.execute(
        "INSERT INTO floating_songs (project_id, song_title, sort_order) VALUES (?, ?, ?)",
        (data["project_id"], data.get("song_title") or "未命名歌曲", order))
    conn.commit()
    row = conn.execute("SELECT * FROM floating_songs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_floating_song(id, data):
    conn = _api.db()
    if "song_title" in data:
        conn.execute(
            "UPDATE floating_songs SET song_title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (data["song_title"], id))
        conn.commit()
    row = conn.execute("SELECT * FROM floating_songs WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def delete_floating_song(id):
    # 物理删除（与剧本元素一致）；唱词由 FK 级联删除
    conn = _api.db()
    row = conn.execute("SELECT project_id, score_file FROM floating_songs WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM floating_songs WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    # 歌曲删除时一并清理挂载的乐谱文件(乐谱文件服务由 score 插件 provide)
    score_svc = _score_svc()
    if row and row["score_file"] and score_svc:
        score_svc["discard_score_file"](row["project_id"], row["score_file"])

# ====== 唱词 ======

def add_lyric(data):
    conn = _api.db()
    song_id = data["song_id"]
    parent_id = data.get("parent_id")
    element_type = data.get("element_type") or "lyric"
    # ensemble 子行在容器内排序，顶层行在歌曲内排序
    if parent_id:
        order = _api.next_sort_order(conn, "floating_lyrics", "parent_id", parent_id)
    else:
        order = _api.next_sort_order(conn, "floating_lyrics", "song_id", song_id)
    character_ids = [int(i) for i in (data.get("character_ids") or [])]
    # ensemble 是容器行，本身无内容
    content = "" if element_type == "ensemble" else data.get("content", "")
    cur = conn.execute(
        "INSERT INTO floating_lyrics (song_id, parent_id, element_type, character_id, character_ids, content, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (song_id, parent_id, element_type, character_ids[0] if character_ids else None,
         json.dumps(character_ids, ensure_ascii=False), content, order))
    conn.commit()
    row = conn.execute("SELECT * FROM floating_lyrics WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _lyric_to_dict(row)

def update_lyric(id, data):
    conn = _api.db()
    sets, vals = [], []
    if "content" in data:
        sets.append("content = ?"); vals.append(data["content"])
    if "character_ids" in data:
        ids = [int(i) for i in (data.get("character_ids") or [])]
        sets.append("character_ids = ?"); vals.append(json.dumps(ids, ensure_ascii=False))
        sets.append("character_id = ?"); vals.append(ids[0] if ids else None)
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE floating_lyrics SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM floating_lyrics WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _lyric_to_dict(row)

def delete_lyric(id):
    # ensemble 行的子行由 parent_id 外键级联删除（ON DELETE CASCADE）
    conn = _api.db()
    conn.execute("DELETE FROM floating_lyrics WHERE id = ?", (id,))
    conn.commit()
    conn.close()

# ====== 与正文歌曲互转 ======
#
# 以下 _ 开头的 helper 直写 graph_nodes(理由见模块 docstring;与 script 插件同口径)

def _refresh_scene_word_count(conn, scene_id):
    """重算场字数(与 script 插件同口径:该场未删元素的 content + song_title)"""
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


def _create_scene_element(conn, scene_id, project_id, parent_id, element_type,
                          content="", song_title="", character_ids=None):
    """在场里建一个元素节点(等价 script 插件 create_element;parent_id 为父元素节点 id,顶层传 None)"""
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
    character_ids = character_ids or []
    payload = json.dumps({
        "scene_id": scene_id, "parent_id": parent_id,
        "character_id": character_ids[0] if character_ids else None,
        "content": content, "song_title": song_title,
        "score_file": None, "version_number": 1,
    }, ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO graph_nodes (project_id, type, parent_id, sort_order, payload) VALUES (?, ?, ?, ?, ?)",
        (project_id, element_type, parent_id or scene_id, row["n"], payload))
    for i, cid in enumerate(character_ids):
        conn.execute(
            "INSERT OR IGNORE INTO element_characters (element_id, character_id, sort_order) VALUES (?, ?, ?)",
            (cur.lastrowid, cid, i + 1))
    return cur.lastrowid


def _node_payload(row):
    try:
        return json.loads(row["payload"] or "{}")
    except ValueError:
        return {}


def _node_to_element_dict(conn, node_id):
    """graph_nodes 节点转旧 script_elements 形状的 dict(与 script 插件 _node_to_element 同形状,
    保持 move-to-scene 的 HTTP 响应不变)"""
    row = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        return None
    p = _node_payload(row)
    elem = {
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
    rows = conn.execute(
        "SELECT character_id FROM element_characters WHERE element_id = ? ORDER BY sort_order, id",
        (node_id,)).fetchall()
    ids = [r["character_id"] for r in rows]
    if not ids and elem["character_id"]:
        ids = [elem["character_id"]]
    elem["character_ids"] = ids
    return elem


def move_to_scene(floating_song_id, scene_id):
    """游离歌曲 → 正文歌曲：在目标场建 song 容器，按元素类型重建
    lyric/dialogue 子元素与 ensemble 容器（含其子元素），然后删除游离歌曲"""
    conn = _api.db()
    song = conn.execute(
        "SELECT * FROM floating_songs WHERE id = ? AND deleted_at IS NULL", (floating_song_id,)).fetchone()
    if not song:
        conn.close()
        raise ValueError("游离歌曲不存在")
    top = conn.execute(
        "SELECT * FROM floating_lyrics WHERE song_id = ? AND parent_id IS NULL ORDER BY sort_order",
        (floating_song_id,)).fetchall()
    children_map = {}
    for l in top:
        if l["element_type"] == "ensemble":
            children_map[l["id"]] = conn.execute(
                "SELECT * FROM floating_lyrics WHERE parent_id = ? ORDER BY sort_order", (l["id"],)).fetchall()
    srow = conn.execute("SELECT project_id FROM scenes WHERE id = ?", (scene_id,)).fetchone()
    if not srow:
        conn.close()
        raise ValueError("场不存在")
    project_id = srow["project_id"]

    new_song_id = _create_scene_element(
        conn, scene_id, project_id, None, "song", song_title=song["song_title"])
    for l in top:
        ids = _parse_ids(l["character_ids"])
        if l["element_type"] == "ensemble":
            ens_id = _create_scene_element(conn, scene_id, project_id, new_song_id, "ensemble")
            for ch in children_map.get(l["id"], []):
                _create_scene_element(
                    conn, scene_id, project_id, ens_id,
                    ch["element_type"] if ch["element_type"] in ("lyric", "dialogue") else "lyric",
                    content=ch["content"], character_ids=_parse_ids(ch["character_ids"]))
        else:
            _create_scene_element(
                conn, scene_id, project_id, new_song_id,
                l["element_type"] if l["element_type"] in ("lyric", "dialogue") else "lyric",
                content=l["content"], character_ids=ids)
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    conn.close()

    # 乐谱随歌曲转移到正文（先改名挂在新的 song 元素上，再删游离歌曲，避免文件被清理）
    score_svc = _score_svc()
    if song["score_file"] and score_svc:
        score_svc["transfer_score"](song["project_id"], song["score_file"], element_id=new_song_id)
    delete_floating_song(floating_song_id)
    # 返回完整元素 dict(与旧 create_element 返回值同形状,前端在读)
    conn = _api.db()
    elem = _node_to_element_dict(conn, new_song_id)
    conn.close()
    return elem

def _element_singers(conn, element_id):
    """元素的演唱/说话角色列表：优先 element_characters，否则退回单 character_id(在节点 payload)"""
    rows = conn.execute(
        "SELECT character_id FROM element_characters WHERE element_id = ? ORDER BY sort_order, id",
        (element_id,)).fetchall()
    ids = [r["character_id"] for r in rows]
    if not ids:
        row = conn.execute(
            "SELECT json_extract(payload, '$.character_id') AS character_id FROM graph_nodes WHERE id = ?",
            (element_id,)).fetchone()
        if row and row["character_id"]:
            ids = [row["character_id"]]
    return ids

def _element_children(conn, parent_id):
    """某元素节点的未删子节点(按 payload.parent_id 取,异构父约定见 script 插件 docstring)"""
    return conn.execute(
        """SELECT * FROM graph_nodes WHERE json_extract(payload, '$.parent_id') = ?
           AND deleted_at IS NULL ORDER BY sort_order""", (parent_id,)).fetchall()

def move_to_floating(element_id):
    """正文歌曲 → 游离歌曲：完整转换 lyric/dialogue/ensemble（ensemble 容器连带其子元素）"""
    conn = _api.db()
    song_row = conn.execute(
        "SELECT * FROM graph_nodes WHERE id = ? AND deleted_at IS NULL", (element_id,)).fetchone()
    song_p = _node_payload(song_row) if song_row else {}
    if not song_row or song_row["type"] != "song":
        conn.close()
        raise ValueError("目标不是歌曲卡片")
    song_title = song_p.get("song_title")
    score_file = song_p.get("score_file")
    children = _element_children(conn, element_id)
    supported = ("lyric", "dialogue", "ensemble")
    if any(ch["type"] not in supported for ch in children):
        conn.close()
        raise ValueError("歌曲含暂不支持的元素类型，不能转为游离歌曲")
    # 收集顶层元素及 ensemble 子元素的演唱者与内容
    singers = {ch["id"]: _element_singers(conn, ch["id"]) for ch in children}
    contents = {ch["id"]: _node_payload(ch).get("content") for ch in children}
    ens_children = {}
    for ch in children:
        if ch["type"] == "ensemble":
            subs = _element_children(conn, ch["id"])
            ens_children[ch["id"]] = subs
            for sub in subs:
                singers[sub["id"]] = _element_singers(conn, sub["id"])
                contents[sub["id"]] = _node_payload(sub).get("content")
    scene_id = song_p.get("scene_id")
    conn.close()

    new_song = create_floating_song({
        "project_id": _project_of_element(element_id),
        "song_title": song_title or "未命名歌曲",
    })
    for ch in children:
        if ch["type"] == "ensemble":
            ens = add_lyric({"song_id": new_song["id"], "element_type": "ensemble"})
            for sub in ens_children.get(ch["id"], []):
                add_lyric({
                    "song_id": new_song["id"], "parent_id": ens["id"],
                    "element_type": sub["type"] if sub["type"] in ("lyric", "dialogue") else "lyric",
                    "content": contents[sub["id"]], "character_ids": singers[sub["id"]],
                })
        else:
            add_lyric({
                "song_id": new_song["id"], "element_type": ch["type"],
                "content": contents[ch["id"]], "character_ids": singers[ch["id"]],
            })

    # 乐谱随歌曲转移到游离歌曲（先改名挂到新行，再删原元素，避免文件被清理）
    score_svc = _score_svc()
    if score_file and score_svc:
        score_svc["transfer_score"](
            _project_of_element(element_id), score_file, floating_song_id=new_song["id"])

    # 删除原歌曲节点及其后代(等价 script 插件 delete_element:物理删,连带合唱者关联与场字数;
    # 乐谱已在上面改名移走,旧节点 payload 里的 score_file 指向已改名文件,无需再清理)
    conn = _api.db()
    ids = [element_id]
    frontier = [element_id]
    while frontier:
        rows = conn.execute(
            "SELECT id FROM graph_nodes WHERE json_extract(payload, '$.parent_id') IN "
            f"({','.join('?' * len(frontier))})", frontier).fetchall()
        frontier = [r["id"] for r in rows]
        ids.extend(frontier)
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM element_characters WHERE element_id IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM graph_nodes WHERE id IN ({placeholders})", ids)
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    conn.close()
    return new_song

def _project_of_element(element_id):
    conn = _api.db()
    row = conn.execute(
        """SELECT s.project_id AS pid FROM graph_nodes e
           JOIN scenes s ON s.id = json_extract(e.payload, '$.scene_id') WHERE e.id = ?""",
        (element_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("元素不存在")
    return row["pid"]

# ====== json_transfer 定制钩子(嵌套 lyrics + character_ids JSON 拼接,默认处理器表达不了) ======

def export_hook(conn, project_id, id_sets, include_deleted):
    """json_transfer export_hook 约定:(conn, project_id, id_sets, include_deleted) ->
    {payload键: 行数组}。产出的 song_dict/lyric dict 键序与原定制段逐字节一致。
    游离歌曲不被其他实体引用,无需写 id_sets"""
    char_ids = id_sets.get("character", set())
    nd = "" if include_deleted else " AND deleted_at IS NULL"
    floating = []
    fs_rows = [_api.row_to_dict(r) for r in conn.execute(
        f"SELECT * FROM floating_songs WHERE project_id = ?{nd} ORDER BY sort_order",
        (project_id,)).fetchall()]
    for s in fs_rows:
        lyrics = [_api.row_to_dict(r) for r in conn.execute(
            "SELECT id, parent_id, element_type, content, character_ids, sort_order FROM floating_lyrics WHERE song_id = ? ORDER BY sort_order, id",
            (s["id"],)).fetchall()]
        song_dict = {
            "song_title": s["song_title"],
            "sort_order": s["sort_order"],
            "lyrics": [{
                # 保留原行 id 供同歌内 parent_id 引用
                "id": l["id"],
                "parent_id": l["parent_id"],
                "element_type": l["element_type"] or "lyric",
                "content": l["content"],
                # 过滤指向已排除角色的悬空引用
                "character_ids": [i for i in _parse_ids(l["character_ids"]) if i in char_ids],
                "sort_order": l["sort_order"],
            } for l in lyrics],
        }
        # 乐谱文件 base64 内嵌；文件丢失(或 score 插件未加载)则不导出
        if s.get("score_file"):
            svc = _score_svc()
            data = svc["read_score_bytes"](project_id, s["score_file"]) if svc else None
            if data is not None:
                song_dict["score_b64"] = base64.b64encode(data).decode("ascii")
        floating.append(song_dict)
    return {"floating_songs": floating}


def import_hook(conn, payload, id_maps, new_project_id):
    """json_transfer import_hook 约定:(conn, payload, id_maps, new_project_id) ->
    {旧id: 新id}。游离歌曲不被下游实体引用,导出载荷也无歌曲级 id,返回空映射;
    老导出文件无 floating_songs 键时视为空"""
    hmap = id_maps.get("character", {})
    score_svc = _score_svc()
    rows = payload.get("floating_songs")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("导出文件格式不正确：floating_songs 应为数组")
    for s in rows:
        if not isinstance(s, dict):
            raise ValueError("导出文件格式不正确：floating_songs 存在非法行")
        cur = conn.execute(
            "INSERT INTO floating_songs (project_id, song_title, sort_order) VALUES (?, ?, ?)",
            (new_project_id, s.get("song_title") or "未命名歌曲", s.get("sort_order", 0)))
        # 乐谱：内嵌的 base64 写回文件并更新 score_file 列(score 插件未加载则跳过)
        if s.get("score_b64") and score_svc:
            filename = score_svc["write_score_file"](
                new_project_id, f"floating_{cur.lastrowid}.mscz",
                base64.b64decode(s["score_b64"]))
            conn.execute("UPDATE floating_songs SET score_file = ? WHERE id = ?",
                         (filename, cur.lastrowid))
        # 先插全部行（parent_id 暂置 NULL）并建立 旧id→新id 映射，再统一回写 parent_id
        lyric_map = {}
        pending_parent = []
        for l in (s.get("lyrics") or []):
            # 演唱者 id 重映射到新角色；悬空引用丢弃
            ids = [hmap[i] for i in (l.get("character_ids") or []) if i in hmap]
            lcur = conn.execute(
                "INSERT INTO floating_lyrics (song_id, element_type, character_id, character_ids, content, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (cur.lastrowid, l.get("element_type") or "lyric", ids[0] if ids else None,
                 json.dumps(ids, ensure_ascii=False), l.get("content", ""), l.get("sort_order", 0)))
            if l.get("id") is not None:
                lyric_map[l["id"]] = lcur.lastrowid
            if l.get("parent_id") is not None:
                pending_parent.append((lcur.lastrowid, l["parent_id"]))
        for new_id, old_parent in pending_parent:
            # 悬空 parent_id（父行未导出）置 NULL，退回顶层
            conn.execute("UPDATE floating_lyrics SET parent_id = ? WHERE id = ?",
                         (lyric_map.get(old_parent), new_id))
    return {}


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # 登记实体:export=False(不进声明式主循环,json_transfer 在定制段固定位置调 hook,
        # 保证导出文件字节不变);recycle=False(物理删除,不进回收站,保持现状语义)
        api.register_entity(entity="floating_song", table="floating_songs", label="游离歌曲",
                            name_column="song_title", export=False, recycle=False,
                            export_hook=export_hook, import_hook=import_hook)

        # ====== Floating Song API(legacy_routes,路径与原 app.py 一致) ======

        @api.route("/api/floating-songs", methods=["GET"])
        def api_list_floating_songs():
            return api.jsonify(list_floating_songs(api.request.args.get("projectId", type=int)))

        @api.route("/api/floating-songs", methods=["POST"])
        def api_create_floating_song():
            return api.jsonify(create_floating_song(api.snake_json())), 201

        @api.route("/api/floating-songs/<int:id>", methods=["PUT"])
        def api_update_floating_song(id):
            return api.jsonify(update_floating_song(id, api.snake_json()))

        @api.route("/api/floating-songs/<int:id>", methods=["DELETE"])
        def api_delete_floating_song(id):
            delete_floating_song(id)
            return api.jsonify({"ok": True})

        @api.route("/api/floating-songs/<int:id>/lyrics", methods=["POST"])
        def api_add_lyric(id):
            data = api.snake_json()
            data["song_id"] = id
            return api.jsonify(add_lyric(data)), 201

        @api.route("/api/floating-lyrics/<int:id>", methods=["PUT"])
        def api_update_lyric(id):
            return api.jsonify(update_lyric(id, api.snake_json()))

        @api.route("/api/floating-lyrics/<int:id>", methods=["DELETE"])
        def api_delete_lyric(id):
            delete_lyric(id)
            return api.jsonify({"ok": True})

        @api.route("/api/floating-songs/<int:id>/move-to-scene", methods=["POST"])
        def api_move_to_scene(id):
            return api.jsonify(move_to_scene(id, api.req_json().get("sceneId")))

        @api.route("/api/elements/<int:id>/move-to-floating", methods=["POST"])
        def api_move_to_floating(id):
            return api.jsonify(move_to_floating(id))
