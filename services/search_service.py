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
        types = ["chapter", "outline", "character", "world_setting", "inspiration", "scene", "floating_song"]

    conn = get_conn()
    results = []
    kw = f"%{keyword}%"

    if "chapter" in types:
        rows = conn.execute("""
            SELECT c.id, c.title, v.title AS volume_title, d.content
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            LEFT JOIN drafts d ON d.chapter_id = c.id AND d.is_current = 1
            WHERE c.project_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL
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

    if "scene" in types:
        # 场名/场景描述 + 该场未软删卡片（含嵌套子元素）的内容与歌名；同一场多条命中合并为一条
        scene_hits = {}
        rows = conn.execute("""
            SELECT s.id, s.title, s.setting, a.title AS act_title
            FROM scenes s JOIN acts a ON s.act_id = a.id
            WHERE s.project_id = ? AND s.deleted_at IS NULL AND a.deleted_at IS NULL
            AND (s.title LIKE ? OR s.setting LIKE ?)
            ORDER BY a.sort_order, s.sort_order
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            text = r["setting"] if r["setting"] and keyword in r["setting"] else r["title"]
            scene_hits[r["id"]] = {"type": "scene", "id": r["id"], "title": r["title"],
                                   "subtitle": r["act_title"], "snippet": _snippet(text, keyword)}
        rows = conn.execute("""
            SELECT e.content, e.song_title, s.id AS scene_id, s.title AS scene_title, a.title AS act_title
            FROM script_elements e
            JOIN scenes s ON e.scene_id = s.id
            JOIN acts a ON s.act_id = a.id
            WHERE s.project_id = ? AND e.deleted_at IS NULL AND s.deleted_at IS NULL AND a.deleted_at IS NULL
            AND (e.content LIKE ? OR e.song_title LIKE ?)
            ORDER BY a.sort_order, s.sort_order, e.sort_order, e.id
        """, (project_id, kw, kw)).fetchall()
        for r in rows:
            if r["scene_id"] in scene_hits:
                continue  # 同一场只保留首个命中
            text = r["content"] if r["content"] and keyword in r["content"] else r["song_title"]
            scene_hits[r["scene_id"]] = {"type": "scene", "id": r["scene_id"], "title": r["scene_title"],
                                         "subtitle": r["act_title"], "snippet": _snippet(text, keyword)}
        results.extend(scene_hits.values())

    if "floating_song" in types:
        # 游离歌曲：搜歌名与唱词；同一首歌多条命中合并为一条
        song_hits = {}
        rows = conn.execute("""
            SELECT id, song_title FROM floating_songs
            WHERE project_id = ? AND deleted_at IS NULL AND song_title LIKE ?
            ORDER BY sort_order
        """, (project_id, kw)).fetchall()
        for r in rows:
            song_hits[r["id"]] = {"type": "floating_song", "id": r["id"], "title": r["song_title"],
                                  "subtitle": "游离歌曲", "snippet": _snippet(r["song_title"], keyword)}
        rows = conn.execute("""
            SELECT l.content, s.id AS song_id, s.song_title
            FROM floating_lyrics l JOIN floating_songs s ON l.song_id = s.id
            WHERE s.project_id = ? AND s.deleted_at IS NULL AND l.content LIKE ?
            ORDER BY s.sort_order, l.sort_order, l.id
        """, (project_id, kw)).fetchall()
        for r in rows:
            if r["song_id"] in song_hits:
                continue  # 同一首歌只保留首个命中
            song_hits[r["song_id"]] = {"type": "floating_song", "id": r["song_id"], "title": r["song_title"],
                                       "subtitle": "游离歌曲", "snippet": _snippet(r["content"], keyword)}
        results.extend(song_hits.values())

    conn.close()
    return results
