-- 灵感笔记插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
CREATE TABLE IF NOT EXISTS inspirations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT DEFAULT 'inspiration',
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    source TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    linked_chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_inspirations_project ON inspirations(project_id, deleted_at);
