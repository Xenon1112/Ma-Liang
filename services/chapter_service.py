from database import get_conn, row_to_dict, next_sort_order

# ====== Volumes ======

def list_volumes(project_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM volumes WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_volume(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM volumes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_volume(data):
    conn = get_conn()
    order = data.get("sort_order", next_sort_order(conn, "volumes", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO volumes (project_id, title, preface, sort_order) VALUES (?, ?, ?, ?)",
        (data["project_id"], data["title"], data.get("preface", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM volumes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_volume(id, data):
    conn = get_conn()
    allowed = ["title", "preface"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE volumes SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM volumes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def reorder_volumes(project_id, ordered_ids):
    conn = get_conn()
    for i, vid in enumerate(ordered_ids):
        conn.execute("UPDATE volumes SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, vid, project_id))
    conn.commit()
    conn.close()

# ====== Chapters ======

def list_chapters(volume_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chapters WHERE volume_id = ? AND deleted_at IS NULL ORDER BY sort_order", (volume_id,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_chapter(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM chapters WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_chapter(data):
    conn = get_conn()
    order = data.get("sort_order", next_sort_order(conn, "chapters", "volume_id", data["volume_id"]))
    cur = conn.execute(
        "INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (?, ?, ?, ?)",
        (data["volume_id"], data["project_id"], data["title"], order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_chapter(id, data):
    conn = get_conn()
    allowed = ["title", "status", "word_count"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE chapters SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def reorder_chapters(volume_id, ordered_ids):
    conn = get_conn()
    for i, cid in enumerate(ordered_ids):
        conn.execute("UPDATE chapters SET sort_order = ? WHERE id = ? AND volume_id = ?", (i + 1, cid, volume_id))
    conn.commit()
    conn.close()
