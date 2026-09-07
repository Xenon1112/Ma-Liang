-- chapter 插件:小说正文 text 节点化(G4),存量正文迁进 graph_nodes
-- 章节正文的实际存储是 drafts 表当前版本(chapters 表从未有过 content 列),
-- 本迁移把每章当前正文复制为 text 节点,drafts 表保留不删、作为回滚底牌
-- 布局(与 script 先例一致的异构父约定):type='text',parent_id 列 = 章节 id,
-- payload = {"chapter_id": 章节id, "content": 正文},sort_order 沿用章节 sort_order
-- 判重与后续查询一律过 payload 的 chapter_id 条件,不能只信 parent_id 列
-- (节点 id 与章节 id 数值可能相撞)
-- 不指定 id 列,自增分配:script 旧元素已按原 id 占住 graph_nodes 的 id 空间
-- 软删章节一并迁移,deleted_at 原样带上,回收站语义不变
-- 只迁当前正文非空的章节,空章不建节点,读取侧按空正文兜底(新建章节由代码建空节点)
-- 全幂等:NOT EXISTS 按 payload 的 chapter_id 判重,重复执行为 no-op

-- drafts 表本体归 draft 插件,但本迁移要读它,全新库上插件迁移早于内核 init_db,
-- 且 draft 以 optional_dependencies 排在本插件之后,故按相同结构兜底建表
-- (IF NOT EXISTS,draft 插件 001 与内核 V1 随后均为 no-op,与 script 001 同款双保险)
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

INSERT INTO graph_nodes (project_id, type, parent_id, sort_order, payload, created_at, updated_at, deleted_at)
SELECT c.project_id, 'text', c.id, c.sort_order,
       json_object('chapter_id', c.id, 'content',
                   COALESCE((SELECT d.content FROM drafts d
                             WHERE d.chapter_id = c.id AND d.is_current = 1
                             ORDER BY d.version_number DESC LIMIT 1), '')),
       c.created_at, c.updated_at, c.deleted_at
FROM chapters c
WHERE COALESCE((SELECT d.content FROM drafts d
                WHERE d.chapter_id = c.id AND d.is_current = 1
                ORDER BY d.version_number DESC LIMIT 1), '') <> ''
  AND NOT EXISTS (SELECT 1 FROM graph_nodes g
                  WHERE g.type = 'text'
                  AND json_extract(g.payload, '$.chapter_id') = c.id);
