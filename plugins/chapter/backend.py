"""卷章管理插件:数据访问 + 路由注册(原 services/chapter_service.py 与 app.py 卷/章路由迁移而来)"""

_api = None  # activate 时注入的 PluginAPI

# ====== Volumes ======

def list_volumes(project_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM volumes WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_volume(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM volumes WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_volume(data):
    conn = _api.db()
    order = data.get("sort_order", _api.next_sort_order(conn, "volumes", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO volumes (project_id, title, preface, sort_order) VALUES (?, ?, ?, ?)",
        (data["project_id"], data["title"], data.get("preface", ""), order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM volumes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_volume(id, data):
    conn = _api.db()
    allowed = ["title", "preface"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE volumes SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM volumes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def reorder_volumes(project_id, ordered_ids):
    conn = _api.db()
    for i, vid in enumerate(ordered_ids):
        conn.execute("UPDATE volumes SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, vid, project_id))
    conn.commit()
    conn.close()

# ====== Chapters ======

def list_chapters(volume_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM chapters WHERE volume_id = ? AND deleted_at IS NULL ORDER BY sort_order", (volume_id,)
    ).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_chapter(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM chapters WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_chapter(data):
    conn = _api.db()
    order = data.get("sort_order", _api.next_sort_order(conn, "chapters", "volume_id", data["volume_id"]))
    cur = conn.execute(
        "INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (?, ?, ?, ?)",
        (data["volume_id"], data["project_id"], data["title"], order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_chapter(id, data):
    conn = _api.db()
    allowed = ["title", "status", "word_count"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            vals.append(data[k])
    # 跨卷移动：排到目标卷末尾
    if "volume_id" in data:
        sets.append("volume_id = ?")
        vals.append(data["volume_id"])
        sets.append("sort_order = ?")
        vals.append(_api.next_sort_order(conn, "chapters", "volume_id", data["volume_id"]))
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE chapters SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def reorder_chapters(volume_id, ordered_ids):
    conn = _api.db()
    for i, cid in enumerate(ordered_ids):
        conn.execute("UPDATE chapters SET sort_order = ? WHERE id = ? AND volume_id = ?", (i + 1, cid, volume_id))
    conn.commit()
    conn.close()


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        api.register_entity(entity="volume", table="volumes", label="卷",
                            export=True, export_order=20)
        api.register_entity(entity="chapter", table="chapters", label="章",
                            export=True, export_order=30)

        # 对外提供卷/章查询,draft 插件的保存前目标校验依赖它(运行时再取,避免加载顺序耦合)
        api.provide("chapter", {
            "get_volume": get_volume,
            "get_chapter": get_chapter,
        })

        # ====== Volume API ======

        @api.route("/api/volumes", methods=["GET"])
        def api_list_volumes():
            project_id = api.request.args.get("projectId", type=int)
            return api.jsonify(list_volumes(project_id))

        @api.route("/api/volumes/<int:id>", methods=["GET"])
        def api_get_volume(id):
            v = get_volume(id)
            return api.jsonify(v) if v else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/volumes", methods=["POST"])
        def api_create_volume():
            return api.jsonify(create_volume(api.snake_json())), 201

        @api.route("/api/volumes/<int:id>", methods=["PUT"])
        def api_update_volume(id):
            return api.jsonify(update_volume(id, api.snake_json()))

        @api.route("/api/volumes/<int:id>", methods=["DELETE"])
        def api_delete_volume(id):
            conn = api.db()
            api.soft_delete(conn, "volumes", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/volumes/reorder", methods=["POST"])
        def api_reorder_volumes():
            data = api.req_json()
            reorder_volumes(data["projectId"], data["orderedIds"])
            return api.jsonify({"ok": True})

        # Volume preface routes(卷首语正文存 drafts 表,版本读写委托 draft 插件)
        @api.route("/api/volumes/<int:id>/preface", methods=["PUT"])
        def api_update_preface(id):
            if not get_volume(id):
                return api.jsonify({"error": "卷不存在或已删除"}), 404
            data = api.req_json()
            update_volume(id, {"preface": data["content"]})
            draft_svc = api.require("draft")
            if draft_svc is None:
                return api.jsonify({"error": "draft 插件未加载"}), 503
            return api.jsonify(draft_svc["save_draft"]({"volume_id": id, "content": data["content"], "version_tag": "auto"}))

        @api.route("/api/volumes/<int:id>/preface-versions", methods=["GET"])
        def api_preface_versions(id):
            draft_svc = api.require("draft")
            if draft_svc is None:
                return api.jsonify({"error": "draft 插件未加载"}), 503
            return api.jsonify(draft_svc["list_drafts"](volume_id=id))

        # ====== Chapter API ======

        @api.route("/api/chapters", methods=["GET"])
        def api_list_chapters():
            volume_id = api.request.args.get("volumeId", type=int)
            return api.jsonify(list_chapters(volume_id))

        @api.route("/api/chapters/<int:id>", methods=["GET"])
        def api_get_chapter(id):
            c = get_chapter(id)
            return api.jsonify(c) if c else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/chapters", methods=["POST"])
        def api_create_chapter():
            return api.jsonify(create_chapter(api.snake_json())), 201

        @api.route("/api/chapters/<int:id>", methods=["PUT"])
        def api_update_chapter(id):
            return api.jsonify(update_chapter(id, api.snake_json()))

        @api.route("/api/chapters/<int:id>", methods=["DELETE"])
        def api_delete_chapter(id):
            conn = api.db()
            api.soft_delete(conn, "chapters", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/chapters/reorder", methods=["POST"])
        def api_reorder_chapters():
            data = api.req_json()
            reorder_chapters(data["volumeId"], data["orderedIds"])
            return api.jsonify({"ok": True})
