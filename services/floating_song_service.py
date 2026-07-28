import json

from database import get_conn, row_to_dict, next_sort_order

# ====== 游离歌曲（音乐剧：不挂场、不进正文，仅出现在 JSON 导出） ======

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

def list_floating_songs(project_id):
    """歌曲 + 嵌套唱词（character_ids 已解析为数组）"""
    conn = get_conn()
    songs = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM floating_songs WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order",
        (project_id,)).fetchall()]
    for s in songs:
        s["lyrics"] = [_lyric_to_dict(r) for r in conn.execute(
            "SELECT * FROM floating_lyrics WHERE song_id = ? ORDER BY sort_order", (s["id"],)).fetchall()]
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
    conn.execute("DELETE FROM floating_songs WHERE id = ?", (id,))
    conn.commit()
    conn.close()

# ====== 唱词 ======

def add_lyric(data):
    conn = get_conn()
    song_id = data["song_id"]
    order = next_sort_order(conn, "floating_lyrics", "song_id", song_id)
    character_ids = [int(i) for i in (data.get("character_ids") or [])]
    cur = conn.execute(
        "INSERT INTO floating_lyrics (song_id, character_id, character_ids, content, sort_order) VALUES (?, ?, ?, ?, ?)",
        (song_id, character_ids[0] if character_ids else None,
         json.dumps(character_ids, ensure_ascii=False), data.get("content", ""), order))
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
    conn = get_conn()
    conn.execute("DELETE FROM floating_lyrics WHERE id = ?", (id,))
    conn.commit()
    conn.close()

# ====== 与正文歌曲互转 ======

def move_to_scene(floating_song_id, scene_id):
    """游离歌曲 → 正文歌曲：在目标场建 song 容器 + lyric 子元素，然后删除游离歌曲"""
    from services.script_service import create_element
    conn = get_conn()
    song = conn.execute(
        "SELECT * FROM floating_songs WHERE id = ? AND deleted_at IS NULL", (floating_song_id,)).fetchone()
    if not song:
        conn.close()
        raise ValueError("游离歌曲不存在")
    lyrics = conn.execute(
        "SELECT * FROM floating_lyrics WHERE song_id = ? ORDER BY sort_order", (floating_song_id,)).fetchall()
    conn.close()

    new_song = create_element({
        "scene_id": scene_id, "element_type": "song", "song_title": song["song_title"],
    })
    for l in lyrics:
        create_element({
            "scene_id": scene_id, "parent_id": new_song["id"], "element_type": "lyric",
            "content": l["content"], "character_ids": _parse_ids(l["character_ids"]),
        })
    delete_floating_song(floating_song_id)
    return new_song

def move_to_floating(element_id):
    """正文歌曲 → 游离歌曲：仅接受子元素全为唱词的歌曲（含对白/重唱则拒绝，避免结构丢失）"""
    conn = get_conn()
    song = conn.execute(
        "SELECT * FROM script_elements WHERE id = ? AND deleted_at IS NULL", (element_id,)).fetchone()
    if not song or song["element_type"] != "song":
        conn.close()
        raise ValueError("目标不是歌曲卡片")
    children = conn.execute(
        "SELECT * FROM script_elements WHERE parent_id = ? AND deleted_at IS NULL ORDER BY sort_order",
        (element_id,)).fetchall()
    if any(ch["element_type"] != "lyric" for ch in children):
        conn.close()
        raise ValueError("歌曲含对白或重唱，不能转为游离歌曲")
    child_ids = [ch["id"] for ch in children]
    singers = {}
    for cid in child_ids:
        rows = conn.execute(
            "SELECT character_id FROM element_characters WHERE element_id = ? ORDER BY sort_order, id",
            (cid,)).fetchall()
        ids = [r["character_id"] for r in rows]
        singers[cid] = ids
    conn.close()

    new_song = create_floating_song({
        "project_id": _project_of_element(element_id),
        "song_title": song["song_title"] or "未命名歌曲",
    })
    for ch in children:
        ids = singers[ch["id"]] or ([ch["character_id"]] if ch["character_id"] else [])
        add_lyric({"song_id": new_song["id"], "content": ch["content"], "character_ids": ids})

    # 删除原歌曲（子元素随 delete_element 删除）
    from services.script_service import delete_element
    delete_element(element_id)
    return new_song

def _project_of_element(element_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT s.project_id AS pid FROM script_elements e JOIN scenes s ON e.scene_id = s.id WHERE e.id = ?",
        (element_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("元素不存在")
    return row["pid"]
