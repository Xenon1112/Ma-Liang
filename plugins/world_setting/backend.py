"""世界观设定插件:数据访问 + 路由注册(原 services/world_setting_service.py 迁移而来)"""

_api = None  # activate 时注入的 PluginAPI


def list_settings(project_id, category=None):
    conn = _api.db()
    sql = "SELECT * FROM world_settings WHERE project_id = ? AND deleted_at IS NULL"
    params = [project_id]
    if category:
        sql += " AND category = ?"; params.append(category)
    sql += " ORDER BY category, sort_order"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_setting(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM world_settings WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_setting(data):
    conn = _api.db()
    order = data.get("sort_order", _api.next_sort_order(conn, "world_settings", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO world_settings (project_id, category, title, content, sort_order) VALUES (?, ?, ?, ?, ?)",
        (data["project_id"], data["category"], data["title"], data.get("content", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM world_settings WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_setting(id, data):
    conn = _api.db()
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
    return _api.row_to_dict(row)


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        api.register_entity(entity="world_setting", table="world_settings", label="设定",
                            export=True, export_order=60)

        @api.route("/api/world-settings", methods=["GET"])
        def api_list_settings():
            project_id = api.request.args.get("projectId", type=int)
            category = api.request.args.get("category")
            return api.jsonify(list_settings(project_id, category))

        @api.route("/api/world-settings/<int:id>", methods=["GET"])
        def api_get_setting(id):
            s = get_setting(id)
            return api.jsonify(s) if s else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/world-settings", methods=["POST"])
        def api_create_setting():
            return api.jsonify(create_setting(api.snake_json())), 201

        @api.route("/api/world-settings/<int:id>", methods=["PUT"])
        def api_update_setting(id):
            return api.jsonify(update_setting(id, api.snake_json()))

        @api.route("/api/world-settings/<int:id>", methods=["DELETE"])
        def api_delete_setting(id):
            conn = api.db()
            api.soft_delete(conn, "world_settings", id)
            conn.close()
            return api.jsonify({"ok": True})
