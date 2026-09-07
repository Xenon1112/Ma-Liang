"""整项目 JSON 导入导出插件:数据访问 + 路由注册(原 services/json_transfer_service.py 与 app.py JSON 导出路由迁移而来)

无专属表(SQL 层按表搬运 volumes/chapters/drafts 等业务表数据),故无 migrations 目录。

声明式搬运:导出/导入的主循环消费内核实体注册表(api.list_entities() 中 export=True
的实体,按 export_order 排序,被引用方必须排在前面),默认处理器按注册信息完成:
- 导出:表有 project_id 列则按项目过滤(有 deleted_at 列则按需排除回收站数据);
  无 project_id 的附属表(如 drafts/character_fields)按 fk/weak_fk 声明挂靠已导出的
  父实体行集。强外键 fk 指向已排除行时级联剔除该行,弱外键 weak_fk 悬空时置 NULL。
- 导入:自增主键重映射(旧id→新id 映射表),fk 列按目标实体的映射重写(非 NULL 但
  映射不到则整行跳过),weak_fk 列悬空置 NULL;weak_fk 指向自身实体时是自引用
  (如 outlines.parent_id),先置 NULL 插入再统一回写。
默认处理器表达不了的表,注册时可传 export_hook/import_hook,传了的实体跳过默认处理器:
- export_hook(conn, project_id, id_sets, include_deleted) -> {payload键: 行数组};
  若有下游实体引用本实体,钩子须把新 id 集合写入 id_sets[entity]。
- import_hook(conn, payload, id_maps, new_project_id) -> {旧id: 新id}(返回值存入
  id_maps[entity],供下游实体重映射)。

payload 键即表名;"project" 根键(单对象、导入时标题加副本后缀)是导出格式固有的根,
单独处理,不走默认处理器。

仍走定制代码路径的表(属于剧本/乐谱等未声明式化的部分):
- acts/scenes/scene_characters/element_characters/script_config(script 插件;
  剧作元素本体已迁入 graph_nodes,本插件把节点 payload 展开/组装回旧 script_elements
  行形状做导入导出,导出文件格式不变,旧导出文件仍可导入)
- floating_songs/floating_lyrics(floating_song 插件注册的 export_hook/import_hook,
  嵌套 lyrics 结构与 character_ids JSON 拼接,默认处理器表达不了;为保持导出文件键序
  逐字节不变,该实体 export=False 不进声明式主循环,由下方定制段在固定位置经
  _entity_hook 显式调用)
- 乐谱文件 base64 内嵌(score 插件,graph_nodes payload 的 score_file
  与 floating_songs 的 score_file 列)

两个跨插件边界:
- 导出文件路径解析复用 export 插件 provide 的 resolve_output_path,
  请求处理时通过 api.require("export") 取用,export 缺失返回 503;
- 对外 provide "json_transfer" 服务,project 插件的项目导入入口经 api.require 取用。
"""
import json
import base64

_api = None  # activate 时注入的 PluginAPI

EXPORT_APP = "novel-writer"
EXPORT_KIND = "project-export"
EXPORT_VERSION = 1


class ExportPluginUnavailable(Exception):
    """export 插件未加载,无法解析导出文件路径(路由层转 503)"""


def _resolve_output_path(output_path, ext, default_name):
    """路径解析由 export 插件 provide;请求处理时经 api.require("export") 取用"""
    export_svc = _api.require("export")
    if export_svc is None:
        raise ExportPluginUnavailable("export 插件未加载")
    return export_svc["resolve_output_path"](output_path, ext, default_name)


def _score_svc():
    """score 插件 provide 的乐谱文件服务;未加载返回 None,调用方按「乐谱文件丢失」降级"""
    return _api.require("score")


def _entity_hook(entity, kind):
    """按 entity 名从实体注册表取定制钩子(export_hook/import_hook)。
    供 floating_song 等 export=False 的实体在定制段固定位置显式调用用;
    插件未加载时返回 None,调用方按「无数据」降级"""
    for info in _api.list_entities():
        if info["entity"] == entity:
            return info.get(kind)
    return None


