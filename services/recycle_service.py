from database import get_conn, row_to_dict, soft_delete, restore_soft_delete
from services.config_service import get_config as _get_config

ENTITY_TABLES = {
    "project": "projects",
    "volume": "volumes",
    "chapter": "chapters",
    "outline": "outlines",
    "character": "characters",
    "world_setting": "world_settings",
    "inspiration": "inspirations",
}

def list_recycle():
    conn = get_conn()
    items = []
    config = _get_config()
    retention_days = int(config.get("recycleRetentionDays", 30))

    for etype, table in ENTITY_TABLES.items():
        rows = conn.execute(f"SELECT id, title, deleted_at FROM {table} WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
        for r in rows:
            items.append({
                "entityType": etype,
                "entityId": r["id"],
                "displayName": f"{r['title']}(id:{r['id']})",
                "deletedAt": r["deleted_at"],
                "remainingDays": 0,  # simplified
            })
    conn.close()
    return items

def restore(entity_type, id):
    conn = get_conn()
    table = ENTITY_TABLES.get(entity_type)
    if table:
        restore_soft_delete(conn, table, id)
    conn.close()

def permanently_delete(entity_type, id):
    conn = get_conn()
    table = ENTITY_TABLES.get(entity_type)
    if table:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
        conn.commit()
    conn.close()

def clean_expired():
    conn = get_conn()
    config = _get_config()
    retention_days = int(config.get("recycleRetentionDays", 30))
    total = 0
    for etype, table in ENTITY_TABLES.items():
        cur = conn.execute(
            f"DELETE FROM {table} WHERE deleted_at IS NOT NULL AND datetime(deleted_at, '+' || ? || ' days') < datetime('now','localtime')",
            (retention_days,)
        )
        total += cur.rowcount
    conn.commit()
    conn.close()
    return total
