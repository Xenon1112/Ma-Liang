"""小说写作助手 - Flask API Server"""
import os
import sys
import json
import argparse
import html
import logging
import signal
import socket
import threading
import webbrowser
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _version import get_version
from database import init_db, get_db_path, get_user_data_dir, soft_delete, get_conn

# PyInstaller 打包后资源位于 sys._MEIPASS；开发时为项目根目录
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
from services.project_service import list_projects, get_project, create_project, update_project, delete_project, get_stats
from services.chapter_service import (
    list_volumes, get_volume, create_volume, update_volume, reorder_volumes,
    list_chapters, get_chapter, create_chapter, update_chapter, reorder_chapters,
)
from services.draft_service import (
    get_current_draft, save_draft, list_drafts, get_draft, diff_drafts,
    rollback_draft, delete_draft, create_snapshot, clean_old_versions,
)
from services.outline_service import tree, get_outline, create_outline, update_outline, reorder_outlines, link_chapter
from services.character_service import (
    list_characters, get_character, create_character, update_character,
    add_field, update_field, remove_field, reorder_fields, set_appearances,
)
from services.world_setting_service import list_settings, get_setting, create_setting, update_setting
from services.inspiration_service import list_inspirations, get_inspiration, create_inspiration, update_inspiration
from services.export_service import export_txt, export_docx
from services.json_transfer_service import export_project_json, import_project_json
from services.backup_service import create_backup, restore_backup, get_backup_info
from services.recycle_service import list_recycle, restore, permanently_delete, clean_expired
from services.search_service import full_text
from services.config_service import get_config, set_config
from services.script_service import (
    list_acts, get_act, create_act, update_act, reorder_acts,
    list_scenes, get_scene, create_scene, update_scene, reorder_scenes, set_scene_characters,
    list_elements, get_element, create_element, update_element, delete_element, reorder_elements, move_element,
)

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
    # Flask/werkzeug 的请求日志也走同一配置
    logging.getLogger("werkzeug").setLevel(logging.WARNING if not debug else logging.DEBUG)


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


# ====== camelCase → snake_case 转换 ======
import re

def camel_to_snake(name):
    """projectId → project_id"""
    s = re.sub(r'([A-Z])', r'_\1', name)
    return s.lower().lstrip('_')

def convert_keys(obj):
    """递归转换 dict 的所有 key 从 camelCase 到 snake_case"""
    if isinstance(obj, dict):
        return {camel_to_snake(k): convert_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_keys(item) for item in obj]
    return obj

def req_json():
    """获取请求 JSON（保留原始 camelCase key）"""
    return request.get_json(silent=True) or {}

def snake_json():
    """获取请求 JSON（转换 key 为 snake_case，供 service 调用）"""
    return convert_keys(req_json())


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


# ====== Project API ======

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    return jsonify(list_projects())

@app.route("/api/projects/<int:id>", methods=["GET"])
def api_get_project(id):
    p = get_project(id)
    return jsonify(p) if p else (jsonify({"error": "not found"}), 404)

@app.route("/api/projects", methods=["POST"])
def api_create_project():
    return jsonify(create_project(snake_json())), 201

@app.route("/api/projects/<int:id>", methods=["PUT"])
def api_update_project(id):
    return jsonify(update_project(id, snake_json()))

@app.route("/api/projects/<int:id>", methods=["DELETE"])
def api_delete_project(id):
    delete_project(id)
    return jsonify({"ok": True})

@app.route("/api/projects/<int:id>/stats", methods=["GET"])
def api_get_stats(id):
    return jsonify(get_stats(id))

@app.route("/api/projects/import", methods=["POST"])
def api_import_project():
    # body 为导出文件解析后的完整 JSON 对象；格式错误由全局 ValueError 处理返回 400
    return jsonify({"project": import_project_json(req_json())}), 201


# ====== Volume API ======

@app.route("/api/volumes", methods=["GET"])
def api_list_volumes():
    project_id = request.args.get("projectId", type=int)
    return jsonify(list_volumes(project_id))

@app.route("/api/volumes/<int:id>", methods=["GET"])
def api_get_volume(id):
    v = get_volume(id)
    return jsonify(v) if v else (jsonify({"error": "not found"}), 404)

