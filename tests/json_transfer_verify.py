"""json_transfer 声明式改造的验证脚本(纯标准库,uv run python tests/json_transfer_verify.py ...)

子命令:
- routes                          加载全部插件,打印路由总数(基线 113)
- projects <db>                   列出库里的项目 id/标题
- seed <workdir>                  在 workdir 造全类型种子库 seed.db(含剧本/游离歌曲/乐谱/软删除)
- export <db> <pid> <out.json> [--deleted] [--appdata DIR]
                                  用当前代码导出指定项目为 JSON(改造前后各跑一次做 diff)
- roundtrip <workdir>             种子库上跑 导出→导入→再导出→归一化对比 回环断言

环境隔离:seed/roundtrip 把 APPDATA 指到 workdir,乐谱文件与插件用户目录都落在临时目录;
export 真实库副本时传 --appdata 指向真实 %APPDATA% 以读到乐谱文件。
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _setup(db_path, appdata=None):
    """在任何 core/services 导入前固定 APPDATA 与 db 路径"""
    if appdata:
        os.environ["APPDATA"] = str(Path(appdata).resolve())
    sys.path.insert(0, str(ROOT))
    from core import database
    database.set_db_path(str(Path(db_path).resolve()))
    return database


def _load_jt():
    """经 app 模块加载全部插件,取回 json_transfer 后端模块句柄"""
    import app as _app  # noqa: F401  (导入即 discover+load_all)
    mod = sys.modules.get("nw_plugin_json_transfer")
    if mod is None or getattr(mod, "_api", None) is None:
        raise RuntimeError("json_transfer 插件未加载成功")
    return mod, _app


def cmd_routes(_args):
    tmp = Path(ROOT) / "tests" / ".verify" / "routes"
    tmp.mkdir(parents=True, exist_ok=True)
    _setup(tmp / "routes.db", appdata=tmp)
    _, app_mod = _load_jt()
    print(len(app_mod.app.routes))


def cmd_projects(args):
    db = _setup(args.db)
    conn = db.get_conn()
    for r in conn.execute("SELECT id, title, project_type, deleted_at FROM projects ORDER BY id"):
        print(r["id"], r["title"], r["project_type"], "deleted" if r["deleted_at"] else "")
    conn.close()


def cmd_seed(args):
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    db_file = workdir / "seed.db"
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_file) + suffix)
        if p.exists():
            p.unlink()
    db = _setup(db_file, appdata=workdir)
    db.init_db()
    conn = db.get_conn()
    c = conn
    # 项目 1:小说
    c.execute("INSERT INTO projects (title, subtitle, author, description, status) VALUES ('小说项目','副','作者','描述','writing')")
    c.execute("INSERT INTO volumes (project_id, title, preface, sort_order) VALUES (1,'卷一','卷首语',1)")
    c.execute("INSERT INTO volumes (project_id, title, sort_order, deleted_at) VALUES (1,'废卷',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order, status, word_count) VALUES (1,1,'第一章',1,'done',1000)")
    c.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order, deleted_at) VALUES (1,1,'废章',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO chapters (volume_id, project_id, title, sort_order) VALUES (2,1,'废卷的章',1)")
    c.execute("INSERT INTO drafts (chapter_id, content, version_number, word_count, change_note, version_tag, is_current, content_hash) VALUES (1,'正文v1',1,100,'','auto',0,'h1')")
    c.execute("INSERT INTO drafts (chapter_id, content, version_number, word_count, is_current, content_hash) VALUES (1,'正文v2',2,120,1,'h2')")
    c.execute("INSERT INTO drafts (volume_id, content, version_number, is_current) VALUES (1,'卷首语草稿',1,1)")
    c.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (2,'废章草稿',1,1)")
    c.execute("INSERT INTO drafts (chapter_id, content, version_number, is_current) VALUES (3,'废卷章草稿',1,1)")
    c.execute("INSERT INTO outlines (project_id, title, content, sort_order, node_type) VALUES (1,'总纲','x',1,'chapter_outline')")
    c.execute("INSERT INTO outlines (project_id, parent_id, title, sort_order) VALUES (1,1,'子纲',1)")
    c.execute("INSERT INTO outlines (project_id, title, sort_order, linked_chapter_id) VALUES (1,'挂章纲',2,1)")
    c.execute("INSERT INTO outlines (project_id, title, sort_order, linked_chapter_id) VALUES (1,'挂废章纲',3,2)")
    c.execute("INSERT INTO outlines (project_id, title, sort_order, deleted_at) VALUES (1,'废纲',4,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO outlines (project_id, parent_id, title, sort_order) VALUES (1,5,'废纲子',5)")
    c.execute("INSERT INTO characters (project_id, name, aliases, sort_order) VALUES (1,'张三','小三',1)")
    c.execute("INSERT INTO characters (project_id, name, sort_order, deleted_at) VALUES (1,'废人',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO character_fields (character_id, field_name, content, sort_order) VALUES (1,'外貌','高',1)")
    c.execute("INSERT INTO character_fields (character_id, field_name, content) VALUES (2,'外貌','废')")
    c.execute("INSERT INTO character_appearances (character_id, chapter_id, note) VALUES (1,1,'首次登场')")
    c.execute("INSERT INTO character_appearances (character_id, chapter_id) VALUES (1,2)")
    c.execute("INSERT INTO character_appearances (character_id, chapter_id) VALUES (2,1)")
    c.execute("INSERT INTO world_settings (project_id, category, title, content, sort_order) VALUES (1,'地理','大陆','x',1)")
    c.execute("INSERT INTO world_settings (project_id, category, title, deleted_at) VALUES (1,'地理','废设定','2026-01-01 00:00:00')")
    c.execute("INSERT INTO inspirations (project_id, type, title, content, source, tags, linked_chapter_id) VALUES (1,'inspiration','灵感1','c','s','t',1)")
    c.execute("INSERT INTO inspirations (project_id, title, linked_chapter_id) VALUES (1,'灵感废章',2)")
    c.execute("INSERT INTO inspirations (project_id, title, deleted_at) VALUES (1,'废灵感','2026-01-01 00:00:00')")
    # 项目 2:音乐剧(剧本结构 + 游离歌曲 + 乐谱)
    c.execute("INSERT INTO projects (title, project_type) VALUES ('音乐剧项目','musical')")
    c.execute("INSERT INTO script_config (project_id, script_type) VALUES (2,'musical')")
    c.execute("INSERT INTO characters (project_id, name, sort_order) VALUES (2,'歌者甲',1)")          # id 3
    c.execute("INSERT INTO characters (project_id, name, sort_order, deleted_at) VALUES (2,'废歌者',2,'2026-01-01 00:00:00')")  # id 4
    c.execute("INSERT INTO acts (project_id, title, sort_order) VALUES (2,'第一幕',1)")
    c.execute("INSERT INTO acts (project_id, title, sort_order, deleted_at) VALUES (2,'废幕',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO scenes (act_id, project_id, title, setting, sort_order, status, word_count) VALUES (1,2,'开场','舞台',1,'done',50)")
    c.execute("INSERT INTO scenes (act_id, project_id, title, sort_order, deleted_at) VALUES (1,2,'废场',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO scenes (act_id, project_id, title, sort_order) VALUES (2,2,'废幕的场',1)")
    c.execute("INSERT INTO script_elements (scene_id, element_type, character_id, content, sort_order) VALUES (1,'dialogue',3,'台词',1)")
    c.execute("INSERT INTO script_elements (scene_id, element_type, content, song_title, sort_order, score_file) VALUES (1,'song','唱词','主题曲',2,'element_9001.mscz')")
    c.execute("INSERT INTO script_elements (scene_id, parent_id, element_type, content, sort_order) VALUES (1,2,'lyric','副歌',1)")
    c.execute("INSERT INTO script_elements (scene_id, element_type, content, sort_order, score_file) VALUES (1,'song','无谱歌',3,'missing.mscz')")
    c.execute("INSERT INTO script_elements (scene_id, element_type, character_id, content, sort_order) VALUES (1,'dialogue',4,'废人台词',4)")
    c.execute("INSERT INTO script_elements (scene_id, element_type, content, sort_order, deleted_at) VALUES (1,'action','废元素',5,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO script_elements (scene_id, parent_id, element_type, content, sort_order) VALUES (1,6,'action','废元素的子',6)")
    c.execute("INSERT INTO script_elements (scene_id, element_type, content) VALUES (2,'action','废场元素')")
    c.execute("INSERT INTO scene_characters (scene_id, character_id, note) VALUES (1,3,'主角')")
    c.execute("INSERT INTO scene_characters (scene_id, character_id) VALUES (1,4)")
    c.execute("INSERT INTO scene_characters (scene_id, character_id) VALUES (2,3)")
    c.execute("INSERT INTO element_characters (element_id, character_id, sort_order) VALUES (1,3,1)")
    c.execute("INSERT INTO element_characters (element_id, character_id) VALUES (3,3)")
    c.execute("INSERT INTO element_characters (element_id, character_id) VALUES (1,4)")
    c.execute("INSERT INTO element_characters (element_id, character_id) VALUES (6,3)")
    c.execute("INSERT INTO floating_songs (project_id, song_title, sort_order, score_file) VALUES (2,'主题歌',1,'floating_9001.mscz')")
    c.execute("INSERT INTO floating_songs (project_id, song_title, sort_order, deleted_at) VALUES (2,'废歌',2,'2026-01-01 00:00:00')")
    c.execute("INSERT INTO floating_songs (project_id, song_title, sort_order) VALUES (2,'无谱歌',3)")
    c.execute("INSERT INTO floating_lyrics (song_id, element_type, character_id, character_ids, content, sort_order) VALUES (1,'lyric',3,'[3]','第一句',1)")
    c.execute("INSERT INTO floating_lyrics (song_id, element_type, character_ids, content, sort_order) VALUES (1,'dialogue','[3, 4]','对白',2)")
    c.execute("INSERT INTO floating_lyrics (song_id, element_type, character_ids, content, sort_order) VALUES (1,'ensemble','[]','重唱容器',3)")
    c.execute("INSERT INTO floating_lyrics (song_id, element_type, parent_id, character_ids, content, sort_order) VALUES (1,'lyric',3,'[3]','重唱子句',1)")
    c.execute("INSERT INTO floating_lyrics (song_id, content, sort_order) VALUES (2,'废歌词',1)")
    conn.commit()
    conn.close()
    # 乐谱文件(APPDATA 已指向 workdir,落在临时目录);G3 起实现在 score 插件,加载插件后取用
    import app as _app  # noqa: F401  (导入即 discover+load_all,activate 注入 _api)
    score_mod = sys.modules.get("nw_plugin_score")
    if score_mod is None or getattr(score_mod, "_api", None) is None:
        raise RuntimeError("score 插件未加载成功")
    score_mod.write_score_file(2, "element_9001.mscz", b"fake-mscz-bytes")
    score_mod.write_score_file(2, "floating_9001.mscz", b"fake-floating-score")
    print(f"种子库已建: {db_file} (项目 1=小说, 2=音乐剧)")


def cmd_export(args):
    _setup(args.db, appdata=args.appdata)
    mod, _ = _load_jt()
    from core import database
    conn = database.get_conn()
    try:
        payload = mod._build_export_payload(conn, args.pid, include_deleted=args.deleted)
    finally:
        conn.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"已导出: {out} ({out.stat().st_size} bytes)")


# ====== 回环 ======

def _norm(obj, strip_title_suffix=False):
    """归一化:剥掉 id/外键/乐谱文件名等导入后必然变化的字段,只比业务内容"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "id" or k.endswith("_id") or k == "character_ids" or k == "score_file":
                continue
            if strip_title_suffix and k == "title" and isinstance(v, str):
                v = v.replace("（副本）", "")
            out[k] = _norm(v)
        return out
    if isinstance(obj, list):
        return [_norm(v) for v in obj]
    return obj


