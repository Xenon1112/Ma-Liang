import json

from core.database import get_conn, row_to_dict, next_sort_order, count_words

# ====== 游离歌曲（音乐剧：不挂场、不进正文，仅出现在 JSON 导出） ======
#
# G2a 注:正文剧作元素已迁入 graph_nodes(script 插件,旧 script_elements 表保留不读写)。
# 本服务尚未插件化,与正文歌曲互转时直接 SQL 读写 graph_nodes(payload 里
# scene_id/parent_id/character_id/content/song_title/score_file;异构父约定见 script 插件
# docstring),G3 插件化时清理为插件间调用。

def _parse_ids(raw):
    try:
        ids = json.loads(raw or "[]")
        return [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()] if isinstance(ids, list) else []
    except (ValueError, TypeError):
        return []

def _lyric_to_dict(row):
    d = row_to_dict(row)
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
    conn = get_conn()
    songs = [row_to_dict(r) for r in conn.execute(
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
    conn = get_conn()
    order = next_sort_order(conn, "floating_songs", "project_id", data["project_id"])
    cur = conn.execute(
        "INSERT INTO floating_songs (project_id, song_title, sort_order) VALUES (?, ?, ?)",
        (data["project_id"], data.get("song_title") or "未命名歌曲", order))
    conn.commit()
    row = conn.execute("SELECT * FROM floating_songs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_floating_song(id, data):
    conn = get_conn()
    if "song_title" in data:
        conn.execute(
            "UPDATE floating_songs SET song_title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (data["song_title"], id))
        conn.commit()
    row = conn.execute("SELECT * FROM floating_songs WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def delete_floating_song(id):
    # 物理删除（与剧本元素一致）；唱词由 FK 级联删除
    conn = get_conn()
    row = conn.execute("SELECT project_id, score_file FROM floating_songs WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM floating_songs WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    # 歌曲删除时一并清理挂载的乐谱文件
    if row and row["score_file"]:
        from services import score_service
        score_service.discard_score_file(row["project_id"], row["score_file"])

# ====== 唱词 ======

def add_lyric(data):
    conn = get_conn()
    song_id = data["song_id"]
    parent_id = data.get("parent_id")
    element_type = data.get("element_type") or "lyric"
    # ensemble 子行在容器内排序，顶层行在歌曲内排序
    if parent_id:
        order = next_sort_order(conn, "floating_lyrics", "parent_id", parent_id)
    else:
        order = next_sort_order(conn, "floating_lyrics", "song_id", song_id)
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
    conn = get_conn()
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
    conn = get_conn()
    conn.execute("DELETE FROM floating_lyrics WHERE id = ?", (id,))
    conn.commit()
    conn.close()

# ====== 与正文歌曲互转 ======
#
# 以下 _ 开头的 helper 直写 graph_nodes(G3 清理,见文件头注释)

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
    total = sum(count_words(r["content"])[1] + count_words(r["song_title"])[1] for r in rows)
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
    conn = get_conn()
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
    if song["score_file"]:
        from services import score_service
        score_service.transfer_score(song["project_id"], song["score_file"], element_id=new_song_id)
    delete_floating_song(floating_song_id)
    # 返回完整元素 dict(与旧 create_element 返回值同形状,前端在读)
    conn = get_conn()
    elem = _node_to_element_dict(conn, new_song_id)
    conn.close()
    return elem

def _element_singers(conn, element_id):
    """元素的演唱/说话角色列表：优先 element_characters，否则退回单 character_id"""
    rows = conn.execute(
        "SELECT character_id FROM element_characters WHERE element_id = ? ORDER BY sort_order, id",
        (element_id,)).fetchall()
    ids = [r["character_id"] for r in rows]
    if not ids:
        row = conn.execute("SELECT character_id FROM script_elements WHERE id = ?", (element_id,)).fetchone()
        if row and row["character_id"]:
            ids = [row["character_id"]]
    return ids

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
    conn = get_conn()
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
    if score_file:
        from services import score_service
        score_service.transfer_score(
            _project_of_element(element_id), score_file, floating_song_id=new_song["id"])

    # 删除原歌曲节点及其后代(等价 script 插件 delete_element:物理删,连带合唱者关联与场字数;
    # 乐谱已在上面改名移走,旧节点 payload 里的 score_file 指向已改名文件,无需再清理)
    conn = get_conn()
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
    conn = get_conn()
    row = conn.execute(
        """SELECT s.project_id AS pid FROM graph_nodes e
           JOIN scenes s ON s.id = json_extract(e.payload, '$.scene_id') WHERE e.id = ?""",
        (element_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("元素不存在")
    return row["pid"]
