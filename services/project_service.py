from database import get_conn, row_to_dict

def list_projects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_project(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def create_project(data):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO projects (title, subtitle, author, description) VALUES (?, ?, ?, ?)",
        (data["title"], data.get("subtitle", ""), data.get("author", ""), data.get("description", ""))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_project(id, data):
    conn = get_conn()
    allowed = ["title", "subtitle", "author", "description", "status"]
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
            (SELECT COALESCE(SUM(word_count), 0) FROM chapters WHERE project_id = ? AND deleted_at IS NULL) AS total_words,
            (SELECT COUNT(*) FROM volumes WHERE project_id = ? AND deleted_at IS NULL) AS volume_count,
            (SELECT COUNT(*) FROM chapters WHERE project_id = ? AND deleted_at IS NULL) AS chapter_count,
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