def _sorted_rows(rows):
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def _roundtrip_one(mod, database, pid, include_deleted, failures):
    tag = f"项目{pid} include_deleted={include_deleted}"
    conn = database.get_conn()
    try:
        src = mod._build_export_payload(conn, pid, include_deleted=include_deleted)
    finally:
        conn.close()
    new_proj = mod.import_project_json(copy.deepcopy(src))  # import 会就地改 payload(弹 score_b64),深拷贝隔离
    conn = database.get_conn()
    try:
        dst = mod._build_export_payload(conn, new_proj["id"], include_deleted=include_deleted)
    finally:
        conn.close()
    keys = list(src.keys())
    if list(dst.keys()) != keys:
        failures.append(f"{tag}: 副本导出键集合/顺序不一致 {keys} vs {list(dst.keys())}")
        print(f"[FAIL] {tag} 键顺序不一致")
        return
    for key in keys:
        a, b = src[key], dst[key]
        if isinstance(a, list):
            na = _sorted_rows([_norm(r) for r in a])
            nb = _sorted_rows([_norm(r) for r in b])
            ok = na == nb
            print(f"[{'PASS' if ok else 'FAIL'}] {tag} {key}: 行数 {len(a)} vs {len(b)}")
            if not ok:
                failures.append(f"{tag} {key}: 归一化内容不一致\n  源={json.dumps(na, ensure_ascii=False)[:400]}\n  副本={json.dumps(nb, ensure_ascii=False)[:400]}")
        else:  # project 根字典
            na, nb = _norm(a), _norm(b, strip_title_suffix=True)
            ok = na == nb
            print(f"[{'PASS' if ok else 'FAIL'}] {tag} {key}: 根信息一致={ok}")
            if not ok:
                failures.append(f"{tag} {key}: {na} vs {nb}")


