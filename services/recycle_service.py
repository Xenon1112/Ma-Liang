import math
from datetime import datetime, timedelta

from core.database import get_conn, row_to_dict, soft_delete, restore_soft_delete
from core.config import get_config as _get_config

ENTITY_TABLES = {
    "project": "projects",
    "volume": "volumes",
    "chapter": "chapters",
    "outline": "outlines",
    "character": "characters",
    "world_setting": "world_settings",
    "inspiration": "inspirations",
    "act": "acts",
    "scene": "scenes",
}

# 名称列不一致：characters 用 name，其余用 title
NAME_COLUMNS = {"characters": "name"}

def _remaining_days(deleted_at, retention_days, now):
    """按删除时间 + 保留天数计算剩余天数（int，可为负）和是否已过期"""
    try:
        deleted_dt = datetime.strptime(deleted_at, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return 0, True
    delta = deleted_dt + timedelta(days=retention_days) - now
    remaining = math.ceil(delta.total_seconds() / 86400)
    return remaining, remaining <= 0

def list_recycle():
    conn = get_conn()
    items = []
    config = _get_config()
    retention_days = int(config.get("recycleRetentionDays", 30))
    now = datetime.now()

    for etype, table in ENTITY_TABLES.items():
        name_col = NAME_COLUMNS.get(table, "title")
        rows = conn.execute(f"SELECT id, {name_col} AS title, deleted_at FROM {table} WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
        for r in rows:
            remaining, expired = _remaining_days(r["deleted_at"], retention_days, now)
            items.append({
                "entityType": etype,
                "entityId": r["id"],
                "displayName": f"{r['title']}(id:{r['id']})",
                "deletedAt": r["deleted_at"],
                "remainingDays": remaining,
                "expired": expired,
            })
    conn.close()
    return items

def _require_deleted(conn, table, id):
    """目标必须存在且处于已软删状态，否则抛错（防止绕过回收站操作活体数据）"""
    row = conn.execute(f"SELECT id FROM {table} WHERE id = ? AND deleted_at IS NOT NULL", (id,)).fetchone()
    if not row:
        raise ValueError("该记录不存在或未被删除")

def restore(entity_type, id):
    conn = get_conn()
    try:
        table = ENTITY_TABLES.get(entity_type)
        if table:
            # _require_deleted 可能抛 ValueError，finally 保证连接关闭（否则 Windows 上泄漏的连接会锁定 WAL 文件）
            _require_deleted(conn, table, id)
            restore_soft_delete(conn, table, id)
    finally:
        conn.close()

def permanently_delete(entity_type, id):
    conn = get_conn()
    try:
        table = ENTITY_TABLES.get(entity_type)
        if table:
            _require_deleted(conn, table, id)
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
            conn.commit()
    finally:
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
