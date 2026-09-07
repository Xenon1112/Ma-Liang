"""全文搜索插件:只读聚合查询 + 路由注册(原 services/search_service.py 与 app.py Search 路由迁移而来)

只读跨表 SQL 直查(SQL 层不按插件隔离),无专属表,故无 migrations 目录。
注:core/database.py 的 tags/entity_tags 两张表与本插件无关,目前无任何代码读写
(inspiration 的"标签"是 inspirations.tags 文本列,不是 tags 表)。
"""

_api = None  # activate 时注入的 PluginAPI


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

    conn = _api.db()
    results = []
    kw = f"%{keyword}%"

    if "chapter" in types:
        # 章节正文已节点化(chapter 插件注册的 text 节点,payload.content;过 payload 条件按
        # chapter_id 关联,不信 parent_id 列);节点缺失时回退 drafts 当前版本兜底。
        # 取数口径:节点优先,COALESCE 保证与迁移前 drafts 直查结果一致
        rows = conn.execute("""
            SELECT c.id, c.title, v.title AS volume_title,
                   COALESCE(json_extract(t.payload, '$.content'), d.content) AS content
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            LEFT JOIN graph_nodes t ON t.type = 'text' AND t.deleted_at IS NULL
                AND json_extract(t.payload, '$.chapter_id') = c.id
            LEFT JOIN drafts d ON d.chapter_id = c.id AND d.is_current = 1
            WHERE c.project_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL
            AND (c.title LIKE ? OR COALESCE(json_extract(t.payload, '$.content'), d.content) LIKE ?)
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
        # 剧作元素已迁入 graph_nodes(见 script 插件):内容/歌名在 payload,
        # 无 scene_id 的非剧本节点 join 不上 scenes,自然排除
        rows = conn.execute("""
            SELECT json_extract(e.payload, '$.content') AS content,
                   json_extract(e.payload, '$.song_title') AS song_title,
                   s.id AS scene_id, s.title AS scene_title, a.title AS act_title
            FROM graph_nodes e
            JOIN scenes s ON s.id = json_extract(e.payload, '$.scene_id')
            JOIN acts a ON s.act_id = a.id
            WHERE s.project_id = ? AND e.deleted_at IS NULL AND s.deleted_at IS NULL AND a.deleted_at IS NULL
            AND (json_extract(e.payload, '$.content') LIKE ? OR json_extract(e.payload, '$.song_title') LIKE ?)
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


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # ====== Search API ======

        @api.route("/api/search", methods=["GET"])
        def api_search():
            return api.jsonify(full_text(
                api.request.args.get("projectId", type=int),
                api.request.args.get("keyword", ""),
                api.request.args.get("types", "").split(",") if api.request.args.get("types") else None,
            ))
