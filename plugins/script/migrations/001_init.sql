-- script 插件:剧本结构表(幕/场/关联表,结构原样抄自 core/database.py MIGRATION_V2/V3/V6 对应部分)
-- 存量库也会执行本文件,IF NOT EXISTS 保证 no-op,新库由本文件先建表(插件迁移早于内核 init_db),
-- 随后内核 V2/V3 的 CREATE IF NOT EXISTS 与 V6 的 ALTER 均因已存在被忽略,双保险
-- 注意:迁移 SQL 按半角分号切分执行,注释里不能出现半角分号
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

-- script_elements 旧表保留不删:存量数据已迁入 graph_nodes,本表仅作回滚底牌,不再读写
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
    score_file TEXT,
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

-- element_characters.element_id 原外键指向 script_elements(id),元素迁入 graph_nodes 后,
-- 新元素 id 不在旧表,旧外键会误拒插入,故本表不再声明指向元素的外键
-- (级联清理由 script 插件删除元素时代码负责,存量库由 002 迁移重建本表到同一形状)
CREATE TABLE IF NOT EXISTS element_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    sort_order REAL DEFAULT 0,
    UNIQUE(element_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_acts_project ON acts(project_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_scenes_act ON scenes(act_id, deleted_at, sort_order);
CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_elements_scene ON script_elements(scene_id, parent_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_scene_chars ON scene_characters(scene_id);
CREATE INDEX IF NOT EXISTS idx_element_chars ON element_characters(element_id);

-- 存量数据迁移:script_elements 逐行复制进 graph_nodes,保留原 id(WHERE NOT EXISTS 保证幂等可重入)
-- 关联表(scene_characters/element_characters)、乐谱文件名、外部快照引用因此无需重映射
-- 约定:顶层元素的 parent_id 列指向场景 id(异构父,scenes 是表不是节点),
-- 嵌套元素(歌曲内唱词等)的 parent_id 列指向父元素节点 id,
-- 消歧靠 payload 内的 scene_id(元素所属场)与 parent_id(仅元素父,顶层为 null),
-- 凡按「场」或「父元素」取元素都必须过 payload 条件,不能只看 parent_id 列(节点 id 与场景 id 可能数值相撞)
INSERT INTO graph_nodes (id, project_id, type, parent_id, sort_order, payload, created_at, updated_at, deleted_at)
SELECT e.id, s.project_id, e.element_type,
       COALESCE(e.parent_id, e.scene_id),
       e.sort_order,
       json_object('scene_id', e.scene_id, 'parent_id', e.parent_id,
                   'character_id', e.character_id, 'content', e.content,
                   'song_title', e.song_title, 'score_file', e.score_file,
                   'version_number', e.version_number),
       e.created_at, e.updated_at, e.deleted_at
FROM script_elements e JOIN scenes s ON e.scene_id = s.id
WHERE NOT EXISTS (SELECT 1 FROM graph_nodes g WHERE g.id = e.id);
