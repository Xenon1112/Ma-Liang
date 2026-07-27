# 小说写作助手 — 打包发布 Todo List

> 将 Flask 应用分别封装为 Windows 11 和 macOS 26+ 可独立运行的桌面程序。

---

## 一、通用准备

- [x] **1.1 启动行为改造**
  - [x] app 启动后自动打开浏览器到 `http://localhost:5200`
  - [x] 加命令行参数 `--no-browser` 禁止自动打开
  - [x] 窗口标题/icon 与最终产品名一致（标题「小说写作助手 v1.0.0」+ favicon）
  - [x] 数据库文件放到系统标准用户数据目录：
    - Windows: `%APPDATA%/novel-writer/data.db`（含旧版主目录数据库自动迁移）
    - macOS: `~/Library/Application Support/novel-writer/data.db`
  - [x] 首次启动时创建用户数据目录

- [x] **1.2 端口冲突处理**
  - [x] 默认端口 5200，若被占用自动尝试 5201、5202...
  - [x] 或允许用户通过 `--port` 指定

- [x] **1.3 日志与错误处理**
  - [x] 异常写入日志文件而非仅 stdout（`%APPDATA%/novel-writer/logs/app.log`）
  - [x] 打包后 Flask debug 模式关闭（默认关闭，需 `--debug` 显式开启）
  - [x] 友好错误页面（404/500 HTML 错误页；数据库损坏时控制台+日志明确提示）

- [x] **1.4 版本号注入**
  - [x] pyproject.toml 中的 version 注入到应用标题/关于对话框（`_version.py` + `importlib.metadata`）
  - [x] 在设置面板或关于页面显示版本号（工具栏标题显示「小说写作助手 v1.0.0」，`/api/version` 接口）

---

## 二、Windows 11 打包

- [x] **2.1 PyInstaller 方案**
  - [x] 安装 PyInstaller：`uv add --dev pyinstaller`
  - [x] 编写 `.spec` 文件：
    - 入口脚本 `app.py`
    - 收集 `templates/`、`static/` 目录
    - 隐藏导入（Flask、docx、sqlite3、re 等）
    - 排除不需要的模块减小体积（tkinter/matplotlib/numpy/pandas/PIL 等）
  - [x] 生成单目录版本（`--onedir`）：启动快，升级方便（已验证 exe 正常运行）
  - [x] 可选：生成单文件版本（`--onefile`）：spec 已就绪 `novel-writer-onefile.spec`（未构建，可选）

- [x] **2.2 安装包制作**
  - [x] NSIS 安装包脚本（`installer.nsi`）：
    - 安装目录选择
    - 开始菜单快捷方式
    - 桌面快捷方式（可选）
    - 卸载程序（卸载时询问是否删除用户数据）
    - 注册表写入（仅用于卸载列表 + App Paths）
  - [ ] 或使用 `uv` 的 `--installer` 模式 + WiX Toolset 生成 .msi（未采用，NSIS 已满足）

- [x] **2.3 Windows 11 特定适配**
  - [x] 应用图标 .ico（多尺寸：16/32/48/256）
  - [x] 窗口/任务栏图标正常显示（exe 图标 + 网页 favicon）
  - [ ] 测试 Windows 11 各版本（22H2+）（需在对应环境实测）
  - [ ] 确认不触发 Windows Defender 误报（PyInstaller 常见问题）（需在干净环境实测）
  - [ ] 如有误报：提交 Microsoft Security Intelligence

- [x] **2.4 交付物**
  - [x] `novel-writer-setup.exe`（NSIS 安装包，推荐）→ `dist/novel-writer-setup.exe`（约 17 MB）
  - [x] `novel-writer-portable.zip`（绿色免安装版）→ `dist/novel-writer-portable.zip`（约 17 MB）
  - [x] 安装/使用说明（中文）→ `dist/安装使用说明.md`

---

## 三、macOS 26+ 打包

