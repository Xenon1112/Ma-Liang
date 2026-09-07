-- km_counter 初始建表(迁移按半角分号切分,注释中不得出现半角分号)
CREATE TABLE IF NOT EXISTS km_counter__notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    name TEXT NOT NULL,
    content TEXT DEFAULT ''
);
