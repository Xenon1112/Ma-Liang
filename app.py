"""小说写作助手 - Flask API Server"""
import os
import sys
import json
from flask import Flask, request, jsonify, send_from_directory

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_db_path, soft_delete, get_conn
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
from services.backup_service import create_backup, restore_backup, get_backup_info
from services.recycle_service import list_recycle, restore, permanently_delete, clean_expired
from services.search_service import full_text
from services.config_service import get_config, set_config

app = Flask(__name__, static_folder="static", template_folder="templates")


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
    return send_from_directory("templates", "index.html")


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

@app.route("/api/drafts/current", methods=["GET"])
def api_get_current_draft():
    ch = request.args.get("chapterId", type=int)
    vol = request.args.get("volumeId", type=int)
    d = get_current_draft(chapter_id=ch, volume_id=vol)
    return jsonify(d) if d else jsonify(None)

@app.route("/api/drafts", methods=["POST"])
def api_save_draft():
    return jsonify(save_draft(snake_json()))

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
    set_appearances(id, snake_json())
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
    return jsonify(export_txt(
        chapter_id=data.get("chapterId"),
        project_id=data.get("projectId"),
        output_path=data["outputPath"],
    ))

@app.route("/api/export/docx", methods=["POST"])
def api_export_docx():
    data = req_json()
    return jsonify(export_docx(
        chapter_id=data.get("chapterId"),
        project_id=data.get("projectId"),
        output_path=data["outputPath"],
        options=data.get("options"),
    ))


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
    set_config(snake_json())
    return jsonify({"ok": True})


# ====== Main ======

def main():
    init_db()
    print(f"Database: {get_db_path()}")
    print("启动小说写作助手: http://localhost:5200")
    app.run(host="127.0.0.1", port=5200, debug=True)

if __name__ == "__main__":
    main()
