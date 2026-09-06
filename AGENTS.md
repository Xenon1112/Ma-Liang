# AGENTS.md

## Python 环境:一律走 uv

本项目由 uv 管理(`pyproject.toml` + `uv.lock`)。**所有 Python 命令必须通过 uv 执行,禁止直接调用系统 `python` / `pip`**:

- 运行应用:`uv run python app.py`(桌面窗口)或 `uv run python app.py --browser`(浏览器模式)
- 插件协议符合性测试:`uv run python tests/run_conformance.py`
- 打包:`uv run pyinstaller novel-writer.spec`
- 加依赖:`uv add <pkg>`;开发依赖:`uv add --dev <pkg>`

原因:`uv run` 执行前会按 lockfile 自动同步 `.venv`;系统 Python 可能与项目环境不一致(本机全局 `python` 命令甚至是坏的)。

## 架构要点

- 正在进行「一切皆插件」重构,设计见 `docs/插件化架构设计.md`,执行计划见 `docs/插件化改造计划书.md`,插件协议见 `docs/插件协议-v0草案.md`(未冻结);
- `core/` 是业务无关内核;`plugins/` 是已迁移的内置插件;`services/` 是待迁移的业务模块;`app.py` 的路由将随迁移逐步清空;
- 改动内核后必须跑 `tests/run_conformance.py`;
- 提交信息使用中文,格式 `type: 描述`(参照 git log)。
