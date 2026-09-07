# 马良 (Ma Liang)

马良是一款面向小说/剧本作者的本地写作工具，基于 Python 标准库 + SQLite，桌面窗口由 pywebview 提供（无 Flask 等 Web 框架依赖），提供**版本管理、草稿管理、资料管理**及多格式导出。

支持三种写作模式：**小说**、**话剧剧本**、**音乐剧剧本**。

## 功能

- **三合一写作模式**：小说（纯白编辑器）/ 话剧剧本（卡片编辑器）/ 音乐剧剧本（卡片编辑器 + 唱词）
- **版本管理**：自动保存 + 手动快照，版本历史查看、diff 对比、一键回滚
- **剧本卡片编辑器**：动作 / 对白 / 歌曲 / 唱词 四种卡片，歌曲嵌套唱词，双击/右键菜单收起歌曲
- **齐白与叠白**：对白卡支持多角色（齐白），双列叠白容器（Dual Dialogue）表现同时说话
- **重唱**：歌曲内重唱容器，多声部唱词并排导出
- **游离歌曲**：音乐剧歌曲库，不进正文与 TXT/DOCX（仅 JSON 导出），支持歌中对白/重唱，与正文歌曲双向互转
- **幕/场结构**：幕 → 场 两级目录，拖拽排序，场可跨幕移动，场景描述 + 出场人物管理
- **卷/章结构**：卷 → 章 两级目录，拖拽排序、章可跨卷移动，卷首语支持且纳入版本管理（小说模式）
- **纯文本编辑器**：专注写作，无格式干扰，字数实时统计；排版设置（衬线/黑体/等宽字体、字号、行距、栏宽），即时预览并记忆
- **分模式统计**：小说按卷/章统计，剧本按幕/场统计字数，音乐剧另计歌曲数
- **大纲管理**：树形大纲，主线/支线/伏笔分类，可关联章节
- **人物管理**：自定义多字段描述（外貌、性格、背景等），出场记录
- **世界观设定**：分类管理（地理、历史、政治、魔法等）
- **灵感素材**：便签式收集，标签和分类
- **导出**：TXT / Word (.docx)，单章或全书；同角色动作+对白自动合并成段
- **JSON 导出/导入**：整项目导出为 JSON（不含回收站），导入自动生成副本
- **全文搜索**：跨章节正文、剧本场景卡片、游离歌曲、大纲、人物、设定、灵感，点击直达
- **备份恢复**：一键备份；恢复时自动列出备份文件下拉选择，无需手输路径
- **回收站**：软删除 + 剩余保留天数显示，到期自动清除
- **编辑器体验**：保存按钮、侧栏与资料面板收起（状态记忆）、首页作品信息编辑、关窗/刷新兜底保存（pagehide keepalive）、优雅退出
- **可自定义快捷键**：全局搜索 / 专注模式 / 章节切换 / 卡片类型切换等，键位可在设置中修改
- **三套主题**：亮色 / 暗色 / 护眼，按钮实时显示当前主题，暗色主题全面板适配

## 环境要求

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)

## 快速开始

```bash
uv sync
uv run python app.py
```

默认打开内置桌面窗口；加 `--browser` 则用系统浏览器打开 `http://localhost:5200`

## 开发约定

- **所有 Python 命令一律通过 uv 执行**，不要直接调用系统 `python` / `pip`：
  - 运行应用：`uv run python app.py`（或 `--browser`）
  - 运行插件协议符合性测试：`uv run python tests/run_conformance.py`
  - 打包：`uv run pyinstaller novel-writer.spec`
  - 加依赖：`uv add <pkg>`；开发依赖：`uv add --dev <pkg>`
- 原因：依赖由 `pyproject.toml` + `uv.lock` 锁定，`uv run` 会在执行前自动同步 `.venv`；直调系统 Python 可能用到错误解释器或缺依赖。

图文新手教程见 [docs/新手教程.md](docs/新手教程.md)（另有 PDF 版）。

## 架构

```
┌──────────────────────────────────────────────────────┐
│  pywebview 原生窗口 (Edge WebView2 / macOS WKWebView) │
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
│  后端（纯标准库，无 Web 框架）                          │
│  core/httpd.py — 路由 shim (http.server)               │
│  app.py — 110+ 路由                                    │
│  ┌──────────┬──────────┬──────────┬──────────────┐  │
│  │ project  │ chapter  │ draft    │ script       │  │
│  │ outline  │ character│ export   │ floating     │  │
│  │ backup   │ recycle  │ search   │ json传输     │  │
│  └──────────┴──────────┴──────────┴──────────────┘  │
│  plugins/ — inspiration / world_setting (已插件化)     │
│              ↕                                        │
│  SQLite（系统用户数据目录 data.db）                     │
│  21 张表，版本化 migration (v1→v5)                     │
└──────────────────────────────────────────────────────┘
```

## 项目结构

