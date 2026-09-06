from core.database import get_conn, row_to_dict, next_sort_order

def _build_tree(rows, parent_id=None):
    return [
        {**row_to_dict(r), "children": _build_tree(rows, r["id"])}
        for r in rows if r["parent_id"] == parent_id
    ]

def tree(project_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM outlines WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return _build_tree(rows)

def get_outline(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM outlines WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_outline(data):
    conn = get_conn()
    order = data.get("sort_order", next_sort_order(conn, "outlines", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO outlines (project_id, parent_id, title, content, sort_order, node_type, linked_chapter_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["project_id"], data.get("parent_id"), data["title"], data.get("content", ""), order,
         data.get("node_type", "chapter_outline"), data.get("linked_chapter_id"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM outlines WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def _is_in_subtree(conn, ancestor_id, node_id):
    """node_id 是否等于 ancestor_id 或位于其子树中（沿 parent 链向上查）"""
    pid = node_id
    while pid is not None:
        if pid == ancestor_id:
            return True
        row = conn.execute("SELECT parent_id FROM outlines WHERE id = ?", (pid,)).fetchone()
        pid = row["parent_id"] if row else None
    return False

def update_outline(id, data):
    conn = get_conn()
    # 移动父级时校验：新父节点须存在未删除，且不能是自身或自身后代（成环会导致子树从大纲树消失）
    new_parent = data.get("parent_id")
    if "parent_id" in data and new_parent is not None:
        prow = conn.execute("SELECT id FROM outlines WHERE id = ? AND deleted_at IS NULL", (new_parent,)).fetchone()
        if not prow:
            conn.close()
            raise ValueError("父节点不存在或已删除")
        if _is_in_subtree(conn, id, new_parent):
            conn.close()
            raise ValueError("不能将节点移动到其自身或子节点下")
    allowed = ["title", "content", "node_type", "linked_chapter_id", "parent_id"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE outlines SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM outlines WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def reorder_outlines(project_id, ordered_ids):
    conn = get_conn()
    for i, oid in enumerate(ordered_ids):
        conn.execute("UPDATE outlines SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, oid, project_id))
    conn.commit()
    conn.close()

def link_chapter(id, chapter_id):
    return update_outline(id, {"linked_chapter_id": chapter_id})
