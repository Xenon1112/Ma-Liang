from database import get_conn, row_to_dict, next_sort_order, count_words

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
    conn = get_conn()
    row = conn.execute("SELECT * FROM script_config WHERE project_id = ?", (project_id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def set_script_config(project_id, script_type):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO script_config (project_id, script_type) VALUES (?, ?)",
        (project_id, script_type)
    )
    conn.commit()
    conn.close()

# ====== Acts ======

def list_acts(project_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM acts WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_act(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM acts WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_act(data):
    conn = get_conn()
    project_id = _get(data, "project_id")
    title = _get(data, "title")
    order = data.get("sort_order") or data.get("sortOrder") or next_sort_order(conn, "acts", "project_id", project_id)
    cur = conn.execute(
        "INSERT INTO acts (project_id, title, sort_order) VALUES (?, ?, ?)",
        (project_id, title, order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM acts WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_act(id, data):
    conn = get_conn()
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
    return row_to_dict(row)

def reorder_acts(project_id, ordered_ids):
    conn = get_conn()
    for i, aid in enumerate(ordered_ids):
        conn.execute("UPDATE acts SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, aid, project_id))
    conn.commit()
    conn.close()

# ====== Scenes ======

def list_scenes(act_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM scenes WHERE act_id = ? AND deleted_at IS NULL ORDER BY sort_order", (act_id,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_scene(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM scenes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if row:
        row = row_to_dict(row)
        chars = conn.execute(
            "SELECT c.id, c.name FROM characters c JOIN scene_characters sc ON c.id = sc.character_id WHERE sc.scene_id = ?", (id,)
        ).fetchall()
        row["characters"] = [row_to_dict(c) for c in chars]
    conn.close()
    return row

def create_scene(data):
    conn = get_conn()
    act_id = _get(data, "act_id")
    project_id = _get(data, "project_id")
    title = _get(data, "title")
    order = data.get("sort_order") or data.get("sortOrder") or next_sort_order(conn, "scenes", "act_id", act_id)
    cur = conn.execute(
        "INSERT INTO scenes (act_id, project_id, title, setting, sort_order) VALUES (?, ?, ?, ?, ?)",
        (act_id, project_id, title, _get(data, "setting") or data.get("setting", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM scenes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_scene(id, data):
    conn = get_conn()
    allowed = ["title", "setting", "status"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE scenes SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM scenes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def reorder_scenes(act_id, ordered_ids):
    conn = get_conn()
    for i, sid in enumerate(ordered_ids):
        conn.execute("UPDATE scenes SET sort_order = ? WHERE id = ? AND act_id = ?", (i + 1, sid, act_id))
    conn.commit()
    conn.close()

def set_scene_characters(scene_id, character_ids):
    conn = get_conn()
    conn.execute("DELETE FROM scene_characters WHERE scene_id = ?", (scene_id,))
    for cid in (character_ids or []):
        conn.execute("INSERT OR IGNORE INTO scene_characters (scene_id, character_id) VALUES (?, ?)", (scene_id, cid))
    conn.commit()
    conn.close()

# ====== Script Elements ======

CONTAINER_TYPES = ("song", "ensemble", "dual")

def _refresh_scene_word_count(conn, scene_id):
    """重算并写回某场字数：统计该场所有未删除元素（含嵌套子元素）的 content 与 song_title。
    只执行 UPDATE，由调用方随同事务一起 commit"""
    if not scene_id:
        return
    rows = conn.execute(
        "SELECT content, song_title FROM script_elements WHERE scene_id = ? AND deleted_at IS NULL",
        (scene_id,)).fetchall()
    total = sum(count_words(r["content"])[1] + count_words(r["song_title"])[1] for r in rows)
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
    """递归加载容器子元素（song/ensemble 可嵌套）"""
    rows = conn.execute(
        """SELECT * FROM script_elements
           WHERE parent_id = ? AND deleted_at IS NULL
           ORDER BY sort_order""", (parent_id,)
    ).fetchall()
    children = []
    for r in rows:
        child = _attach_characters(conn, row_to_dict(r))
        if child["element_type"] in CONTAINER_TYPES and depth < 4:
            child["children"] = _load_children(conn, child["id"], depth + 1)
        children.append(child)
    return children

def list_elements(scene_id):
    conn = get_conn()
    # 先取顶层元素
    rows = conn.execute(
        """SELECT * FROM script_elements
           WHERE scene_id = ? AND parent_id IS NULL AND deleted_at IS NULL
           ORDER BY sort_order""", (scene_id,)
    ).fetchall()
    result = []
    for r in rows:
        elem = _attach_characters(conn, row_to_dict(r))
        if elem["element_type"] in CONTAINER_TYPES:
            elem["children"] = _load_children(conn, elem["id"])
        result.append(elem)
    conn.close()
    return result

def get_element(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM script_elements WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if row:
        elem = _attach_characters(conn, row_to_dict(row))
    else:
        elem = None
    conn.close()
    return elem

def create_element(data):
    conn = get_conn()
    scene_id = _get(data, "scene_id")
    parent_id = _get(data, "parent_id")
    element_type = _get(data, "element_type")
    where_field = "scene_id"
    where_value = scene_id
    if parent_id:
        where_field = "parent_id"
        where_value = parent_id
    order = data.get("sort_order") or data.get("sortOrder") or next_sort_order(conn, "script_elements", where_field, where_value)

    character_ids = _get(data, "character_ids") or []
    character_id = _get(data, "character_id") or (character_ids[0] if character_ids else None)

    cur = conn.execute(
        """INSERT INTO script_elements
           (scene_id, parent_id, element_type, character_id, content, song_title, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (scene_id, parent_id, element_type,
         character_id, _get(data, "content") or data.get("content", ""),
         _get(data, "song_title") or data.get("song_title", ""), order)
    )
    if character_ids:
        _set_element_characters(conn, cur.lastrowid, character_ids)
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    row = conn.execute("SELECT * FROM script_elements WHERE id = ?", (cur.lastrowid,)).fetchone()
    elem = _attach_characters(conn, row_to_dict(row))
    conn.close()
    return elem

def update_element(id, data):
    conn = get_conn()
    allowed = ["element_type", "character_id", "content", "song_title"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    character_ids = _get(data, "character_ids")
    if character_ids is not None and "character_id" not in data:
        sets.append("character_id = ?"); vals.append(character_ids[0] if character_ids else None)
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE script_elements SET {', '.join(sets)} WHERE id = ?", vals)
    if character_ids is not None:
        _set_element_characters(conn, id, character_ids)
    row = conn.execute("SELECT scene_id FROM script_elements WHERE id = ?", (id,)).fetchone()
    if row:
        _refresh_scene_word_count(conn, row["scene_id"])
    conn.commit()
    row = conn.execute("SELECT * FROM script_elements WHERE id = ?", (id,)).fetchone()
    elem = _attach_characters(conn, row_to_dict(row))
    conn.close()
    return elem

def delete_element(id):
    conn = get_conn()
    row = conn.execute("SELECT scene_id FROM script_elements WHERE id = ?", (id,)).fetchone()
    scene_id = row["scene_id"] if row else None
    # 如果是 song 容器，级联删除子元素
    conn.execute("DELETE FROM script_elements WHERE parent_id = ?", (id,))
    conn.execute("DELETE FROM script_elements WHERE id = ?", (id,))
    _refresh_scene_word_count(conn, scene_id)
    conn.commit()
    conn.close()

def reorder_elements(scene_id, parent_id, ordered_ids):
    conn = get_conn()
    where = "parent_id" if parent_id else "scene_id"
    where_val = parent_id if parent_id else scene_id
    # 先把不在 parent 下的元素设为 NULL
    if parent_id is None:
        conn.execute("UPDATE script_elements SET parent_id = NULL WHERE scene_id = ? AND id IN ({})".format(
            ','.join('?' * len(ordered_ids))), [scene_id] + ordered_ids)
    for i, eid in enumerate(ordered_ids):
        conn.execute(
            f"UPDATE script_elements SET sort_order = ?, parent_id = ? WHERE id = ? AND {where} = ?",
            (i + 1, parent_id, eid, where_val)
        )
    conn.commit()
    conn.close()

def move_element(element_id, new_parent_id):
    """将元素移入/移出歌曲块"""
    conn = get_conn()
    row = conn.execute("SELECT scene_id FROM script_elements WHERE id = ?", (element_id,)).fetchone()
    old_scene_id = row["scene_id"] if row else None
    conn.execute("UPDATE script_elements SET parent_id = ? WHERE id = ?", (new_parent_id, element_id))
    # 正常只换父容器、场不变；若跨场挂到别场容器下，新旧两个场景都要刷新
    _refresh_scene_word_count(conn, old_scene_id)
    if new_parent_id:
        prow = conn.execute("SELECT scene_id FROM script_elements WHERE id = ?", (new_parent_id,)).fetchone()
        if prow and prow["scene_id"] != old_scene_id:
            _refresh_scene_word_count(conn, prow["scene_id"])
    conn.commit()
    conn.close()
