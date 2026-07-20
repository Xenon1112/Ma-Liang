# 小说写作助手

基于 Python Flask + SQLite 的本地写作工具，面向小说作者，提供**版本管理、草稿管理、资料管理**及多格式导出。

## 功能

- **项目管理**：支持多部作品同时管理，软删除 + 回收站
- **卷/章结构**：卷 → 章 两级目录，拖拽排序，卷首语支持
- **版本管理**：自动保存 + 手动快照，版本历史查看、diff 对比、一键回滚
- **纯文本编辑器**：专注写作，无格式干扰，字数实时统计
- **大纲管理**：树形大纲，支持主线/支线/伏笔分类，可关联章节
- **人物管理**：自定义多字段描述（外貌、性格、背景等），出场记录
- **世界观设定**：分类管理（地理、历史、政治、魔法等）
- **灵感素材**：便签式收集，支持标签和分类
- **导出**：TXT 纯文本 / Word (.docx)，支持单章或全书导出
- **全文搜索**：跨章节、人物、设定、灵感搜索
- **备份恢复**：一键备份 SQLite 数据库，支持从备份恢复
- **三套主题**：亮色 / 暗色 / 护眼

## 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)（推荐的包管理工具）

## 快速开始

```bash
cd novel-writer
uv sync
uv run python app.py
```

浏览器打开 `http://localhost:5200`

## 项目结构

```
novel-writer/
├── app.py                 # Flask 主入口，REST API 路由
├── database.py            # SQLite 初始化 + 自动迁移
├── services/              # 业务逻辑层
│   ├── project_service.py
│   ├── chapter_service.py     # 卷 + 章
│   ├── draft_service.py       # 版本管理（核心）
│   ├── outline_service.py
│   ├── character_service.py
│   ├── world_setting_service.py
│   ├── inspiration_service.py
│   ├── export_service.py      # TXT / Word 导出
│   ├── backup_service.py
│   ├── recycle_service.py
│   ├── search_service.py
│   └── config_service.py
├── templates/
│   └── index.html         # 前端单页应用
├── static/
│   ├── css/
│   │   ├── main.css
│   │   └── themes.css
│   └── js/
│       ├── api.js         # REST API 封装
│       ├── app.js         # 应用入口
│       ├── state.js       # 前端状态管理
│       ├── utils/
│       └── components/    # UI 组件（12 个）
├── pyproject.toml
└── LICENSE
```

## 数据存储

数据库文件默认保存在用户目录：`~/novel-writer-data.db`

可通过备份功能导出/恢复数据库文件。

## 许可证

MIT License
