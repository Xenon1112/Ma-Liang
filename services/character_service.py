from core.database import get_conn, row_to_dict, next_sort_order

def list_characters(project_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM characters WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_character(id):
    conn = get_conn()
    char = conn.execute("SELECT * FROM characters WHERE id = ? AND deleted_at IS NULL", (id,)).fetchone()
    if not char:
        conn.close(); return None
    char = row_to_dict(char)
    char["fields"] = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM character_fields WHERE character_id = ? ORDER BY sort_order", (id,)
    ).fetchall()]
    char["appearances"] = [row_to_dict(r) for r in conn.execute("""
        SELECT ca.*, c.title AS chapter_title, v.title AS volume_title
        FROM character_appearances ca
        JOIN chapters c ON ca.chapter_id = c.id
        JOIN volumes v ON c.volume_id = v.id
        WHERE ca.character_id = ? AND c.deleted_at IS NULL AND v.deleted_at IS NULL
    """, (id,)).fetchall()]
    conn.close()
    return char

def create_character(data):
    conn = get_conn()
    order = data.get("sort_order", next_sort_order(conn, "characters", "project_id", data["project_id"]))
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
    conn = get_conn()
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
    conn = get_conn()
    order = next_sort_order(conn, "character_fields", "character_id", data["character_id"])
    cur = conn.execute(
        "INSERT INTO character_fields (character_id, field_name, sort_order) VALUES (?, ?, ?)",
        (data["character_id"], data["field_name"], order)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM character_fields WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)

def update_field(field_id, data):
    conn = get_conn()
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
    return row_to_dict(row)

def remove_field(field_id):
    conn = get_conn()
    conn.execute("DELETE FROM character_fields WHERE id = ?", (field_id,))
    conn.commit()
    conn.close()

def reorder_fields(character_id, ordered_ids):
    conn = get_conn()
    for i, fid in enumerate(ordered_ids):
        conn.execute("UPDATE character_fields SET sort_order = ? WHERE id = ? AND character_id = ?", (i + 1, fid, character_id))
    conn.commit()
    conn.close()

def set_appearances(character_id, appearances):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM character_appearances WHERE character_id = ?", (character_id,))
        for a in (appearances or []):
            conn.execute("INSERT OR REPLACE INTO character_appearances (character_id, chapter_id, note) VALUES (?, ?, ?)",
                         (character_id, a.get("chapter_id"), a.get("note", "")))
        conn.commit()
    finally:
        conn.close()