def _fetch_all(conn, sql, params):
    return [_api.row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def _export_entities():
    """export=True 的注册实体,按 export_order 排序(外键被引用方必须排在前面)"""
    return sorted((e for e in _api.list_entities() if e.get("export")),
                  key=lambda e: e["export_order"])


def _export_entity_rows(conn, info, project_id, id_sets, include_deleted):
    """默认导出处理器:按注册的 fk/weak_fk 声明取一个实体的项目内行集,
    并把本实体的 id 集合写入 id_sets[entity] 供下游实体挂靠/过滤。

    id_sets: {entity: 已导出 id 集合}(均为级联剔除后的最终行集)。"""
    table = info["table"]
    entity = info["entity"]
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    # 有 deleted_at 列的表按需追加回收站过滤条件
    nd = "" if include_deleted or "deleted_at" not in cols else " AND deleted_at IS NULL"
    if "project_id" in cols:
        rows = _fetch_all(conn, f"SELECT * FROM {table} WHERE project_id = ?{nd}", (project_id,))
    else:
        # 附属表:按声明的外键挂靠已导出的父实体行集(任一外键挂上即入选,如 drafts
        # 挂 chapter 或 volume);自引用外键不作挂靠条件
        conds, params = [], []
        for col, target in {**info["fk"], **info["weak_fk"]}.items():
            if target == entity:
                continue
            ids = list(id_sets.get(target) or ())
            if ids:
                conds.append(f"{col} IN ({', '.join('?' * len(ids))})")
                params.extend(ids)
            else:
                conds.append("0")  # 父实体行集为空,该列挂不上任何行
        if not conds:
            raise ValueError(f"实体 {entity} 的表 {table} 无 project_id 列且未声明外键,无法按项目导出")
        rows = _fetch_all(conn, f"SELECT * FROM {table} WHERE {' OR '.join(conds)}{nd}", params)
    # 强外键:指向已排除行的行级联剔除(对应 ON DELETE CASCADE 语义)
    for col, target in info["fk"].items():
        valid = id_sets.get(target) or set()
        rows = [r for r in rows if r.get(col) is None or r[col] in valid]
    my_ids = {r["id"] for r in rows} if "id" in cols else set()
    # 弱外键:悬空引用置 NULL(对应 ON DELETE SET NULL 语义)
    for col, target in info["weak_fk"].items():
        valid = my_ids if target == entity else (id_sets.get(target) or set())
        for r in rows:
            if r.get(col) is not None and r[col] not in valid:
                r[col] = None
    id_sets[entity] = my_ids
    return rows


def _build_export_payload(conn, project_id, include_deleted=False):
    """把一个项目的数据收集为导出字典。
    include_deleted=False（默认）时不含回收站（软删除）数据，并级联剔除引用
    已排除行的关联行（如指向已删章节的出场记录、属于已删章节的草稿）；
    可空的弱引用（大纲 linked_chapter_id、元素 character_id 等）则置 NULL。"""
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        raise ValueError("Project not found")
    payload = {
        "app": EXPORT_APP,
        "kind": EXPORT_KIND,
        "version": EXPORT_VERSION,
        "project": _api.row_to_dict(proj),
    }
    # 声明式主循环:注册实体按 export_order 导出;project 根已作为单对象写入 payload["project"]
    id_sets = {"project": {project_id}}
    for info in _export_entities():
        if info["entity"] == "project":
            continue
        hook = info.get("export_hook")
        if hook:
            extra = hook(conn, project_id, id_sets, include_deleted)
            if extra:
                payload.update(extra)
            continue
        payload[info["table"]] = _export_entity_rows(
            conn, info, project_id, id_sets, include_deleted)

    # ====== 以下为定制代码路径(见模块 docstring;acts/scenes 属 script 插件,元素已迁 graph_nodes)======
    pid = (project_id,)
    nd = "" if include_deleted else " AND deleted_at IS NULL"
    ch_ids = id_sets.get("chapter", set())
    char_ids = id_sets.get("character", set())

    # 剧本项目结构：幕 → 场 → 卡片元素
    acts = _fetch_all(conn, f"SELECT * FROM acts WHERE project_id = ?{nd}", pid)
    act_ids = {r["id"] for r in acts}
    payload["acts"] = acts

    scenes = _fetch_all(conn, f"SELECT * FROM scenes WHERE project_id = ?{nd}", pid)
    scenes = [r for r in scenes if r["act_id"] in act_ids]
    scene_ids = {r["id"] for r in scenes}
    payload["scenes"] = scenes

    # 排序还原旧查询经 idx_elements_scene(scene_id, parent_id, sort_order) 的取数顺序
    # (按场分组,场内顶层在前、再按父元素分组,组内按 sort_order),保证导出文件字节稳定
    elements = _fetch_all(conn, f"""
        SELECT * FROM graph_nodes WHERE project_id = ?{nd}
        ORDER BY json_extract(payload, '$.scene_id'), json_extract(payload, '$.parent_id'), sort_order
    """, pid)
    # 剧作元素已迁入 graph_nodes(script 插件):payload 展开回旧 script_elements 行形状
    # (键序与旧表列序一致,sort_order 按旧 REAL 列语义转 float,保证导出文件字节稳定);
    # payload 无 scene_id 的节点不是剧本元素,跳过
    elem_rows = []
    for n in elements:
        try:
            p = json.loads(n["payload"] or "{}")
        except ValueError:
            p = {}
        if p.get("scene_id") is None:
            continue
        elem_rows.append({
            "id": n["id"], "scene_id": p.get("scene_id"), "parent_id": p.get("parent_id"),
            "element_type": n["type"], "character_id": p.get("character_id"),
            "content": p.get("content"), "song_title": p.get("song_title"),
            "sort_order": float(n["sort_order"] or 0), "version_number": p.get("version_number"),
            "created_at": n["created_at"], "updated_at": n["updated_at"],
            "deleted_at": n["deleted_at"], "score_file": p.get("score_file"),
        })
    elements = [r for r in elem_rows if r["scene_id"] in scene_ids]
    elem_ids = {r["id"] for r in elements}
    for r in elements:
        if r.get("parent_id") not in elem_ids:
            r["parent_id"] = None
        if r.get("character_id") not in char_ids:
            r["character_id"] = None
        # 乐谱文件 base64 内嵌；文件丢失(或 score 插件未加载)则清掉悬空引用
        if r.get("score_file"):
            svc = _score_svc()
            data = svc["read_score_bytes"](project_id, r["score_file"]) if svc else None
            if data is not None:
                r["score_b64"] = base64.b64encode(data).decode("ascii")
            else:
                r["score_file"] = None
    payload["script_elements"] = elements

    s_chars = _fetch_all(conn, """
        SELECT * FROM scene_characters WHERE scene_id IN
            (SELECT id FROM scenes WHERE project_id = ?)
    """, pid)
    payload["scene_characters"] = [r for r in s_chars
                                   if r["scene_id"] in scene_ids and r["character_id"] in char_ids]

    e_chars = _fetch_all(conn, """
        SELECT * FROM element_characters WHERE element_id IN
            (SELECT id FROM graph_nodes WHERE project_id = ?)
    """, pid)
    payload["element_characters"] = [r for r in e_chars
                                     if r["element_id"] in elem_ids and r["character_id"] in char_ids]

    payload["script_config"] = _fetch_all(conn, "SELECT * FROM script_config WHERE project_id = ?", pid)

    # 游离歌曲（独立顶层键；由 floating_song 插件注册的 export_hook 产出,
    # 在此固定位置调用以保持导出文件键序逐字节不变;插件未加载时退化为空数组）
    fs_hook = _entity_hook("floating_song", "export_hook")
    if fs_hook:
        extra = fs_hook(conn, project_id, id_sets, include_deleted)
        payload["floating_songs"] = (extra or {}).get("floating_songs", [])
    else:
        payload["floating_songs"] = []
    return payload


def export_project_json(project_id, output_path="", include_deleted=False):
    """导出整个项目为 JSON 文件（默认不含回收站数据），返回 {"filePath": ...}"""
    conn = _api.db()
    try:
        payload = _build_export_payload(conn, project_id, include_deleted=include_deleted)
    finally:
        conn.close()
    out = _resolve_output_path(output_path, "json", payload["project"].get("title") or "export")
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise ValueError(f"无法写入文件 {out}：{e}")
    return {"filePath": out}


def _rows(payload, key):
    """取导出文件中的表行数组，类型不符时报格式错误"""
    rows = payload.get(key)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError(f"导出文件格式不正确：{key} 应为数组")
    return rows


def _insert_rows(conn, table, rows, remap, required=(), self_field=None):
    """按 remap（{字段: {旧id: 新id}}）重映射外键后逐行插入，返回 {旧id: 新id}。
    required 中的外键若指向不存在的旧 id（悬空引用，如引用了被排除的回收站行），
    整行跳过；可空外键悬空时置 NULL。
    self_field 用于自引用表（如 outlines.parent_id）：先置 NULL 插入，再统一回写。"""
    id_map = {}
    pending_self = []
    for src in rows:
        if not isinstance(src, dict):
            raise ValueError(f"导出文件格式不正确：{table} 存在非法行")
        row = dict(src)
        old_id = row.pop("id", None)
        old_self = row.pop(self_field, None) if self_field else None
        skip = False
        for field, m in remap.items():
            v = row.get(field)
            if v is not None:
                nv = m.get(v)
                if nv is None and field in required:
                    skip = True
                    break
                row[field] = nv
        if skip:
            continue
        if self_field and self_field in src:
            row[self_field] = None
        cols = list(row.keys())
        cur = conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [row[c] for c in cols])
        if old_id is not None:
            id_map[old_id] = cur.lastrowid
        if old_self is not None:
            pending_self.append((cur.lastrowid, old_self))
    for new_id, old_self in pending_self:
        conn.execute(f"UPDATE {table} SET {self_field} = ? WHERE id = ?",
                     (id_map.get(old_self), new_id))
    return id_map


