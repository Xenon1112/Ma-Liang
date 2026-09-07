-- graph 插件:统一块级线性节点模型地基表
-- 层级与顺序用 parent_id + sort_order 表达(不做分支边),NULL parent_id 为根级
-- 节点内容放 payload(JSON 文本),形状由节点类型决定
CREATE TABLE IF NOT EXISTS graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    parent_id INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_children ON graph_nodes(project_id, parent_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(project_id, type);
