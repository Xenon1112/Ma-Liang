-- 版本管理插件:建表(结构原样抄自 core/database.py MIGRATION_V1 对应部分)
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    volume_id INTEGER REFERENCES volumes(id) ON DELETE CASCADE,
    content TEXT DEFAULT '',
    version_number INTEGER NOT NULL,
    word_count INTEGER DEFAULT 0,
    change_note TEXT DEFAULT '',
    version_tag TEXT DEFAULT 'auto',
    is_current INTEGER DEFAULT 1,
    content_hash TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_chapter ON drafts(chapter_id, created_at);
CREATE INDEX IF NOT EXISTS idx_drafts_volume ON drafts(volume_id, created_at);
