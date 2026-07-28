from database import get_conn, row_to_dict

def list_projects():
    conn = get_conn()
    # 内联统计（章数/总字数，口径同 get_stats：章、卷均未软删），避免首页逐作品再发请求
    rows = conn.execute("""
        SELECT p.*,
            (SELECT COALESCE(SUM(c.word_count), 0) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = p.id AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS total_words,
            (SELECT COUNT(*) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = p.id AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS chapter_count
        FROM projects p WHERE p.deleted_at IS NULL ORDER BY p.updated_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = row_to_dict(r)
        d["totalWords"] = d.pop("total_words")
        d["chapterCount"] = d.pop("chapter_count")
        result.append(d)
    return result

def get_project_tree(project_id):
    """一次取回目录树：novel → 卷(含章节)；剧本 → 幕(含场)。替代前端 1+N 逐级请求"""
    conn = get_conn()
    proj = conn.execute("SELECT project_type FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return None
    ptype = proj["project_type"] or "novel"
    if ptype == "novel":
        parents = conn.execute(
            "SELECT * FROM volumes WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)).fetchall()
        children = conn.execute(
            """SELECT c.* FROM chapters c JOIN volumes v ON c.volume_id = v.id
               WHERE c.project_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL
               ORDER BY c.sort_order""", (project_id,)).fetchall()
        key, pid_field, child_key = "volumes", "volume_id", "chapters"
    else:
        parents = conn.execute(
            "SELECT * FROM acts WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)).fetchall()
        children = conn.execute(
            """SELECT s.* FROM scenes s JOIN acts a ON s.act_id = a.id
               WHERE s.project_id = ? AND s.deleted_at IS NULL AND a.deleted_at IS NULL
               ORDER BY s.sort_order""", (project_id,)).fetchall()
        key, pid_field, child_key = "acts", "act_id", "scenes"
    by_parent = {}
    for ch in children:
        by_parent.setdefault(ch[pid_field], []).append(row_to_dict(ch))
    result = []
    for p in parents:
        d = row_to_dict(p)
        d[child_key] = by_parent.get(p["id"], [])
        result.append(d)
    conn.close()
    return {"type": ptype, key: result}

def get_project(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_project(data):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO projects (title, subtitle, author, description, project_type) VALUES (?, ?, ?, ?, ?)",
        (data["title"], data.get("subtitle", ""), data.get("author", ""),
         data.get("description", ""), data.get("project_type", "novel"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_project(id, data):
    conn = get_conn()
    allowed = ["title", "subtitle", "author", "description", "status", "project_type"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def delete_project(id):
    from database import soft_delete
    conn = get_conn()
    soft_delete(conn, "projects", id)
    conn.close()

def get_stats(project_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT
            (SELECT COALESCE(SUM(c.word_count), 0) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS total_words,
            (SELECT COUNT(*) FROM volumes WHERE project_id = ? AND deleted_at IS NULL) AS volume_count,
            (SELECT COUNT(*) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS chapter_count,
            (SELECT COUNT(*) FROM characters WHERE project_id = ? AND deleted_at IS NULL) AS character_count,
            (SELECT COUNT(*) FROM drafts WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = ?)) AS draft_count
    """, (project_id, project_id, project_id, project_id, project_id)).fetchone()
    conn.close()
    return {
        "totalWords": row["total_words"],
        "volumeCount": row["volume_count"],
        "chapterCount": row["chapter_count"],
        "characterCount": row["character_count"],
        "draftCount": row["draft_count"],
    }
