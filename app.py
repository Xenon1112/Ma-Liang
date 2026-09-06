"""小说写作助手 - API Server（miniframe，纯标准库，替代 Flask）"""
import os
import sys
import json
import argparse
import html
import logging
import socket
import threading
import webbrowser
from pathlib import Path
from core.httpd import Flask, request, jsonify, send_from_directory, req_json, snake_json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _version import get_version
from core.database import init_db, get_db_path, get_user_data_dir, soft_delete, get_conn

# PyInstaller 打包后资源位于 sys._MEIPASS；开发时为项目根目录
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
from core.config import get_config, set_config
from services.script_service import (
    list_acts, get_act, create_act, update_act, reorder_acts,
    list_scenes, get_scene, create_scene, update_scene, reorder_scenes, set_scene_characters,
    list_elements, get_element, create_element, update_element, delete_element, reorder_elements, move_element,
)
from services.floating_song_service import (
    list_floating_songs, create_floating_song, update_floating_song, delete_floating_song,
    add_lyric, update_lyric, delete_lyric, move_to_scene, move_to_floating,
)
from services.score_service import (
    get_score_info, open_score, delete_score, detect_musescore_path, get_musescore_path,
)
from core import plugin_manager

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static", template_folder=TEMPLATES_DIR)

APP_TITLE = "马良"
DEFAULT_PORT = 5200


# ====== 日志 ======

def setup_logging(debug=False):
    """异常写入日志文件（用户数据目录/logs/app.log），同时输出到控制台"""
    log_dir = get_user_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    # miniframe 的请求日志也走同一配置
    logging.getLogger("miniframe").setLevel(logging.WARNING if not debug else logging.DEBUG)


# ====== 友好错误页面 ======

def _error_page(title, detail):
    # detail 可能含用户输入（请求路径）或异常信息，插入 HTML 前需转义防 XSS
    detail = html.escape(str(detail))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>{title} - {APP_TITLE}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:80px auto;padding:0 20px;color:#333}}
