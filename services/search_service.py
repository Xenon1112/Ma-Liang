from database import get_conn, row_to_dict

def _snippet(text, keyword, ctx=40):
    if not text: return ""
    idx = text.find(keyword)
    if idx == -1: return text[:100]
    start = max(0, idx - ctx)
    end = min(len(text), idx + len(keyword) + ctx)
    s = text[start:end]
    if start > 0: s = "..." + s
    if end < len(text): s = s + "..."
    return s

def full_text(project_id, keyword, types=None):
    if types is None:
        types = ["chapter", "outline", "character", "world_setting", "inspiration"]

    conn = get_conn()
    results = []
    kw = f"%{keyword}%"

    if "chapter" in types:
        rows = conn.execute("""
            SELECT c.id, c.title, v.title AS volume_title, d.content
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            LEFT JOIN drafts d ON d.chapter_id = c.id AND d.is_current = 1
            WHERE c.project_id = ? AND c.deleted_at IS NULL
            AND (c.title LIKE ? OR d.content LIKE ?)
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            results.append({"type": "chapter", "id": r["id"], "title": r["title"],
                           "subtitle": r["volume_title"], "snippet": _snippet(r["content"], keyword)})

    if "outline" in types:
        rows = conn.execute("""
            SELECT id, title, content FROM outlines
            WHERE project_id = ? AND deleted_at IS NULL AND (title LIKE ? OR content LIKE ?)
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            results.append({"type": "outline", "id": r["id"], "title": r["title"], "snippet": _snippet(r["content"], keyword)})

    if "character" in types:
        rows = conn.execute("""
            SELECT c.id, c.name AS title, GROUP_CONCAT(cf.content, ' ') AS all_content
            FROM characters c
            LEFT JOIN character_fields cf ON c.id = cf.character_id
            WHERE c.project_id = ? AND c.deleted_at IS NULL AND (c.name LIKE ? OR cf.content LIKE ?)
            GROUP BY c.id
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            results.append({"type": "character", "id": r["id"], "title": r["title"], "snippet": _snippet(r["all_content"], keyword)})

    if "world_setting" in types:
        rows = conn.execute("""
            SELECT id, title, content FROM world_settings
            WHERE project_id = ? AND deleted_at IS NULL AND (title LIKE ? OR content LIKE ?)
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            results.append({"type": "world_setting", "id": r["id"], "title": r["title"], "snippet": _snippet(r["content"], keyword)})

    if "inspiration" in types:
        rows = conn.execute("""
            SELECT id, title, content FROM inspirations
            WHERE project_id = ? AND deleted_at IS NULL AND (title LIKE ? OR content LIKE ?)
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            results.append({"type": "inspiration", "id": r["id"], "title": r["title"], "snippet": _snippet(r["content"], keyword)})

    conn.close()
    return results
