-- 项目管理插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
-- project_type 列来自全局 MIGRATION_V2 的 ALTER,这里直接并入建表
-- (存量库也会执行本文件,IF NOT EXISTS 保证 no-op,新库先建表,随后内核 init_db 的 V2 ALTER 因 duplicate column 被忽略,双保险)
-- 注意:迁移 SQL 按半角分号切分执行,注释里不能再出现半角分号
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subtitle TEXT DEFAULT '',
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'writing',
    project_type TEXT DEFAULT 'novel',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted_at);
