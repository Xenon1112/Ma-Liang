"""回收站插件:软删除聚合 + 路由注册(原 services/recycle_service.py 与 app.py Recycle 路由迁移而来)

无专属表(软删除标记在各业务表的 deleted_at 列),故无 migrations 目录。
保留天数配置读 legacy 无前缀键 recycleRetentionDays(迁移期允许,键名保持不变)。

实体清单来自内核实体注册表(api.list_entities(),各实体插件 activate 时注册,
请求处理时取用,无加载顺序依赖);尚未插件化的实体走下方 LEGACY_ENTITY_TABLES 过渡映射。
"""
import math
from datetime import datetime, timedelta

_api = None  # activate 时注入的 PluginAPI

# 过渡映射:entity -> (table, name_column),只覆盖尚未插件化的实体
# act/scene 属于 script 服务(services/script_service.py,表由 core/database.py 全局 schema 建),
# 待阶段 3 script 迁移为插件并自行 register_entity 后删除本映射
LEGACY_ENTITY_TABLES = {
    "act": ("acts", "title"),
    "scene": ("scenes", "title"),
}

def _entity_tables():
    """合并实体注册表与 legacy 过渡映射,返回 {entity: (table, name_column)}"""
    tables = dict(LEGACY_ENTITY_TABLES)
    for info in _api.list_entities():
        tables[info["entity"]] = (info["table"], info["name_column"])
    return tables

def _retention_days():
    return int(_api.get_config("recycleRetentionDays", 30))

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
    conn = _api.db()
    items = []
    retention_days = _retention_days()
    now = datetime.now()

    for etype, (table, name_col) in _entity_tables().items():
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
    conn = _api.db()
    try:
        entry = _entity_tables().get(entity_type)
        if entry:
            # _require_deleted 可能抛 ValueError，finally 保证连接关闭（否则 Windows 上泄漏的连接会锁定 WAL 文件）
            _require_deleted(conn, entry[0], id)
            _api.restore_soft_delete(conn, entry[0], id)
    finally:
        conn.close()

def permanently_delete(entity_type, id):
    conn = _api.db()
    try:
        entry = _entity_tables().get(entity_type)
        if entry:
            _require_deleted(conn, entry[0], id)
            conn.execute(f"DELETE FROM {entry[0]} WHERE id = ?", (id,))
            conn.commit()
    finally:
        conn.close()

def clean_expired():
    conn = _api.db()
    retention_days = _retention_days()
    total = 0
    for etype, (table, name_col) in _entity_tables().items():
        cur = conn.execute(
            f"DELETE FROM {table} WHERE deleted_at IS NOT NULL AND datetime(deleted_at, '+' || ? || ' days') < datetime('now','localtime')",
            (retention_days,)
        )
        total += cur.rowcount
    conn.commit()
    conn.close()
    return total


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # ====== Recycle API ======

        @api.route("/api/recycle", methods=["GET"])
        def api_list_recycle():
            return api.jsonify(list_recycle())

        @api.route("/api/recycle/restore", methods=["POST"])
        def api_restore_recycle():
            data = api.req_json()
            restore(data["entityType"], data["entityId"])
            return api.jsonify({"ok": True})

        @api.route("/api/recycle/permanent-delete", methods=["POST"])
        def api_permanent_delete():
            data = api.req_json()
            permanently_delete(data["entityType"], data["entityId"])
            return api.jsonify({"ok": True})

        @api.route("/api/recycle/clean", methods=["POST"])
        def api_clean_expired():
            return api.jsonify({"count": clean_expired()})
