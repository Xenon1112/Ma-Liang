-- 人物管理插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aliases TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS character_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    content TEXT DEFAULT '',
    sort_order REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS character_appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    note TEXT DEFAULT '',
    UNIQUE(character_id, chapter_id)
);

CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, deleted_at);