def _import_entity_rows(conn, info, payload, id_maps):
    """默认导入处理器:按注册的 fk/weak_fk 声明重映射插入,返回 {旧id: 新id}。
    id_maps: {entity: {旧id: 新id}}(被引用实体须已按 export_order 先导入)。"""
    remap, required, self_field = {}, [], None
    for col, target in info["fk"].items():
        remap[col] = id_maps.get(target, {})
        required.append(col)
    for col, target in info["weak_fk"].items():
        if target == info["entity"]:
            self_field = col
        else:
            remap[col] = id_maps.get(target, {})
    return _insert_rows(conn, info["table"], _rows(payload, info["table"]),
                        remap, required=tuple(required), self_field=self_field)


def import_project_json(payload):
    """把导出 JSON 创建为全新项目副本（所有 id 重新分配，标题加「（副本）」），返回新项目字典"""
    if not isinstance(payload, dict):
        raise ValueError("导入数据格式不正确")
    if payload.get("app") != EXPORT_APP or payload.get("kind") != EXPORT_KIND:
        raise ValueError("不是有效的项目导出文件")
    if payload.get("version") != EXPORT_VERSION:
        raise ValueError(f"不支持的导出版本：{payload.get('version')}")
    proj = payload.get("project")
    if not isinstance(proj, dict) or not proj.get("title"):
        raise ValueError("导出文件缺少项目信息")

    conn = _api.db()
    try:
        # projects 根:标题加副本后缀(导出格式固有的根,单独处理)
        prow = dict(proj)
        prow.pop("id", None)
        prow["title"] = f"{prow['title']}（副本）"
        cols = list(prow.keys())
        cur = conn.execute(
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [prow[c] for c in cols])
        new_project_id = cur.lastrowid
        pmap = {proj["id"]: new_project_id} if proj.get("id") is not None else {}

        # 声明式主循环:注册实体按 export_order 重映射插入(依赖顺序与导出一致)
        id_maps = {"project": pmap}
        for info in _export_entities():
            if info["entity"] == "project":
                continue
            hook = info.get("import_hook")
            if hook:
                id_maps[info["entity"]] = hook(conn, payload, id_maps, new_project_id) or {}
                continue
            id_maps[info["entity"]] = _import_entity_rows(conn, info, payload, id_maps)

        # ====== 以下为定制代码路径(见模块 docstring;acts/scenes 属 script 插件,元素已迁 graph_nodes)======
        vmap = id_maps.get("volume", {})
        cmap = id_maps.get("chapter", {})
        hmap = id_maps.get("character", {})

        amap = _insert_rows(conn, "acts", _rows(payload, "acts"),
                            {"project_id": pmap}, required=("project_id",))
        smap = _insert_rows(conn, "scenes", _rows(payload, "scenes"),
                            {"act_id": amap, "project_id": pmap},
                            required=("act_id", "project_id"))
        elem_rows = _rows(payload, "script_elements")
        # 乐谱：抽出内嵌的 base64（不参与列插入），无内嵌数据的行清掉悬空的 score_file
        elem_score_b64 = {}
        for r in elem_rows:
            b = r.pop("score_b64", None)
            if b and r.get("id") is not None:
                elem_score_b64[r["id"]] = b
            elif r.get("score_file"):
                r["score_file"] = None
        # 剧作元素已迁入 graph_nodes(script 插件):旧行形状重新组装为节点
        # (type=element_type,内容字段进 payload;scene_id 强引用映射不到整行跳过,
        # character_id 弱引用悬空置 NULL,均与旧默认/定制语义一致)
        emap = {}
        pending_parent = []
        for src in elem_rows:
            if not isinstance(src, dict):
                raise ValueError("导出文件格式不正确：script_elements 存在非法行")
            row = dict(src)
            old_id = row.pop("id", None)
            old_parent = row.pop("parent_id", None)
            scene_id = row.get("scene_id")
            if scene_id is not None:
                scene_id = smap.get(scene_id)
                if scene_id is None:
                    continue
            character_id = row.get("character_id")
            if character_id is not None:
                character_id = hmap.get(character_id)
            node_payload = json.dumps({
                "scene_id": scene_id, "parent_id": None,
                "character_id": character_id,
                "content": row.get("content"), "song_title": row.get("song_title"),
                "score_file": row.get("score_file"), "version_number": row.get("version_number"),
            }, ensure_ascii=False)
            # 列 parent_id 暂置场景 id(异构父),元素父在第二趟统一回写
            cols = ["project_id", "type", "parent_id", "sort_order", "payload"]
            vals = [new_project_id, row.get("element_type"), scene_id,
                    row.get("sort_order", 0), node_payload]
            for extra in ("created_at", "updated_at", "deleted_at"):
                if extra in row:
                    cols.append(extra)
                    vals.append(row[extra])
            cur = conn.execute(
                f"INSERT INTO graph_nodes ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                vals)
            if old_id is not None:
                emap[old_id] = cur.lastrowid
            if old_parent is not None:
                pending_parent.append((cur.lastrowid, old_parent))
        for new_id, old_parent in pending_parent:
            new_parent = emap.get(old_parent)
            if new_parent is None:
                # 悬空 parent_id(父元素未导出)退回顶层:列 parent_id 保持场景 id,payload 置 null
                conn.execute(
                    "UPDATE graph_nodes SET payload = json_set(payload, '$.parent_id', NULL) WHERE id = ?",
                    (new_id,))
            else:
                conn.execute(
                    """UPDATE graph_nodes SET parent_id = ?,
                           payload = json_set(payload, '$.parent_id', ?) WHERE id = ?""",
                    (new_parent, new_parent, new_id))
        # 按新 id 写回乐谱文件并更新 payload 的 score_file(score 插件未加载则跳过,score_file 保持 NULL)
        score_svc = _score_svc()
        if elem_score_b64 and score_svc:
            for old_id, b in elem_score_b64.items():
                new_id = emap.get(old_id)
                if new_id is None:
                    continue
                filename = score_svc["write_score_file"](
                    new_project_id, f"element_{new_id}.mscz", base64.b64decode(b))
                conn.execute(
                    "UPDATE graph_nodes SET payload = json_set(payload, '$.score_file', ?) WHERE id = ?",
                    (filename, new_id))
        _insert_rows(conn, "scene_characters", _rows(payload, "scene_characters"),
                     {"scene_id": smap, "character_id": hmap},
                     required=("scene_id", "character_id"))
        _insert_rows(conn, "element_characters", _rows(payload, "element_characters"),
                     {"element_id": emap, "character_id": hmap},
                     required=("element_id", "character_id"))
        for row in _rows(payload, "script_config"):
            conn.execute("INSERT INTO script_config (project_id, script_type) VALUES (?, ?)",
                         (new_project_id, row.get("script_type", "play")))
        # 游离歌曲（独立键；由 floating_song 插件注册的 import_hook 处理,
        # 老导出文件无此键时钩子内部视为空;插件未加载则跳过）
        fs_import = _entity_hook("floating_song", "import_hook")
        if fs_import:
            id_maps["floating_song"] = fs_import(conn, payload, id_maps, new_project_id) or {}
        conn.commit()
        return _api.row_to_dict(conn.execute(
            "SELECT * FROM projects WHERE id = ?", (new_project_id,)).fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class Plugin:
    def activate(self, api):
        global _api
        _api = api

        # 对外提供整项目 JSON 导入/导出,project 插件的 /api/projects/import 依赖它(运行时再取)
        api.provide("json_transfer", {
            "import_project_json": import_project_json,
            "export_project_json": export_project_json,
        })

        @api.route("/api/export/json", methods=["POST"])
        def api_export_json():
            data = api.req_json()
            try:
                return api.jsonify(export_project_json(
                    project_id=data.get("projectId"),
                    output_path=data.get("outputPath", ""),
                ))
            except ExportPluginUnavailable as e:
                return api.jsonify({"error": str(e)}), 503
            except ValueError as e:
                return api.jsonify({"error": str(e)}), 400
