from core.database import get_conn, row_to_dict

def list_inspirations(project_id, type=None, tag=None):
    conn = get_conn()
    sql = "SELECT * FROM inspirations WHERE project_id = ? AND deleted_at IS NULL"
    params = [project_id]
    if type:
        sql += " AND type = ?"; params.append(type)
    if tag:
        sql += " AND tags LIKE ?"; params.append(f"%{tag}%")
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_inspiration(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM inspirations WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_inspiration(data):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO inspirations (project_id, type, title, content, source, tags, linked_chapter_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["project_id"], data.get("type", "inspiration"), data["title"], data.get("content", ""),
         data.get("source", ""), data.get("tags", ""), data.get("linked_chapter_id"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM inspirations WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_inspiration(id, data):
    conn = get_conn()
    allowed = ["type", "title", "content", "source", "tags", "linked_chapter_id"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE inspirations SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM inspirations WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)
