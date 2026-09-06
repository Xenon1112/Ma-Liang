from core.database import get_conn, row_to_dict, next_sort_order

def list_settings(project_id, category=None):
    conn = get_conn()
    sql = "SELECT * FROM world_settings WHERE project_id = ? AND deleted_at IS NULL"
    params = [project_id]
    if category:
        sql += " AND category = ?"; params.append(category)
    sql += " ORDER BY category, sort_order"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_setting(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM world_settings WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_setting(data):
    conn = get_conn()
    order = data.get("sort_order", next_sort_order(conn, "world_settings", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO world_settings (project_id, category, title, content, sort_order) VALUES (?, ?, ?, ?, ?)",
        (data["project_id"], data["category"], data["title"], data.get("content", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM world_settings WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_setting(id, data):
    conn = get_conn()
    allowed = ["category", "title", "content"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE world_settings SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM world_settings WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)
