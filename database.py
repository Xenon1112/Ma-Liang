import sqlite3
import os
import sys
import hashlib
import re
import shutil
from pathlib import Path

DB_PATH = None
APP_NAME = "novel-writer"

def get_user_data_dir():
    """系统标准用户数据目录（首次调用时自动创建）"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        d = base / APP_NAME
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        d = Path.home() / f".{APP_NAME}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_db_path():
    global DB_PATH
    if DB_PATH is None:
        new_path = get_user_data_dir() / "data.db"
        # 迁移旧版位于用户主目录下的数据库文件
        old_path = Path.home() / "novel-writer-data.db"
        if old_path.exists() and not new_path.exists():
            try:
                shutil.copy2(old_path, new_path)
            except OSError:
                pass
        DB_PATH = str(new_path)
    return DB_PATH

def set_db_path(path):
    global DB_PATH
    DB_PATH = path

def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS db_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    row = conn.execute("SELECT MAX(version) as v FROM db_version").fetchone()
    current = row["v"] or 0

    migrations = [
        (1, MIGRATION_V1),
        (2, MIGRATION_V2),
        (3, MIGRATION_V3),
    ]
    for ver, sql in migrations:
        if ver > current:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as e:
                        # 仅忽略"已存在"类错误（如重复加列），磁盘故障等真实错误照常抛出
                        msg = str(e).lower()
                        if "already exists" not in msg and "duplicate column" not in msg:
                            raise
            conn.execute("INSERT INTO db_version (version) VALUES (?)", (ver,))
            print(f"Migration v{ver} applied")
    conn.commit()
    conn.close()

def hash_content(content):
    return hashlib.sha256((content or "").encode()).hexdigest()

def count_words(text):
    text = text or ""
    chinese = len(re.findall(r'[一-鿿〇]', text))
    total = len(re.sub(r'\s', '', text))
    return chinese, total

def next_sort_order(conn, table, where_field, where_value):
    # 并非所有表都有 deleted_at 列（如 character_fields），按需拼接条件
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    cond = " AND deleted_at IS NULL" if "deleted_at" in cols else ""
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM {table} WHERE {where_field} = ?{cond}",
        (where_value,)
    ).fetchone()
    return row["n"]


MIGRATION_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subtitle TEXT DEFAULT '',
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'writing',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

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

CREATE TABLE IF NOT EXISTS world_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

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

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#808080'
);

CREATE TABLE IF NOT EXISTS entity_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(entity_type, entity_id, tag_id)
);

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_projects_deleted ON projects(deleted_at);
CREATE INDEX IF NOT EXISTS idx_volumes_project ON volumes(project_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_chapters_project ON chapters(project_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_drafts_chapter ON drafts(chapter_id, created_at);
CREATE INDEX IF NOT EXISTS idx_drafts_volume ON drafts(volume_id, created_at);
CREATE INDEX IF NOT EXISTS idx_outlines_project ON outlines(project_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_world_settings_project ON world_settings(project_id, deleted_at, category);
CREATE INDEX IF NOT EXISTS idx_inspirations_project ON inspirations(project_id, deleted_at);
"""

MIGRATION_V2 = """
ALTER TABLE projects ADD COLUMN project_type TEXT DEFAULT 'novel';

CREATE TABLE IF NOT EXISTS script_config (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    script_type TEXT NOT NULL DEFAULT 'play'
);

CREATE TABLE IF NOT EXISTS acts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    act_id INTEGER NOT NULL REFERENCES acts(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    setting TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    word_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS script_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES script_elements(id) ON DELETE CASCADE,
    element_type TEXT NOT NULL,
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    content TEXT DEFAULT '',
    song_title TEXT DEFAULT '',
    sort_order REAL DEFAULT 0,
    version_number INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS scene_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    note TEXT DEFAULT '',
    UNIQUE(scene_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_acts_project ON acts(project_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_scenes_act ON scenes(act_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_elements_scene ON script_elements(scene_id, parent_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_scene_chars ON scene_characters(scene_id);
"""

MIGRATION_V3 = """
CREATE TABLE IF NOT EXISTS element_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL REFERENCES script_elements(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    sort_order REAL DEFAULT 0,
    UNIQUE(element_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_element_chars ON element_characters(element_id);
"""


def soft_delete(conn, table, id):
    conn.execute(f"UPDATE {table} SET deleted_at = datetime('now','localtime') WHERE id = ?", (id,))
    conn.commit()

def restore_soft_delete(conn, table, id):
    conn.execute(f"UPDATE {table} SET deleted_at = NULL WHERE id = ?", (id,))
    conn.commit()

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)
