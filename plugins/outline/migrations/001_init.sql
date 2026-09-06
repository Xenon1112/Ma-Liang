-- 大纲管理插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
CREATE TABLE IF NOT EXISTS outlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES outlines(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    node_type TEXT DEFAULT 'chapter_outline',
    linked_chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_outlines_project ON outlines(project_id, deleted_at);
