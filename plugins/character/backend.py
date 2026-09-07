"""人物管理插件:数据访问 + 路由注册(原 services/character_service.py 与 app.py Character 路由迁移而来)"""

_api = None  # activate 时注入的 PluginAPI


def list_characters(project_id):
    conn = _api.db()
    rows = conn.execute(
        "SELECT * FROM characters WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [_api.row_to_dict(r) for r in rows]

def get_character(id):
    conn = _api.db()
    char = conn.execute("SELECT * FROM characters WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if not char:
        conn.close(); return None
    char = _api.row_to_dict(char)
    char["fields"] = [_api.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM character_fields WHERE character_id = ? ORDER BY sort_order", (id,)
    ).fetchall()]
    char["appearances"] = [_api.row_to_dict(r) for r in conn.execute("""
        SELECT ca.*, c.title AS chapter_title, v.title AS volume_title
        FROM character_appearances ca
        JOIN chapters c ON ca.chapter_id = c.id
        JOIN volumes v ON c.volume_id = v.id
        WHERE ca.character_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL
    """, (id,)).fetchall()]
    conn.close()
    return char

def create_character(data):
    conn = _api.db()
    order = data.get("sort_order", _api.next_sort_order(conn, "characters", "project_id", data["project_id"]))
    cur = conn.execute(
        "INSERT INTO characters (project_id, name, aliases, sort_order) VALUES (?, ?, ?, ?)",
        (data["project_id"], data["name"], data.get("aliases", ""), order)
    )
    char_id = cur.lastrowid
    for i, name in enumerate(["外貌", "性格", "背景", "能力", "口头禅", "备注"]):
        conn.execute("INSERT INTO character_fields (character_id, field_name, sort_order) VALUES (?, ?, ?)", (char_id, name, i + 1))
    conn.commit()
    conn.close()
    return get_character(char_id)

def update_character(id, data):
    conn = _api.db()
    allowed = ["name", "aliases"]
    sets, vals = [], []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?"); vals.append(data[k])
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        vals.append(id)
        conn.execute(f"UPDATE characters SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    conn.close()
    return get_character(id)

def add_field(data):
    conn = _api.db()
    order = _api.next_sort_order(conn, "character_fields", "character_id", data["character_id"])
    cur = conn.execute(
        "INSERT INTO character_fields (character_id, field_name, sort_order) VALUES (?, ?, ?)",
        (data["character_id"], data["field_name"], order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM character_fields WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def update_field(field_id, data):
    conn = _api.db()
    sets, vals = [], []
    if "field_name" in data:
        sets.append("field_name = ?"); vals.append(data["field_name"])
    if "content" in data:
        sets.append("content = ?"); vals.append(data["content"])
    if sets:
        vals.append(field_id)
        conn.execute(f"UPDATE character_fields SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    row = conn.execute("SELECT * FROM character_fields WHERE id = ?", (field_id,)).fetchone()
    conn.close()
    return _api.row_to_dict(row)

def remove_field(field_id):
    conn = _api.db()
    conn.execute("DELETE FROM character_fields WHERE id = ?", (field_id,))
    conn.commit()
    conn.close()

def reorder_fields(character_id, ordered_ids):
    conn = _api.db()
    for i, fid in enumerate(ordered_ids):
        conn.execute("UPDATE character_fields SET sort_order = ? WHERE id = ? AND character_id = ?", (i + 1, fid, character_id))
    conn.commit()
    conn.close()

def set_appearances(character_id, appearances):
    conn = _api.db()
    try:
        conn.execute("DELETE FROM character_appearances WHERE character_id = ?", (character_id,))
        for a in (appearances or []):
            conn.execute("INSERT OR REPLACE INTO character_appearances (character_id, chapter_id, note) VALUES (?, ?, ?)",
                         (character_id, a.get("chapter_id"), a.get("note", "")))
        conn.commit()
    finally:
        conn.close()


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        api.register_entity(entity="character", table="characters", label="人物",
                            name_column="name", export=True, export_order=50,
                            fk={"project_id": "project"})
        # character_fields/character_appearances 是附属表(无 deleted_at,不进回收站),
        # 注册仅为 JSON 导出/导入的声明式搬运
        api.register_entity(entity="character_field", table="character_fields", label="人物字段",
                            recycle=False, export=True, export_order=55,
                            fk={"character_id": "character"})
        api.register_entity(entity="character_appearance", table="character_appearances", label="人物出场",
                            recycle=False, export=True, export_order=56,
                            fk={"character_id": "character", "chapter_id": "chapter"})

        # ====== Character API ======

        @api.route("/api/characters", methods=["GET"])
        def api_list_characters():
            project_id = api.request.args.get("projectId", type=int)
            return api.jsonify(list_characters(project_id))

        @api.route("/api/characters/<int:id>", methods=["GET"])
        def api_get_character(id):
            c = get_character(id)
            return api.jsonify(c) if c else (api.jsonify({"error": "not found"}), 404)

        @api.route("/api/characters", methods=["POST"])
        def api_create_character():
            return api.jsonify(create_character(api.snake_json())), 201

        @api.route("/api/characters/<int:id>", methods=["PUT"])
        def api_update_character(id):
            return api.jsonify(update_character(id, api.snake_json()))

        @api.route("/api/characters/<int:id>", methods=["DELETE"])
        def api_delete_character(id):
            conn = api.db()
            api.soft_delete(conn, "characters", id)
            conn.close()
            return api.jsonify({"ok": True})

        @api.route("/api/characters/fields", methods=["POST"])
        def api_add_field():
            return api.jsonify(add_field(api.snake_json())), 201

        @api.route("/api/characters/fields/<int:id>", methods=["PUT"])
        def api_update_field(id):
            return api.jsonify(update_field(id, api.snake_json()))

        @api.route("/api/characters/fields/<int:id>", methods=["DELETE"])
        def api_remove_field(id):
            remove_field(id)
            return api.jsonify({"ok": True})

        @api.route("/api/characters/<int:id>/fields/reorder", methods=["POST"])
        def api_reorder_fields(id):
            reorder_fields(id, api.req_json()["orderedIds"])
            return api.jsonify({"ok": True})

        @api.route("/api/characters/<int:id>/appearances", methods=["PUT"])
        def api_set_appearances(id):
            body = api.request.get_json(silent=True)
            # 兼容两种请求体：直接数组 [{chapterId, note}, ...] 或 {"appearances": [...]}
            if isinstance(body, list):
                appearances = api.convert_keys(body)
            else:
                appearances = api.convert_keys(body or {}).get("appearances", [])
            set_appearances(id, appearances)
            return api.jsonify({"ok": True})