- [ ] **3.1 PyInstaller 方案**
  - [x] `.spec` 文件适配 macOS（`novel-writer-mac.spec` 已就绪，CI 未构建验证）：
    - `icon.icns` 图标（由 CI 用 sips/iconutil 从 static/icon-256.png 生成）
    - `Info.plist` 配置（Bundle name, version, LSMinimumSystemVersion 26.0）
  - [x] 生成 `.app` bundle（GitHub Actions `.github/workflows/build-mac.yml` 已跑通，Build macOS #1 成功）
  - [ ] 测试 arm64（Apple Silicon）原生运行（dmg 已发出，待真机实测）

- [ ] **3.2 代码签名与公证（macOS 26 严格要求）**
  - [ ] Apple Developer 账号（$99/年，个人即可）
  - [ ] 创建 Developer ID Application 证书
  - [ ] `codesign` 签名 .app bundle 内所有可执行文件和库
  - [ ] `notarytool submit` 提交 Apple 公证
  - [ ] 公证通过后 stapler 绑定票据
  - [x] 若无法获取签名证书：
    - [x] 提供手动绕过 Gatekeeper 的说明（系统设置 → 隐私与安全性 → 仍要打开；或 xattr 去隔离，见 `dist/安装使用说明-mac.md`）
    - [ ] 或使用 Homebrew Cask 分发

- [x] **3.3 DMG 制作**
  - [x] `hdiutil` 创建 .dmg（CI 已验证，产物「马良-macOS」17.9 MB）
  - [x] dmg 背景图 + Applications 快捷方式（拖拽安装）（已含 Applications 符号链接；背景图未做）
  - [ ] 窗口大小和图标位置预设

- [ ] **3.4 macOS 26 特定适配**
  - [ ] 确认与 macOS 26 新权限模型兼容（如需要本地网络权限弹窗）
  - [ ] Finder 中显示正确的应用名（非 python/app）
  - [ ] 菜单栏应用名显示正确
  - [ ] 测试 macOS 15 + 26 双版本兼容

- [ ] **3.5 交付物**
  - [ ] `马良-macOS.dmg`（未签名，附 Gatekeeper 绕过说明）
  - [ ] 或 `novel-writer.app.zip`（解压即用）
  - [x] 安装说明（中文，含首次打开绕过 Gatekeeper 的步骤）→ `dist/安装使用说明-mac.md`

---

## 四、可选优化

- [ ] **4.1 自动更新**
  - [ ] 启动时检查 GitHub/Gitee Release 中的最新版本
  - [ ] 下载更新包并提示用户安装（或自动替换）
  - [ ] 版本号靠 `pyproject.toml` 中的 `version` 字段驱动

- [x] **4.2 应用图标**
  - [x] 设计统一的 .ico / .icns / .png 图标（已生成 .ico + 256px .png；.icns 待 macOS 打包时生成）
  - [x] 不同尺寸适配（任务栏、Dock、桌面、关于页）

- [ ] **4.3 多语言支持预留**
  - [ ] 提取所有 UI 文案到单独的 i18n 文件
  - [ ] 当前仅中文，预留英文接口

- [ ] **4.4 CI/CD 自动构建**
  - [ ] GitHub Actions：push tag → 自动构建 Win/Mac 包
  - [ ] 构建产物自动上传到 Release

---

## 五、自测清单

- [ ] **Windows 11**
  - [ ] 全新机器安装 → 启动 → 新建项目 → 写作 → 保存 → 导出 → 正常退出（打包版已在开发机验证启动与 API；全新机器待实测）
  - [ ] 重新打开 → 项目列表存在 → 内容完整
  - [x] 卸载 → 用户数据目录保留（或询问是否删除）（NSIS 卸载流程已实现）
  - [ ] 非管理员账户下运行正常（绿色版无需管理员；安装包需管理员安装）
  - [ ] 路径含中文/空格时运行正常

- [ ] **macOS 26**
  - [ ] 首次打开 Gatekeeper 提示 → 处理后正常运行
  - [ ] 新建项目 → 剧本模式 → 卡片编辑器 → 唱词功能完整
  - [ ] 退出 → 重新打开 → 数据完整
  - [ ] 拖入 Applications 文件夹后运行正常
  - [ ] Apple Silicon (arm64) 原生运行（非 Rosetta）
  - [ ] 本地网络权限弹窗不影响使用
