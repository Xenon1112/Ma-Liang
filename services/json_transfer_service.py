import json
import base64
from core.database import get_conn, row_to_dict
from services.export_service import _resolve_output_path

EXPORT_APP = "novel-writer"
EXPORT_KIND = "project-export"
EXPORT_VERSION = 1

# 参与导出/导入的项目级数据表（不含 tags/entity_tags/app_config 等全局表）
_TABLE_KEYS = [
    "volumes", "chapters", "drafts", "outlines",
    "characters", "character_fields", "character_appearances",
    "world_settings", "inspirations",
    "acts", "scenes", "script_elements",
    "scene_characters", "element_characters", "script_config",
]


def _fetch_all(conn, sql, params):
    return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


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
        "project": row_to_dict(proj),
    }
    pid = (project_id,)
    # 有 deleted_at 列的表按需追加回收站过滤条件
    nd = "" if include_deleted else " AND deleted_at IS NULL"

    volumes = _fetch_all(conn, f"SELECT * FROM volumes WHERE project_id = ?{nd}", pid)
    vol_ids = {r["id"] for r in volumes}
    payload["volumes"] = volumes

    chapters = _fetch_all(conn, f"SELECT * FROM chapters WHERE project_id = ?{nd}", pid)
    # 级联：所属卷被排除的章节一并剔除
    chapters = [r for r in chapters if r["volume_id"] in vol_ids]
    ch_ids = {r["id"] for r in chapters}
    payload["chapters"] = chapters

    # 草稿挂在章节上（章节草稿）或卷上（卷首语草稿，chapter_id 为 NULL）
    drafts = _fetch_all(conn, """
        SELECT * FROM drafts WHERE
            chapter_id IN (SELECT id FROM chapters WHERE project_id = ?)
            OR volume_id IN (SELECT id FROM volumes WHERE project_id = ?)
    """, (project_id, project_id))
    payload["drafts"] = [d for d in drafts if d["chapter_id"] in ch_ids
                         or (d["chapter_id"] is None and d["volume_id"] in vol_ids)]

    outlines = _fetch_all(conn, f"SELECT * FROM outlines WHERE project_id = ?{nd}", pid)
    outline_ids = {r["id"] for r in outlines}
    for r in outlines:
        # 弱引用指向已排除行时置 NULL（对应 ON DELETE SET NULL 语义）
        if r.get("parent_id") not in outline_ids:
            r["parent_id"] = None
        if r.get("linked_chapter_id") not in ch_ids:
            r["linked_chapter_id"] = None
    payload["outlines"] = outlines

    characters = _fetch_all(conn, f"SELECT * FROM characters WHERE project_id = ?{nd}", pid)
    char_ids = {r["id"] for r in characters}
    payload["characters"] = characters

    fields = _fetch_all(conn, """
        SELECT * FROM character_fields WHERE character_id IN
            (SELECT id FROM characters WHERE project_id = ?)
    """, pid)
    payload["character_fields"] = [r for r in fields if r["character_id"] in char_ids]

    appearances = _fetch_all(conn, """
        SELECT * FROM character_appearances WHERE character_id IN
            (SELECT id FROM characters WHERE project_id = ?)
    """, pid)
    payload["character_appearances"] = [r for r in appearances
                                        if r["character_id"] in char_ids and r["chapter_id"] in ch_ids]

    payload["world_settings"] = _fetch_all(conn, f"SELECT * FROM world_settings WHERE project_id = ?{nd}", pid)

    inspirations = _fetch_all(conn, f"SELECT * FROM inspirations WHERE project_id = ?{nd}", pid)
    for r in inspirations:
        if r.get("linked_chapter_id") not in ch_ids:
            r["linked_chapter_id"] = None
    payload["inspirations"] = inspirations

    # 剧本项目结构：幕 → 场 → 卡片元素
    acts = _fetch_all(conn, f"SELECT * FROM acts WHERE project_id = ?{nd}", pid)
    act_ids = {r["id"] for r in acts}
    payload["acts"] = acts

    scenes = _fetch_all(conn, f"SELECT * FROM scenes WHERE project_id = ?{nd}", pid)
    scenes = [r for r in scenes if r["act_id"] in act_ids]
    scene_ids = {r["id"] for r in scenes}
    payload["scenes"] = scenes

    elements = _fetch_all(conn, f"""
        SELECT * FROM script_elements WHERE scene_id IN
            (SELECT id FROM scenes WHERE project_id = ?){nd}
    """, pid)
    elements = [r for r in elements if r["scene_id"] in scene_ids]
    elem_ids = {r["id"] for r in elements}
    for r in elements:
        if r.get("parent_id") not in elem_ids:
            r["parent_id"] = None
        if r.get("character_id") not in char_ids:
            r["character_id"] = None
        # 乐谱文件 base64 内嵌；文件丢失则清掉悬空引用
        if r.get("score_file"):
            from services import score_service
            data = score_service.read_score_bytes(project_id, r["score_file"])
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
            (SELECT id FROM script_elements WHERE scene_id IN
                (SELECT id FROM scenes WHERE project_id = ?))
    """, pid)
    payload["element_characters"] = [r for r in e_chars
                                     if r["element_id"] in elem_ids and r["character_id"] in char_ids]

    payload["script_config"] = _fetch_all(conn, "SELECT * FROM script_config WHERE project_id = ?", pid)

    # 游离歌曲（独立顶层键；lyrics 为扁平结构，parent_id 引用同歌内其他行的 id；
    # 不进正文/TXT/DOCX，仅音乐剧有数据）
    from services.floating_song_service import _parse_ids
    floating = []
    fs_rows = _fetch_all(conn, f"SELECT * FROM floating_songs WHERE project_id = ?{nd} ORDER BY sort_order", pid)
    for s in fs_rows:
        lyrics = _fetch_all(conn,
            "SELECT id, parent_id, element_type, content, character_ids, sort_order FROM floating_lyrics WHERE song_id = ? ORDER BY sort_order, id",
            (s["id"],))
        song_dict = {
            "song_title": s["song_title"],
            "sort_order": s["sort_order"],
            "lyrics": [{
                # 保留原行 id 供同歌内 parent_id 引用
                "id": l["id"],
                "parent_id": l["parent_id"],
                "element_type": l["element_type"] or "lyric",
                "content": l["content"],
                # 过滤指向已排除角色的悬空引用
                "character_ids": [i for i in _parse_ids(l["character_ids"]) if i in char_ids],
                "sort_order": l["sort_order"],
            } for l in lyrics],
        }
        # 乐谱文件 base64 内嵌；文件丢失则不导出
        if s.get("score_file"):
            from services import score_service
            data = score_service.read_score_bytes(project_id, s["score_file"])
            if data is not None:
                song_dict["score_b64"] = base64.b64encode(data).decode("ascii")
        floating.append(song_dict)
    payload["floating_songs"] = floating
    return payload


def export_project_json(project_id, output_path="", include_deleted=False):
    """导出整个项目为 JSON 文件（默认不含回收站数据），返回 {"filePath": ...}"""
    conn = get_conn()
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

    conn = get_conn()
    try:
        # projects：标题加副本后缀
        prow = dict(proj)
        prow.pop("id", None)
        prow["title"] = f"{prow['title']}（副本）"
        cols = list(prow.keys())
        cur = conn.execute(
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [prow[c] for c in cols])
        new_project_id = cur.lastrowid
        pmap = {proj["id"]: new_project_id} if proj.get("id") is not None else {}

        # 按依赖顺序逐表重映射 id 插入；required 列出不可空外键，悬空则整行跳过
        vmap = _insert_rows(conn, "volumes", _rows(payload, "volumes"),
                            {"project_id": pmap}, required=("project_id",))
        cmap = _insert_rows(conn, "chapters", _rows(payload, "chapters"),
                            {"volume_id": vmap, "project_id": pmap},
                            required=("volume_id", "project_id"))
        _insert_rows(conn, "drafts", _rows(payload, "drafts"),
                     {"chapter_id": cmap, "volume_id": vmap},
                     required=("chapter_id", "volume_id"))
        _insert_rows(conn, "outlines", _rows(payload, "outlines"),
                     {"project_id": pmap, "linked_chapter_id": cmap},
                     required=("project_id",), self_field="parent_id")
        hmap = _insert_rows(conn, "characters", _rows(payload, "characters"),
                            {"project_id": pmap}, required=("project_id",))
        _insert_rows(conn, "character_fields", _rows(payload, "character_fields"),
                     {"character_id": hmap}, required=("character_id",))
        _insert_rows(conn, "character_appearances", _rows(payload, "character_appearances"),
                     {"character_id": hmap, "chapter_id": cmap},
                     required=("character_id", "chapter_id"))
        _insert_rows(conn, "world_settings", _rows(payload, "world_settings"),
                     {"project_id": pmap}, required=("project_id",))
        _insert_rows(conn, "inspirations", _rows(payload, "inspirations"),
                     {"project_id": pmap, "linked_chapter_id": cmap},
                     required=("project_id",))
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
        emap = _insert_rows(conn, "script_elements", elem_rows,
                            {"scene_id": smap, "character_id": hmap},
                            required=("scene_id",), self_field="parent_id")
        # 按新 id 写回乐谱文件并更新 score_file 列
        if elem_score_b64:
            from services import score_service
            for old_id, b in elem_score_b64.items():
                new_id = emap.get(old_id)
                if new_id is None:
                    continue
                filename = score_service.write_score_file(
                    new_project_id, f"element_{new_id}.mscz", base64.b64decode(b))
                conn.execute("UPDATE script_elements SET score_file = ? WHERE id = ?",
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
        # 游离歌曲（独立键；老导出文件无此键时视为空）
        for s in _rows(payload, "floating_songs"):
            if not isinstance(s, dict):
                raise ValueError("导出文件格式不正确：floating_songs 存在非法行")
            cur = conn.execute(
                "INSERT INTO floating_songs (project_id, song_title, sort_order) VALUES (?, ?, ?)",
                (new_project_id, s.get("song_title") or "未命名歌曲", s.get("sort_order", 0)))
            # 乐谱：内嵌的 base64 写回文件并更新 score_file 列
            if s.get("score_b64"):
                from services import score_service
                filename = score_service.write_score_file(
                    new_project_id, f"floating_{cur.lastrowid}.mscz",
                    base64.b64decode(s["score_b64"]))
                conn.execute("UPDATE floating_songs SET score_file = ? WHERE id = ?",
                             (filename, cur.lastrowid))
            # 先插全部行（parent_id 暂置 NULL）并建立 旧id→新id 映射，再统一回写 parent_id
            lyric_map = {}
            pending_parent = []
            for l in (s.get("lyrics") or []):
                # 演唱者 id 重映射到新角色；悬空引用丢弃
                ids = [hmap[i] for i in (l.get("character_ids") or []) if i in hmap]
                lcur = conn.execute(
                    "INSERT INTO floating_lyrics (song_id, element_type, character_id, character_ids, content, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                    (cur.lastrowid, l.get("element_type") or "lyric", ids[0] if ids else None,
                     json.dumps(ids, ensure_ascii=False), l.get("content", ""), l.get("sort_order", 0)))
                if l.get("id") is not None:
                    lyric_map[l["id"]] = lcur.lastrowid
                if l.get("parent_id") is not None:
                    pending_parent.append((lcur.lastrowid, l["parent_id"]))
            for new_id, old_parent in pending_parent:
                # 悬空 parent_id（父行未导出）置 NULL，退回顶层
                conn.execute("UPDATE floating_lyrics SET parent_id = ? WHERE id = ?",
                             (lyric_map.get(old_parent), new_id))
        conn.commit()
        return row_to_dict(conn.execute(
            "SELECT * FROM projects WHERE id = ?", (new_project_id,)).fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