h1{{color:#c0392b}}pre{{background:#f5f5f5;padding:12px;border-radius:6px;overflow:auto;font-size:13px}}</style>
</head><body>
<h1>{title}</h1>
<p>很抱歉，{APP_TITLE}遇到了问题。您可以尝试刷新页面；若问题持续，请查看日志文件或联系开发者。</p>
<pre>{detail}</pre>
<p><a href="/">返回首页</a></p>
</body></html>"""


@app.errorhandler(404)
def error_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return _error_page("页面不存在 (404)", request.path), 404


@app.errorhandler(500)
def error_500(e):
    logging.exception("未处理的服务器异常")
    detail = str(getattr(e, "original_exception", e))
    if request.path.startswith("/api/"):
        return jsonify({"error": "internal server error", "detail": detail}), 500
    return _error_page("服务器内部错误 (500)", detail), 500


@app.errorhandler(ValueError)
def error_value(e):
    # service 层抛出的参数/状态校验错误统一按 400 返回，消息可展示给用户
    return jsonify({"error": str(e)}), 400


# ====== 前端页面 ======

@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(STATIC_DIR, "favicon.ico")


# ====== 版本信息 ======

@app.route("/api/version", methods=["GET"])
def api_version():
    version = get_version()
    return jsonify({
        "name": APP_TITLE,
        "version": version,
        # 0.x 版本自动标注内测渠道，升到 1.0 后自动消失
        "channel": "内测版" if version.startswith("0.") else "",
        "dbPath": get_db_path(),
    })


# ====== Config API ======

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(get_config())

@app.route("/api/config", methods=["PUT"])
def api_set_config():
    # 配置键保持 camelCase（与 DEFAULTS 及读取方一致），不能做 snake 转换
    set_config(req_json())
    return jsonify({"ok": True})


# ====== 退出 ======

@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    def _stop():
        # 先停 HTTP server，再关 webview 窗口（--browser 模式无窗口则跳过）
        app.shutdown()
        try:
            import webview
            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass
    # 延迟片刻，让本次响应先送达浏览器
    threading.Timer(0.5, _stop).start()
    return jsonify({"ok": True})


# ====== Script: Act API ======

@app.route("/api/acts", methods=["GET"])
def api_list_acts():
    return jsonify(list_acts(request.args.get("projectId", type=int)))

@app.route("/api/acts/<int:id>", methods=["GET"])
def api_get_act(id):
    a = get_act(id)
    return jsonify(a) if a else (jsonify({"error": "not found"}), 404)

@app.route("/api/acts", methods=["POST"])
def api_create_act():
    return jsonify(create_act(snake_json())), 201

@app.route("/api/acts/<int:id>", methods=["PUT"])
def api_update_act(id):
    return jsonify(update_act(id, snake_json()))

@app.route("/api/acts/<int:id>", methods=["DELETE"])
def api_delete_act(id):
    conn = get_conn()
    soft_delete(conn, "acts", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/acts/reorder", methods=["POST"])
def api_reorder_acts():
    data = req_json()
    reorder_acts(data["projectId"], data["orderedIds"])
    return jsonify({"ok": True})


# ====== Script: Scene API ======

@app.route("/api/scenes", methods=["GET"])
def api_list_scenes():
    return jsonify(list_scenes(request.args.get("actId", type=int)))

@app.route("/api/scenes/<int:id>", methods=["GET"])
def api_get_scene(id):
    s = get_scene(id)
    return jsonify(s) if s else (jsonify({"error": "not found"}), 404)

@app.route("/api/scenes", methods=["POST"])
def api_create_scene():
    return jsonify(create_scene(snake_json())), 201

@app.route("/api/scenes/<int:id>", methods=["PUT"])
def api_update_scene(id):
    return jsonify(update_scene(id, snake_json()))

@app.route("/api/scenes/<int:id>", methods=["DELETE"])
def api_delete_scene(id):
    conn = get_conn()
    soft_delete(conn, "scenes", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/scenes/reorder", methods=["POST"])
def api_reorder_scenes():
    data = req_json()
    reorder_scenes(data["actId"], data["orderedIds"])
    return jsonify({"ok": True})

@app.route("/api/scenes/<int:id>/characters", methods=["PUT"])
def api_set_scene_characters(id):
    set_scene_characters(id, req_json().get("characterIds", []))
    return jsonify({"ok": True})


# ====== Script: Element API ======

@app.route("/api/elements", methods=["GET"])
def api_list_elements():
    return jsonify(list_elements(request.args.get("sceneId", type=int)))

@app.route("/api/elements/<int:id>", methods=["GET"])
def api_get_element(id):
    e = get_element(id)
    return jsonify(e) if e else (jsonify({"error": "not found"}), 404)

@app.route("/api/elements", methods=["POST"])
def api_create_element():
    return jsonify(create_element(snake_json())), 201

@app.route("/api/elements/<int:id>", methods=["PUT"])
def api_update_element(id):
    return jsonify(update_element(id, snake_json()))

@app.route("/api/elements/<int:id>", methods=["DELETE"])
def api_delete_element(id):
    delete_element(id)
    return jsonify({"ok": True})

@app.route("/api/elements/reorder", methods=["POST"])
def api_reorder_elements():
    data = req_json()
    reorder_elements(data["sceneId"], data.get("parentId"), data["orderedIds"])
    return jsonify({"ok": True})

@app.route("/api/elements/<int:id>/move", methods=["POST"])
def api_move_element(id):
    data = req_json()
    move_element(id, data.get("parentId"))
    return jsonify({"ok": True})


# ====== Floating Song API（游离歌曲，仅音乐剧） ======

@app.route("/api/floating-songs", methods=["GET"])
def api_list_floating_songs():
    return jsonify(list_floating_songs(request.args.get("projectId", type=int)))

@app.route("/api/floating-songs", methods=["POST"])
def api_create_floating_song():
    return jsonify(create_floating_song(snake_json())), 201

@app.route("/api/floating-songs/<int:id>", methods=["PUT"])
def api_update_floating_song(id):
    return jsonify(update_floating_song(id, snake_json()))

@app.route("/api/floating-songs/<int:id>", methods=["DELETE"])
def api_delete_floating_song(id):
    delete_floating_song(id)
    return jsonify({"ok": True})

@app.route("/api/floating-songs/<int:id>/lyrics", methods=["POST"])
def api_add_lyric(id):
    data = snake_json()
    data["song_id"] = id
    return jsonify(add_lyric(data)), 201

@app.route("/api/floating-lyrics/<int:id>", methods=["PUT"])
def api_update_lyric(id):
    return jsonify(update_lyric(id, snake_json()))

@app.route("/api/floating-lyrics/<int:id>", methods=["DELETE"])
def api_delete_lyric(id):
    delete_lyric(id)
    return jsonify({"ok": True})

@app.route("/api/floating-songs/<int:id>/move-to-scene", methods=["POST"])
def api_move_to_scene(id):
    return jsonify(move_to_scene(id, req_json().get("sceneId")))

@app.route("/api/elements/<int:id>/move-to-floating", methods=["POST"])
def api_move_to_floating(id):
    return jsonify(move_to_floating(id))


# ====== Score API（歌曲乐谱，调起本机 MuseScore 编辑） ======

def _score_target(data):
    """从参数中取 projectId/elementId/floatingSongId 三元组"""
    return (
        data.get("projectId") or data.get("project_id"),
        data.get("elementId") or data.get("element_id"),
        data.get("floatingSongId") or data.get("floating_song_id"),
    )

@app.route("/api/score", methods=["GET"])
def api_get_score():
    return jsonify(get_score_info(
        request.args.get("projectId", type=int),
        request.args.get("elementId", type=int),
        request.args.get("floatingSongId", type=int),
    ))

@app.route("/api/score/open", methods=["POST"])
def api_open_score():
    data = snake_json()
    project_id, element_id, floating_song_id = _score_target(data)
    created, path = open_score(project_id, element_id, floating_song_id, data.get("song_title"))
    return jsonify({"opened": True, "created": created, "path": path})

@app.route("/api/score/delete", methods=["POST"])
def api_delete_score():
    data = snake_json()
    project_id, element_id, floating_song_id = _score_target(data)
    delete_score(project_id, element_id, floating_song_id)
    return jsonify({"ok": True})

@app.route("/api/score/detect-path", methods=["GET"])
def api_detect_musescore_path():
    return jsonify({
        "detected": detect_musescore_path(),
        "current": get_musescore_path(),
    })


# ====== 插件加载 ======

def _load_plugins():
    """模块导入时即加载插件,使插件路由进入 app.routes(main() 中幂等重复调用)"""
    try:
        plugin_manager.discover()
        plugin_manager.load_all(app)
    except Exception:
        logging.getLogger("novel-writer").exception("插件加载流程异常")

_load_plugins()


# ====== 插件前端资源 ======

@app.route("/api/plugins/registry", methods=["GET"])
def api_plugins_registry():
    """前端引导脚本用的插件注册表(各插件 id/manifest/version/web 资源列表与状态)"""
    return jsonify(plugin_manager.registry())


@app.route("/plugins/<pid>/<path:filepath>", methods=["GET"])
def plugin_web_static(pid, filepath):
    """从插件目录 serve 前端资源;只服务已加载插件,目录穿越由 send_from_directory 拒绝(404)"""
    plugin_dir = plugin_manager.get_plugin_dir(pid)
    if not plugin_dir:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(plugin_dir, filepath)


# ====== Main ======

def find_free_port(start, max_tries=100):
    """从 start 开始找可用端口（5200 被占用则尝试 5201、5202...）"""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口 {start}~{start + max_tries - 1} 均被占用，请用 --port 指定其他端口")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="novel-writer", description=f"{APP_TITLE} v{get_version()}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--browser", action="store_true", help="用系统浏览器打开（调试用），不开内置窗口")
    parser.add_argument("--debug", action="store_true", help="开启 debug 模式（仅开发用）")
    parser.add_argument("--version", action="version", version=f"%(prog)s {get_version()}")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    setup_logging(debug=args.debug)
    log = logging.getLogger("novel-writer")

    try:
        init_db()
    except Exception as e:
        log.exception("数据库初始化失败：%s", get_db_path())
        print(f"\n[错误] 数据库初始化失败，数据库文件可能已损坏：{get_db_path()}")
        print("请备份后删除该文件再重新启动，或从应用内恢复备份。详见日志："
              f"{get_user_data_dir() / 'logs' / 'app.log'}")
        sys.exit(1)

    # 模块导入时已加载过插件(discover/load_all 均幂等,此处不会重复加载)
    plugin_manager.discover()
    plugin_manager.load_all(app)

    try:
        port = find_free_port(args.port)
    except RuntimeError as e:
        log.error(str(e))
        print(f"\n[错误] {e}")
        sys.exit(1)

    if port != args.port:
        print(f"端口 {args.port} 被占用，已切换到 {port}")
    log.info("数据库：%s", get_db_path())
    log.info("版本：%s", get_version())

    url = f"http://localhost:{port}"
    print(f"启动{APP_TITLE} v{get_version()}: {url}")

    if args.browser:
        # 调试模式：不开内置窗口，用系统浏览器访问
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=port, debug=args.debug)
        return

    # 默认：后台线程跑 HTTP server，主线程开 pywebview 内置窗口（窗口关闭即退出）
    server_thread = threading.Thread(
        target=app.run,
        kwargs={"host": "127.0.0.1", "port": port, "debug": args.debug},
        daemon=True,
    )
    server_thread.start()

    import webview
    webview.create_window(
        f"{APP_TITLE} v{get_version()}", url,
        width=1440, height=900, min_size=(1024, 700),
    )
    webview.start()  # 阻塞，窗口全部关闭后返回
    app.shutdown()

if __name__ == "__main__":
    main()
