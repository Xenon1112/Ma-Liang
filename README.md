# 马良 (Ma Liang)

马良是一款面向小说/剧本作者的本地写作工具，基于 Python Flask + SQLite，提供**版本管理、草稿管理、资料管理**及多格式导出。

支持三种写作模式：**小说**、**话剧剧本**、**音乐剧剧本**。

## 功能

- **三合一写作模式**：小说（纯白编辑器）/ 话剧剧本（卡片编辑器）/ 音乐剧剧本（卡片编辑器 + 唱词）
- **版本管理**：自动保存 + 手动快照，版本历史查看、diff 对比、一键回滚
- **剧本卡片编辑器**：动作 / 对白 / 歌曲 / 唱词 四种卡片，歌曲嵌套唱词，双击/右键菜单收起歌曲
- **齐白与叠白**：对白卡支持多角色（齐白），双列叠白容器（Dual Dialogue）表现同时说话
- **重唱**：歌曲内重唱容器，多声部唱词并排导出
- **游离歌曲**：音乐剧歌曲库，不进正文与 TXT/DOCX（仅 JSON 导出），支持歌中对白/重唱，与正文歌曲双向互转
- **幕/场结构**：幕 → 场 两级目录，拖拽排序，场可跨幕移动，场景描述 + 出场人物管理
- **卷/章结构**：卷 → 章 两级目录，卷首语支持（小说模式）
- **纯文本编辑器**：专注写作，无格式干扰，字数实时统计
- **分模式统计**：小说按卷/章统计，剧本按幕/场统计字数，音乐剧另计歌曲数
- **大纲管理**：树形大纲，主线/支线/伏笔分类，可关联章节
- **人物管理**：自定义多字段描述（外貌、性格、背景等），出场记录
- **世界观设定**：分类管理（地理、历史、政治、魔法等）
- **灵感素材**：便签式收集，标签和分类
- **导出**：TXT / Word (.docx)，单章或全书；同角色动作+对白自动合并成段
- **JSON 导出/导入**：整项目导出为 JSON（不含回收站），导入自动生成副本
- **全文搜索**：跨章节正文、剧本场景卡片、游离歌曲、大纲、人物、设定、灵感，点击直达
- **备份恢复**：一键备份/恢复 SQLite 数据库
- **回收站**：软删除 + 到期自动清除
- **编辑器体验**：保存按钮、侧栏与资料面板收起（状态记忆）、首页作品信息编辑、优雅退出
- **可自定义快捷键**：全局搜索 / 专注模式 / 章节切换 / 卡片类型切换等，键位可在设置中修改
- **三套主题**：亮色 / 暗色 / 护眼

## 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)

## 快速开始

```bash
uv sync
uv run python app.py
```

浏览器打开 `http://localhost:5200`

## 架构

```
┌──────────────────────────────────────────────────────┐
│  前端 (SPA)                                          │
│  templates/index.html                                │
│  ┌──────────┬──────────────────┬──────────────────┐  │
│  │ 目录树   │ 编辑器            │ 资料面板         │  │
│  │          │                  │                  │  │
│  │ 小说模式 │ 小说 → 纯白      │ 大纲 / 人物      │  │
│  │ 卷→章   │ 剧本 → 卡片      │ 设定 / 灵感      │  │
│  │          │                  │                  │  │
│  │ 剧本模式 │ 动作/对白/歌曲   │                  │  │
│  │ 幕→场   │ 唱词嵌套子卡片   │                  │  │
│  └──────────┴──────────────────┴──────────────────┘  │
│              ↕ REST API (fetch)                      │
├──────────────────────────────────────────────────────┤
│  后端 (Flask)                                        │
│  app.py — 70+ 路由                                   │
│  ┌──────────┬──────────┬──────────┬──────────────┐  │
│  │ project  │ chapter  │ draft    │ script       │  │
│  │ outline  │ character│ world    │ inspiration  │  │
│  │ export   │ backup   │ recycle  │ search/config│  │
│  │ json传输 │ floating │          │              │  │
│  └──────────┴──────────┴──────────┴──────────────┘  │
│              ↕                                        │
│  SQLite（系统用户数据目录 data.db）                     │
│  21 张表，版本化 migration (v1→v5)                     │
└──────────────────────────────────────────────────────┘
```

## 项目结构

