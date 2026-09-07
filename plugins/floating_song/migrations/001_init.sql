-- 游离歌曲(音乐剧:不挂场、不进正文,仅出现在 JSON 导出)
-- schema 逐列抄自全局 MIGRATION_V4/V5/V6(V5 的 element_type/parent_id 与 V6 的
-- score_file 为 ALTER 追加列,此处并入 CREATE TABLE 且保持末尾追加的物理列序)
CREATE TABLE IF NOT EXISTS floating_songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    song_title TEXT NOT NULL DEFAULT '',
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT,
    score_file TEXT
);

CREATE TABLE IF NOT EXISTS floating_lyrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES floating_songs(id) ON DELETE CASCADE,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    character_ids TEXT DEFAULT '[]',
    content TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    element_type TEXT DEFAULT 'lyric',
    parent_id INTEGER REFERENCES floating_lyrics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_floating_songs_project ON floating_songs(project_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_floating_lyrics_song ON floating_lyrics(song_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_floating_lyrics_parent ON floating_lyrics(song_id, parent_id, sort_order);
