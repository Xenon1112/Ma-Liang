-- 存量库重建 element_characters:去掉指向 script_elements(id) 的外键(元素已迁 graph_nodes,
-- 新元素 id 不在旧表,旧外键会误拒插入)。行数据原样保留(id 不变),重建结果与 001 的新库形状一致
-- 幂等:插件迁移只执行一次,手工重跑也同样收敛(新表 IF NOT EXISTS 建空表后被换入)
-- 注意:迁移 SQL 按半角分号切分执行,注释里不能出现半角分号
CREATE TABLE IF NOT EXISTS element_characters__nofk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    sort_order REAL DEFAULT 0,
    UNIQUE(element_id, character_id)
);

INSERT INTO element_characters__nofk (id, element_id, character_id, sort_order)
SELECT id, element_id, character_id, sort_order FROM element_characters;

DROP TABLE element_characters;

ALTER TABLE element_characters__nofk RENAME TO element_characters;

CREATE INDEX IF NOT EXISTS idx_element_chars ON element_characters(element_id);
