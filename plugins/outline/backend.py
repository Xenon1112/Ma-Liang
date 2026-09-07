"""大纲管理插件:数据访问 + 路由注册(原 services/outline_service.py 与 app.py Outline 路由迁移而来)"""

_api = None  # activate 时注入的 PluginAPI

def _build_tree(rows, parent_id=None):
    return [
        {**_api.row_to_dict(r), "children": _build_tree(rows, r["id"])}
        for r in rows if r["parent_id"] == parent_id
    ]

def tree(project_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM outlines WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return _build_tree(rows)

def get_outline(id):
    conn = _api.db()
    row = conn.execute("SELECT * FROM outlines WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def create_outline(data):
    conn = _api.db()
    order = data.get("sort_order", _api.next_sort_order(conn, "outlines", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO outlines (project_id, parent_id, title, content, sort_order, node_type, linked_chapter_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["project_id"], data.get("parent_id"), data["title"], data.get("content", ""), order,
         data.get("node_type", "chapter_outline"), data.get("linked_chapter_id"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM outlines WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

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
    conn = _api.db()
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
    return _api.row_to_dict(row)

def reorder_outlines(project_id, ordered_ids):
    conn = _api.db()
    for i, oid in enumerate(ordered_ids):
        conn.execute("UPDATE outlines SET sort_order = ? WHERE id = ? AND project_id = ?", (i + 1, oid, project_id))
    conn.commit()
    conn.close()

def link_chapter(id, chapter_id):
    return update_outline(id, {"linked_chapter_id": chapter_id})


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        api.register_entity(entity="outline", table="outlines", label="大纲",
                            export=True, export_order=40,
                            fk={"project_id": "project"},
                            weak_fk={"parent_id": "outline", "linked_chapter_id": "chapter"})

        @api.route("/api/outlines", methods=["GET"])
        def api_outline_tree():
            project_id = api.request.args.get("projectId", type=int)
            return api.jsonify(tree(project_id))

        @api.route("/api/outlines/<int:id>", methods=["GET"])
        def api_get_outline(id):
            o = get_outline(id)
            return api.jsonify(o) if o else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/outlines", methods=["POST"])
        def api_create_outline():
            return api.jsonify(create_outline(api.snake_json())), 201

        @api.route("/api/outlines/<int:id>", methods=["PUT"])
        def api_update_outline(id):
            return api.jsonify(update_outline(id, api.snake_json()))

        @api.route("/api/outlines/<int:id>", methods=["DELETE"])
        def api_delete_outline(id):
            conn = api.db()
            # 有未删除的子节点时拒绝删除，避免子节点成为不可见孤儿
            child = conn.execute(
                "SELECT 1 FROM outlines WHERE parent_id = ? AND deleted_at IS NULL LIMIT 1", (id,)
            ).fetchone()
            if child:
                conn.close()
                return api.jsonify({"error": "请先删除子节点"}), 400
            api.soft_delete(conn, "outlines", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/outlines/reorder", methods=["POST"])
        def api_reorder_outlines():
            data = api.req_json()
            reorder_outlines(data["projectId"], data["orderedIds"])
            return api.jsonify({"ok": True})

        @api.route("/api/outlines/<int:id>/link", methods=["POST"])
        def api_link_chapter(id):
            return api.jsonify(link_chapter(id, api.req_json().get("chapterId")))