@app.route("/api/volumes", methods=["POST"])
def api_create_volume():
    return jsonify(create_volume(snake_json())), 201

@app.route("/api/volumes/<int:id>", methods=["PUT"])
def api_update_volume(id):
    return jsonify(update_volume(id, snake_json()))

@app.route("/api/volumes/<int:id>", methods=["DELETE"])
def api_delete_volume(id):
    conn = get_conn()
    soft_delete(conn, "volumes", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/volumes/reorder", methods=["POST"])
def api_reorder_volumes():
    data = req_json()
    reorder_volumes(data["projectId"], data["orderedIds"])
    return jsonify({"ok": True})

# Volume preface routes
@app.route("/api/volumes/<int:id>/preface", methods=["PUT"])
def api_update_preface(id):
    err = _draft_target_error(None, id)
    if err:
        return err
    data = req_json()
    update_volume(id, {"preface": data["content"]})
    return jsonify(save_draft({"volume_id": id, "content": data["content"], "version_tag": "auto"}))

@app.route("/api/volumes/<int:id>/preface-versions", methods=["GET"])
def api_preface_versions(id):
    return jsonify(list_drafts(volume_id=id))


# ====== Chapter API ======

@app.route("/api/chapters", methods=["GET"])
def api_list_chapters():
    volume_id = request.args.get("volumeId", type=int)
    return jsonify(list_chapters(volume_id))

@app.route("/api/chapters/<int:id>", methods=["GET"])
def api_get_chapter(id):
    c = get_chapter(id)
    return jsonify(c) if c else (jsonify({"error": "not found"}), 404)

@app.route("/api/chapters", methods=["POST"])
def api_create_chapter():
    return jsonify(create_chapter(snake_json())), 201

@app.route("/api/chapters/<int:id>", methods=["PUT"])
def api_update_chapter(id):
    return jsonify(update_chapter(id, snake_json()))

@app.route("/api/chapters/<int:id>", methods=["DELETE"])
def api_delete_chapter(id):
    conn = get_conn()
    soft_delete(conn, "chapters", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/chapters/reorder", methods=["POST"])
def api_reorder_chapters():
    data = req_json()
    reorder_chapters(data["volumeId"], data["orderedIds"])
    return jsonify({"ok": True})


# ====== Draft API ======

def _draft_target_error(chapter_id, volume_id):
    """目标章/卷不存在或已软删时返回错误响应，否则返回 None"""
    if chapter_id is not None and not get_chapter(chapter_id):
        return jsonify({"error": "章节不存在或已删除"}), 404
    if volume_id is not None and not get_volume(volume_id):
        return jsonify({"error": "卷不存在或已删除"}), 404
    return None

@app.route("/api/drafts/current", methods=["GET"])
def api_get_current_draft():
    ch = request.args.get("chapterId", type=int)
    vol = request.args.get("volumeId", type=int)
    d = get_current_draft(chapter_id=ch, volume_id=vol)
    return jsonify(d) if d else jsonify(None)

@app.route("/api/drafts", methods=["POST"])
def api_save_draft():
    data = snake_json()
    err = _draft_target_error(data.get("chapter_id"), data.get("volume_id"))
    if err:
        return err
    return jsonify(save_draft(data))

@app.route("/api/drafts/list", methods=["GET"])
def api_list_drafts():
    ch = request.args.get("chapterId", type=int)
    vol = request.args.get("volumeId", type=int)
    return jsonify(list_drafts(chapter_id=ch, volume_id=vol))

@app.route("/api/drafts/<int:id>", methods=["GET"])
def api_get_draft(id):
    return jsonify(get_draft(id))

@app.route("/api/drafts/diff", methods=["POST"])
def api_diff_drafts():
    data = req_json()
    return jsonify(diff_drafts(data["draftIdA"], data["draftIdB"]))

@app.route("/api/drafts/<int:id>/rollback", methods=["POST"])
def api_rollback_draft(id):
    return jsonify(rollback_draft(id))

@app.route("/api/drafts/<int:id>", methods=["DELETE"])
def api_delete_draft(id):
    delete_draft(id)
    return jsonify({"ok": True})

@app.route("/api/drafts/snapshot", methods=["POST"])
def api_create_snapshot():
    return jsonify(create_snapshot(snake_json()))

@app.route("/api/drafts/clean", methods=["POST"])
def api_clean_versions():
    data = req_json()
    return jsonify({"count": clean_old_versions(
        chapter_id=data.get("chapterId"),
        volume_id=data.get("volumeId"),
        keep_count=data.get("keepCount", 50),
    )})


# ====== Outline API ======

@app.route("/api/outlines", methods=["GET"])
def api_outline_tree():
    project_id = request.args.get("projectId", type=int)
    return jsonify(tree(project_id))

@app.route("/api/outlines/<int:id>", methods=["GET"])
def api_get_outline(id):
    o = get_outline(id)
    return jsonify(o) if o else (jsonify({"error": "not found"}), 404)

@app.route("/api/outlines", methods=["POST"])
def api_create_outline():
    return jsonify(create_outline(snake_json())), 201

@app.route("/api/outlines/<int:id>", methods=["PUT"])
def api_update_outline(id):
    return jsonify(update_outline(id, snake_json()))

@app.route("/api/outlines/<int:id>", methods=["DELETE"])
def api_delete_outline(id):
    conn = get_conn()
    # 有未删除的子节点时拒绝删除，避免子节点成为不可见孤儿
    child = conn.execute(
        "SELECT 1 FROM outlines WHERE parent_id = ? AND deleted_at IS NULL LIMIT 1", (id,)
    ).fetchone()
    if child:
        conn.close()
        return jsonify({"error": "请先删除子节点"}), 400
    soft_delete(conn, "outlines", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/outlines/reorder", methods=["POST"])
def api_reorder_outlines():
    data = req_json()
    reorder_outlines(data["projectId"], data["orderedIds"])
    return jsonify({"ok": True})

@app.route("/api/outlines/<int:id>/link", methods=["POST"])
def api_link_chapter(id):
    return jsonify(link_chapter(id, req_json().get("chapterId")))


# ====== Character API ======

@app.route("/api/characters", methods=["GET"])
def api_list_characters():
    project_id = request.args.get("projectId", type=int)
    return jsonify(list_characters(project_id))

@app.route("/api/characters/<int:id>", methods=["GET"])
def api_get_character(id):
    c = get_character(id)
    return jsonify(c) if c else (jsonify({"error": "not found"}), 404)

@app.route("/api/characters", methods=["POST"])
def api_create_character():
    return jsonify(create_character(snake_json())), 201

@app.route("/api/characters/<int:id>", methods=["PUT"])
def api_update_character(id):
    return jsonify(update_character(id, snake_json()))

@app.route("/api/characters/<int:id>", methods=["DELETE"])
def api_delete_character(id):
    conn = get_conn()
    soft_delete(conn, "characters", id)
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/characters/fields", methods=["POST"])
def api_add_field():
    return jsonify(add_field(snake_json())), 201

@app.route("/api/characters/fields/<int:id>", methods=["PUT"])
def api_update_field(id):
    return jsonify(update_field(id, snake_json()))

@app.route("/api/characters/fields/<int:id>", methods=["DELETE"])
def api_remove_field(id):
    remove_field(id)
    return jsonify({"ok": True})

@app.route("/api/characters/<int:id>/fields/reorder", methods=["POST"])
def api_reorder_fields(id):
    reorder_fields(id, req_json()["orderedIds"])
    return jsonify({"ok": True})

@app.route("/api/characters/<int:id>/appearances", methods=["PUT"])
def api_set_appearances(id):
    body = request.get_json(silent=True)
    # 兼容两种请求体：直接数组 [{chapterId, note}, ...] 或 {"appearances": [...]}
    if isinstance(body, list):
        appearances = convert_keys(body)
    else:
        appearances = convert_keys(body or {}).get("appearances", [])
    set_appearances(id, appearances)
    return jsonify({"ok": True})


# ====== World Setting API ======

@app.route("/api/world-settings", methods=["GET"])
def api_list_settings():
    project_id = request.args.get("projectId", type=int)
    category = request.args.get("category")
    return jsonify(list_settings(project_id, category))

@app.route("/api/world-settings/<int:id>", methods=["GET"])
def api_get_setting(id):
    s = get_setting(id)
    return jsonify(s) if s else (jsonify({"error": "not found"}), 404)

@app.route("/api/world-settings", methods=["POST"])
def api_create_setting():
    return jsonify(create_setting(snake_json())), 201

@app.route("/api/world-settings/<int:id>", methods=["PUT"])
def api_update_setting(id):
    return jsonify(update_setting(id, snake_json()))

@app.route("/api/world-settings/<int:id>", methods=["DELETE"])
def api_delete_setting(id):
    conn = get_conn()
    soft_delete(conn, "world_settings", id)
    conn.close()
    return jsonify({"ok": True})


# ====== Inspiration API ======

@app.route("/api/inspirations", methods=["GET"])
def api_list_inspirations():
    project_id = request.args.get("projectId", type=int)
    return jsonify(list_inspirations(project_id, request.args.get("type"), request.args.get("tag")))

@app.route("/api/inspirations/<int:id>", methods=["GET"])
def api_get_inspiration(id):
    i = get_inspiration(id)
    return jsonify(i) if i else (jsonify({"error": "not found"}), 404)

@app.route("/api/inspirations", methods=["POST"])
def api_create_inspiration():
    return jsonify(create_inspiration(snake_json())), 201

@app.route("/api/inspirations/<int:id>", methods=["PUT"])
def api_update_inspiration(id):
    return jsonify(update_inspiration(id, snake_json()))

@app.route("/api/inspirations/<int:id>", methods=["DELETE"])
def api_delete_inspiration(id):
    conn = get_conn()
    soft_delete(conn, "inspirations", id)
    conn.close()
    return jsonify({"ok": True})


# ====== Export API ======

@app.route("/api/export/txt", methods=["POST"])
def api_export_txt():
    data = req_json()
    try:
        return jsonify(export_txt(
            chapter_id=data.get("chapterId"),
            project_id=data.get("projectId"),
            output_path=data.get("outputPath", ""),
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/export/docx", methods=["POST"])
def api_export_docx():
    data = req_json()
    try:
        return jsonify(export_docx(
            chapter_id=data.get("chapterId"),
            project_id=data.get("projectId"),
            output_path=data.get("outputPath", ""),
            options=data.get("options"),
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/export/json", methods=["POST"])
def api_export_json():
    data = req_json()
    try:
        return jsonify(export_project_json(
            project_id=data.get("projectId"),
            output_path=data.get("outputPath", ""),
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ====== Backup API ======

@app.route("/api/backup", methods=["POST"])
def api_create_backup():
    return jsonify(create_backup(req_json().get("backupPath")))

@app.route("/api/backup/info", methods=["POST"])
def api_backup_info():
    return jsonify(get_backup_info(req_json()["backupFilePath"]))

@app.route("/api/backup/restore", methods=["POST"])
def api_restore_backup():
    return jsonify(restore_backup(req_json()["backupFilePath"]))

@app.route("/api/backup/db-path", methods=["GET"])
def api_db_path():
    return jsonify({"dbPath": get_db_path()})


# ====== Recycle API ======

@app.route("/api/recycle", methods=["GET"])
def api_list_recycle():
    return jsonify(list_recycle())

@app.route("/api/recycle/restore", methods=["POST"])
def api_restore_recycle():
    data = req_json()
    restore(data["entityType"], data["entityId"])
    return jsonify({"ok": True})

@app.route("/api/recycle/permanent-delete", methods=["POST"])
def api_permanent_delete():
    data = req_json()
    permanently_delete(data["entityType"], data["entityId"])
    return jsonify({"ok": True})

@app.route("/api/recycle/clean", methods=["POST"])
def api_clean_expired():
    return jsonify({"count": clean_expired()})


# ====== Search API ======

@app.route("/api/search", methods=["GET"])
def api_search():
    return jsonify(full_text(
        request.args.get("projectId", type=int),
        request.args.get("keyword", ""),
        request.args.get("types", "").split(",") if request.args.get("types") else None,
    ))


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
        try:
            # 触发 KeyboardInterrupt，让 werkzeug 正常退出服务循环
            signal.raise_signal(signal.SIGINT)
        except Exception:
            os._exit(0)
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
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--debug", action="store_true", help="开启 Flask debug 模式（仅开发用）")
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
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"启动{APP_TITLE} v{get_version()}: {url}")
    app.run(host="127.0.0.1", port=port, debug=args.debug)

if __name__ == "__main__":
    main()
