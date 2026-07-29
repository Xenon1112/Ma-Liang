"""版本信息：构建/打包时由 pyproject.toml 同步"""
__version__ = "0.0.2"


def get_version():
    """优先读取已安装包的版本，回退到内置常量"""
    try:
        from importlib.metadata import version
        return version("novel-writer")
    except Exception:
        return __version__
