"""灵感笔记插件:数据访问 + 路由注册(原 services/inspiration_service.py 迁移而来)"""

_api = None  # activate 时注入的 PluginAPI


def list_inspirations(project_id, type=None, tag=None):
    conn = _api.db()
    sql = "SELECT * FROM inspirations WHERE project_id = ? AND deleted_at IS NULL"
    params = [project_id]
    if type:
        sql += " AND type = ?"; params.append(type)
    if tag:
        sql += " AND tags LIKE ?"; params.append(f"%{tag}%")
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_inspiration(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM inspirations WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_inspiration(data):
    conn = _api.db()
    cur = conn.execute(
        "INSERT INTO inspirations (project_id, type, title, content, source, tags, linked_chapter_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["project_id"], data.get("type", "inspiration"), data["title"], data.get("content", ""),
         data.get("source", ""), data.get("tags", ""), data.get("linked_chapter_id"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM inspirations WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_inspiration(id, data):
    conn = _api.db()
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
    return _api.row_to_dict(row)


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        @api.route("/api/inspirations", methods=["GET"])
        def api_list_inspirations():
            project_id = api.request.args.get("projectId", type=int)
            return api.jsonify(list_inspirations(project_id, api.request.args.get("type"), api.request.args.get("tag")))

        @api.route("/api/inspirations/<int:id>", methods=["GET"])
        def api_get_inspiration(id):
            i = get_inspiration(id)
            return api.jsonify(i) if i else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/inspirations", methods=["POST"])
        def api_create_inspiration():
            return api.jsonify(create_inspiration(api.snake_json())), 201

        @api.route("/api/inspirations/<int:id>", methods=["PUT"])
        def api_update_inspiration(id):
            return api.jsonify(update_inspiration(id, api.snake_json()))

        @api.route("/api/inspirations/<int:id>", methods=["DELETE"])
        def api_delete_inspiration(id):
            conn = api.db()
            api.soft_delete(conn, "inspirations", id)
            conn.close()
            return api.jsonify({"ok": True})
