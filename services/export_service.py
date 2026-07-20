import os
from database import get_conn, row_to_dict

def _get_chapter_content(chapter_id):
    conn = get_conn()
    ch = conn.execute("SELECT * FROM chapters WHERE id = ? AND deleted_at IS NULL", (chapter_id,)).fetchone()
    if not ch: conn.close(); return None
    vol = conn.execute("SELECT * FROM volumes WHERE id = ?", (ch["volume_id"],)).fetchone()
    draft = conn.execute(
        "SELECT * FROM drafts WHERE chapter_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1",
        (chapter_id,)
    ).fetchone()
    conn.close()
    return {
        "volumeTitle": vol["title"] if vol else "",
        "volumePreface": vol["preface"] if vol else "",
        "chapterTitle": ch["title"],
        "content": draft["content"] if draft else "",
    }

def _get_project_contents(project_id):
    conn = get_conn()
    volumes = conn.execute("SELECT * FROM volumes WHERE project_id = ? AND deleted_at IS NULL ORDER BY sort_order", (project_id,)).fetchall()
    result = []
    for vol in volumes:
        chapters = conn.execute("SELECT * FROM chapters WHERE volume_id = ? AND deleted_at IS NULL ORDER BY sort_order", (vol["id"],)).fetchall()
        ch_contents = []
        for ch in chapters:
            draft = conn.execute("SELECT * FROM drafts WHERE chapter_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1", (ch["id"],)).fetchone()
            ch_contents.append({"title": ch["title"], "content": draft["content"] if draft else ""})
        result.append({
            "volumeTitle": vol["title"],
            "volumePreface": vol["preface"] or "",
            "chapters": ch_contents,
        })
    conn.close()
    return result

def export_txt(chapter_id=None, project_id=None, output_path=""):
    text = ""
    if chapter_id:
        data = _get_chapter_content(chapter_id)
        if not data: raise ValueError("Chapter not found")
        if data["volumeTitle"]: text += f"【{data['volumeTitle']}】\n\n"
        text += f"第X章 {data['chapterTitle']}\n\n{data['content']}"
    elif project_id:
        volumes = _get_project_contents(project_id)
        for vol in volumes:
            text += f"\n\n========== {vol['volumeTitle']} ==========\n\n"
            if vol["volumePreface"]: text += f"{vol['volumePreface']}\n\n---\n\n"
            for ch in vol["chapters"]:
                text += f"第X章 {ch['title']}\n\n{ch['content']}\n\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return {"filePath": output_path}


def export_docx(chapter_id=None, project_id=None, output_path="", options=None):
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    opts = options or {}
    font_name = opts.get("font", "SimSun")
    font_size = opts.get("fontSize", 12)  # 12pt
    line_spacing = opts.get("lineSpacing", 1.5)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = font_name
    style.font.size = Pt(font_size)
    style.paragraph_format.line_spacing = line_spacing

    if chapter_id:
        data = _get_chapter_content(chapter_id)
        if not data: raise ValueError("Chapter not found")
        if data["volumeTitle"]:
            doc.add_heading(data["volumeTitle"], level=1)
        doc.add_heading(data["chapterTitle"], level=2)
        for para in (data["content"] or "").split("\n"):
            doc.add_paragraph(para)
    elif project_id:
        volumes = _get_project_contents(project_id)
        for vol in volumes:
            doc.add_heading(vol["volumeTitle"], level=1)
            if vol["volumePreface"]:
                p = doc.add_paragraph(vol["volumePreface"])
                p.italic = True
            for ch in vol["chapters"]:
                doc.add_heading(ch["title"], level=2)
                for para in (ch["content"] or "").split("\n"):
                    doc.add_paragraph(para)

    doc.save(output_path)
    return {"filePath": output_path}