```
novel-writer/
├── app.py                      # 主入口 + 内核杂项路由 + 未迁移的 Script/Floating-Song/Score 路由 + pywebview 窗口
├── core/                       # 内核（插件化重构，业务无关）
│   ├── httpd.py                # Flask API 子集 shim（纯标准库 http.server）
│   ├── database.py             # SQLite 初始化 + 版本化 migration + 插件迁移框架
│   ├── config.py               # 应用配置
│   ├── events.py               # 后端事件总线
│   ├── plugin_api.py           # 插件 API（插件唯一允许接触的边界，含 provide/require 服务注册表）
│   └── plugin_manager.py       # 插件发现/校验/拓扑排序/动态加载/故障隔离
├── _version.py                 # 版本号注入 (importlib.metadata / 打包回退)
├── plugins/                    # 内置插件（一切皆插件，与第三方插件同协议；各含 plugin.json + backend.py，按需含 migrations/ + web/）
│   ├── project/                # 项目管理 + 分模式统计 + 目录树单请求 + JSON 导入入口
│   ├── chapter/                # 卷章管理（含小说目录树/编辑器等前端）
│   ├── draft/                  # 版本管理 (SHA256 hash, LCS diff)
│   ├── outline/                # 大纲管理 (tree 构建)
│   ├── character/              # 人物管理 (多字段编辑)
│   ├── inspiration/            # 灵感笔记
│   ├── world_setting/          # 世界观设定
│   ├── search/                 # 全文搜索
│   ├── graph/                  # 内容节点地基 (graph_nodes + 类型注册表)
│   ├── script/                 # 剧本模式 (act/scene/卡片 CRUD; 卡片存 graph_nodes, 场景字数维护)
│   ├── score/                  # 乐谱管理 + 调起本机 MuseScore (provide 乐谱文件服务)
│   ├── floating_song/          # 游离歌曲 (唱词/对白/重唱, 与正文互转; 仅音乐剧, 不进回收站)
│   ├── recycle/                # 回收站 (软删除聚合/恢复/清理)
│   ├── export/                 # TXT / Word (.docx) 导出，provide 导出路径解析
│   ├── json_transfer/          # 整项目 JSON 导出/导入 (不含回收站)，依赖 export 插件
│   └── backup/                 # DB 备份 + 恢复
├── templates/
│   └── index.html              # 前端 SPA (三栏布局 + 插件前端引导器)
├── static/
│   ├── css/
│   │   ├── main.css            # 全局样式 + 布局 + 卡片编辑器样式
│   │   └── themes.css          # 三套主题变量 (light/dark/warm)
│   └── js/
│       ├── api.js              # REST API 封装层 (fetch)
│       ├── app.js              # 应用入口 + 模式切换 + 工具栏 + 备份对话框
│       ├── state.js            # 前端状态管理 + 事件系统
│       ├── shortcuts.js        # 可自定义快捷键系统
│       ├── utils/
│       │   ├── word-count.js   # 中文字数统计
│       │   └── debounce.js     # 输入防抖
│       ├── core/
│       │   └── nw.js               # NW 命名空间 (插件挂载点 + 扩展点注册表)
│       └── components/             # 未迁移的剧本模式组件（阶段 3 随 script/floating_song/score 迁出）
│           ├── floating-song-editor.js # 游离歌曲编辑器
│           └── modal.js                # 通用弹窗
├── installer.nsi                # NSIS 安装包脚本
├── novel-writer.spec            # PyInstaller 单目录打包配置
├── novel-writer-onefile.spec    # PyInstaller 单文件打包配置 (可选)
├── novel-writer-mac.spec        # PyInstaller macOS .app 打包配置
├── .github/workflows/
│   └── build-mac.yml            # macOS CI 构建 (DMG 产物)
├── version_info.txt             # exe 版本信息资源
├── icon.ico                     # 应用图标 (多尺寸)
├── tools/                       # NSIS 工具链
├── tests/
│   └── run_conformance.py       # 插件协议符合性测试
├── debug_api_test.py            # API 全流程调试脚本
├── pyproject.toml               # uv 项目配置
├── uv.lock                      # 依赖锁定
├── dist/                        # 打包交付产物 (setup.exe / portable.zip)
├── docs/                        # 新手教程 + 插件化架构/计划/协议文档
├── LICENSE                      # GPLv3
└── README.md
```

## 数据存储

- 数据库文件位于系统标准用户数据目录（首次启动自动创建，旧版主目录数据库自动迁移）：
  - Windows: `%APPDATA%/novel-writer/data.db`
  - macOS: `~/Library/Application Support/novel-writer/data.db`
  - Linux: `~/.novel-writer/data.db`
- 22 张表：projects, volumes, chapters, drafts, outlines, characters, character_fields, character_appearances, world_settings, inspirations, tags, entity_tags, app_config, script_config, acts, scenes, script_elements（仅回滚底牌，不再读写）, scene_characters, element_characters, floating_songs, floating_lyrics, graph_nodes
- 版本化迁移 (v1→v5)，首次启动自动建表，老库自动升级

## 许可证

GNU General Public License v3.0 or later (GPL-3.0-or-later)

因集成 MuseScore（GPLv3 许可），本项目自该版本起改用 GPLv3 发布。完整许可证文本见 [LICENSE](LICENSE)。
