-- 卷章管理插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    preface TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id INTEGER NOT NULL REFERENCES volumes(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    sort_order REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    word_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_volumes_project ON volumes(project_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, deleted_at);
