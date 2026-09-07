"""项目管理插件:数据访问 + 路由注册(原 services/project_service.py 迁移而来)

整项目 JSON 导入依赖 json_transfer 插件 provide 的 import_project_json,
运行时通过 api.require("json_transfer") 获取,避免插件间直接 import。
"""

_api = None  # activate 时注入的 PluginAPI


def list_projects():
    conn = _api.db()
    # 内联统计（一次取回两套口径，Python 侧按 project_type 组装），避免首页逐作品再发请求
    # 小说：章数/总字数（章、卷均未软删）；剧本：幕数/场数/场字数和（幕、场均未软删）
    rows = conn.execute("""
        SELECT p.*,
            (SELECT COALESCE(SUM(c.word_count), 0) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = p.id AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS novel_words,
            (SELECT COUNT(*) FROM chapters c JOIN volumes v ON c.volume_id = v.id
             WHERE c.project_id = p.id AND c.deleted_at IS NULL AND v.deleted_at IS NULL) AS chapter_count,
            (SELECT COUNT(*) FROM acts a
             WHERE a.project_id = p.id AND a.deleted_at IS NULL) AS act_count,
            (SELECT COUNT(*) FROM scenes s JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = p.id AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS scene_count,
            (SELECT COALESCE(SUM(s.word_count), 0) FROM scenes s JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = p.id AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS script_words,
            (SELECT COUNT(*) FROM graph_nodes e
             JOIN scenes s ON s.id = json_extract(e.payload, '$.scene_id') JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = p.id AND e.type = 'song'
               AND e.deleted_at IS NULL AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS body_song_count,
            (SELECT COUNT(*) FROM floating_songs f
             WHERE f.project_id = p.id AND f.deleted_at IS NULL) AS floating_song_count
        FROM projects p WHERE p.deleted_at IS NULL ORDER BY p.updated_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = _api.row_to_dict(r)
        ptype = d.get("project_type") or "novel"
        body_songs = d.pop("body_song_count")
        floating_songs = d.pop("floating_song_count")
        novel_words = d.pop("novel_words")
        chapter_count = d.pop("chapter_count")
        act_count = d.pop("act_count")
        scene_count = d.pop("scene_count")
        script_words = d.pop("script_words")
        if ptype == "novel":
            d["totalWords"] = novel_words
            d["chapterCount"] = chapter_count
        else:
            d["totalWords"] = script_words
            d["actCount"] = act_count
            d["sceneCount"] = scene_count
            if ptype == "musical":
                d["songCount"] = body_songs + floating_songs
        result.append(d)
    return result

def get_project_tree(project_id):
    """一次取回目录树：novel → 卷(含章节)；剧本 → 幕(含场)。替代前端 1+N 逐级请求"""
    conn = _api.db()
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
        by_parent.setdefault(ch[pid_field], []).append(_api.row_to_dict(ch))
    result = []
    for p in parents:
        d = _api.row_to_dict(p)
        d[child_key] = by_parent.get(p["id"], [])
        result.append(d)
    conn.close()
    return {"type": ptype, key: result}

def get_project(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_project(data):
    conn = _api.db()
    cur = conn.execute(
        "INSERT INTO projects (title, subtitle, author, description, project_type) VALUES (?, ?, ?, ?, ?)",
        (data["title"], data.get("subtitle", ""), data.get("author", ""),
         data.get("description", ""), data.get("project_type", "novel"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_project(id, data):
    conn = _api.db()
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
    return _api.row_to_dict(row)

def delete_project(id):
    conn = _api.db()
    _api.soft_delete(conn, "projects", id)
    conn.close()

def get_stats(project_id):
    conn = _api.db()
    proj = conn.execute(
        "SELECT project_type FROM projects WHERE id = ? AND deleted_at IS NULL", (project_id,)).fetchone()
    ptype = (proj["project_type"] if proj else None) or "novel"
    if ptype == "novel":
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
    # 剧本/音乐剧：幕数、场数（幕未软删）、场字数和；音乐剧另计歌曲数（正文 song 元素 + 游离歌曲）
    row = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM acts WHERE project_id = ? AND deleted_at IS NULL) AS act_count,
            (SELECT COUNT(*) FROM scenes s JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = ? AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS scene_count,
            (SELECT COALESCE(SUM(s.word_count), 0) FROM scenes s JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = ? AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS total_words,
            (SELECT COUNT(*) FROM characters WHERE project_id = ? AND deleted_at IS NULL) AS character_count,
            (SELECT COUNT(*) FROM graph_nodes e
             JOIN scenes s ON s.id = json_extract(e.payload, '$.scene_id') JOIN acts a ON s.act_id = a.id
             WHERE s.project_id = ? AND e.type = 'song'
               AND e.deleted_at IS NULL AND s.deleted_at IS NULL AND a.deleted_at IS NULL) AS body_song_count,
            (SELECT COUNT(*) FROM floating_songs WHERE project_id = ? AND deleted_at IS NULL) AS floating_song_count
    """, (project_id,) * 6).fetchone()
    conn.close()
    stats = {
        "totalWords": row["total_words"],
        "actCount": row["act_count"],
        "sceneCount": row["scene_count"],
        "characterCount": row["character_count"],
    }
    if ptype == "musical":
        stats["songCount"] = row["body_song_count"] + row["floating_song_count"]
    return stats


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        api.register_entity(entity="project", table="projects", label="作品",
                            export=True, export_order=10)

        @api.route("/api/projects", methods=["GET"])
        def api_list_projects():
            return api.jsonify(list_projects())

        @api.route("/api/projects/<int:id>", methods=["GET"])
        def api_get_project(id):
            p = get_project(id)
            return api.jsonify(p) if p else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/projects", methods=["POST"])
        def api_create_project():
            return api.jsonify(create_project(api.snake_json())), 201

        @api.route("/api/projects/<int:id>", methods=["PUT"])
        def api_update_project(id):
            return api.jsonify(update_project(id, api.snake_json()))

        @api.route("/api/projects/<int:id>", methods=["DELETE"])
        def api_delete_project(id):
            delete_project(id)
            return api.jsonify({"ok": True})

        @api.route("/api/projects/<int:id>/stats", methods=["GET"])
        def api_get_stats(id):
            return api.jsonify(get_stats(id))

        @api.route("/api/projects/<int:id>/tree", methods=["GET"])
        def api_project_tree(id):
            # 目录树（卷+章 或 幕+场）一次取回，替代前端 1+N 逐级请求
            t = get_project_tree(id)
            return api.jsonify(t) if t else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/projects/import", methods=["POST"])
        def api_import_project():
            jt = api.require("json_transfer")
            if jt is None:
                return api.jsonify({"error": "json_transfer 插件未加载"}), 503
            # body 为导出文件解析后的完整 JSON 对象；格式错误由全局 ValueError 处理返回 400
            return api.jsonify({"project": jt["import_project_json"](api.req_json())}), 201