```
novel-writer/
├── app.py                      # Flask 主入口，70+ REST API 路由
├── database.py                 # SQLite 初始化 + 版本化 migration (v1→v5)
├── _version.py                 # 版本号注入 (importlib.metadata / 打包回退)
├── services/                   # 业务逻辑层
│   ├── project_service.py      # 项目管理 + 分模式统计 + 目录树单请求
│   ├── chapter_service.py      # 卷 + 章 CRUD
│   ├── draft_service.py        # 版本管理 (SHA256 hash, LCS diff)
│   ├── script_service.py       # 剧本模式 (act/scene/element CRUD, 场景字数维护)
│   ├── floating_song_service.py # 游离歌曲 (唱词/对白/重唱, 与正文互转)
│   ├── outline_service.py      # 大纲 (tree 构建)
│   ├── character_service.py    # 人物 + 自定义字段 + 出场记录
│   ├── world_setting_service.py
│   ├── inspiration_service.py
│   ├── export_service.py       # TXT / Word (.docx) 导出
│   ├── json_transfer_service.py # 整项目 JSON 导出/导入 (不含回收站)
│   ├── backup_service.py       # DB 备份 + 恢复
│   ├── recycle_service.py      # 软删除 + 到期清理
│   ├── search_service.py       # 全文搜索 (章节/场景卡片/游离歌曲/资料)
│   └── config_service.py       # 应用配置
├── templates/
│   └── index.html              # 前端 SPA (三栏布局)
├── static/
│   ├── css/
│   │   ├── main.css            # 全局样式 + 布局 + 卡片编辑器样式
│   │   └── themes.css          # 三套主题变量 (light/dark/warm)
│   └── js/
│       ├── api.js              # REST API 封装层 (fetch)
│       ├── app.js              # 应用入口 + 模式切换 + 工具栏
│       ├── state.js            # 前端状态管理 + 事件系统
│       ├── shortcuts.js        # 可自定义快捷键系统
│       ├── utils/
│       │   ├── word-count.js   # 中文字数统计
│       │   └── debounce.js     # 输入防抖
│       └── components/
│           ├── modal.js             # 通用弹窗
│           ├── project-list.js      # 首页作品列表 (统计/编辑/导入)
│           ├── sidebar.js           # 小说目录树 (卷→章)
│           ├── script-sidebar.js    # 剧本目录树 (幕→场, 拖拽排序)
│           ├── editor.js            # 小说纯文本编辑器
│           ├── card-editor.js       # 剧本卡片编辑器 (核心)
│           ├── floating-song-editor.js # 游离歌曲编辑器
│           ├── version-panel.js     # 版本历史 + diff
│           ├── outline-tree.js      # 大纲树形编辑
│           ├── character-panel.js   # 人物多字段编辑
│           ├── world-setting-panel.js
│           ├── inspiration-panel.js
│           ├── search-panel.js      # 全局搜索
│           ├── recycle-bin.js       # 回收站
│           └── export-dialog.js     # 导出对话框
├── installer.nsi                # NSIS 安装包脚本
├── novel-writer.spec            # PyInstaller 单目录打包配置
├── novel-writer-onefile.spec    # PyInstaller 单文件打包配置 (可选)
├── novel-writer-mac.spec        # PyInstaller macOS .app 打包配置
├── .github/workflows/
│   └── build-mac.yml            # macOS CI 构建 (DMG 产物)
├── version_info.txt             # exe 版本信息资源
├── icon.ico                     # 应用图标 (多尺寸)
├── tools/                       # NSIS 工具链
├── debug_api_test.py            # API 全流程调试脚本
├── pyproject.toml               # uv 项目配置
├── uv.lock                      # 依赖锁定
├── dist/                        # 打包交付产物 (setup.exe / portable.zip)
├── LICENSE                      # MIT
└── README.md
```

## 数据存储

- 数据库文件位于系统标准用户数据目录（首次启动自动创建，旧版主目录数据库自动迁移）：
  - Windows: `%APPDATA%/novel-writer/data.db`
  - macOS: `~/Library/Application Support/novel-writer/data.db`
  - Linux: `~/.novel-writer/data.db`
- 21 张表：projects, volumes, chapters, drafts, outlines, characters, character_fields, character_appearances, world_settings, inspirations, tags, entity_tags, app_config, script_config, acts, scenes, script_elements, scene_characters, element_characters, floating_songs, floating_lyrics
- 版本化迁移 (v1→v5)，首次启动自动建表，老库自动升级

## 许可证

MIT License