def cmd_roundtrip(args):
    workdir = Path(args.workdir).resolve()
    ns = argparse.Namespace(workdir=str(workdir))
    cmd_seed(ns)
    _setup(workdir / "seed.db", appdata=workdir)
    mod, _ = _load_jt()
    from core import database
    failures = []
    _roundtrip_one(mod, database, 1, False, failures)
    _roundtrip_one(mod, database, 2, False, failures)
    _roundtrip_one(mod, database, 2, True, failures)
    if failures:
        print(f"\n{len(failures)} 项失败")
        for f in failures:
            print("-", f)
        sys.exit(1)
    print("\n回环全部通过")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("routes")
    p = sub.add_parser("projects"); p.add_argument("db")
    p = sub.add_parser("seed"); p.add_argument("workdir")
    p = sub.add_parser("export")
    p.add_argument("db"); p.add_argument("pid", type=int); p.add_argument("out")
    p.add_argument("--deleted", action="store_true")
    p.add_argument("--appdata", default=None)
    p = sub.add_parser("roundtrip"); p.add_argument("workdir")
    args = ap.parse_args()
    {"routes": cmd_routes, "projects": cmd_projects, "seed": cmd_seed,
     "export": cmd_export, "roundtrip": cmd_roundtrip}[args.cmd](args)


if __name__ == "__main__":
    main()
