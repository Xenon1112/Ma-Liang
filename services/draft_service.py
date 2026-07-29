from database import get_conn, row_to_dict, hash_content, count_words

def get_current_draft(chapter_id=None, volume_id=None):
    conn = get_conn()
    if chapter_id:
        row = conn.execute(
            "SELECT * FROM drafts WHERE chapter_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1",
            (chapter_id,)
        ).fetchone()
    elif volume_id:
        row = conn.execute(
            "SELECT * FROM drafts WHERE volume_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1",
            (volume_id,)
        ).fetchone()
    else:
        row = None
    conn.close()
    return row_to_dict(row)

def save_draft(data):
    conn = get_conn()
    chapter_id = data.get("chapter_id")
    volume_id = data.get("volume_id")
    content = data.get("content", "")
    change_note = data.get("change_note", "")
    version_tag = data.get("version_tag", "auto")
    new_hash = hash_content(content)

    try:
        # 事务内完成"读 current → 置旧 → 插新"，防止并发自动保存产生两个 current
        conn.execute("BEGIN IMMEDIATE")
        if chapter_id:
            row = conn.execute(
                "SELECT * FROM drafts WHERE chapter_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1",
                (chapter_id,)).fetchone()
        elif volume_id:
            row = conn.execute(
                "SELECT * FROM drafts WHERE volume_id = ? AND is_current = 1 ORDER BY version_number DESC LIMIT 1",
                (volume_id,)).fetchone()
        else:
            row = None
        current = row_to_dict(row)

        if current and current.get("content_hash") == new_hash:
            conn.commit()
            return current

        new_version = (current["version_number"] + 1) if current else 1
        chinese, total = count_words(content)

        # 取消旧的 current
        if current:
            conn.execute("UPDATE drafts SET is_current = 0 WHERE id = ?", (current["id"],))

        cur = conn.execute("""
            INSERT INTO drafts (chapter_id, volume_id, content, version_number, word_count, change_note, version_tag, is_current, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (chapter_id, volume_id, content, new_version, total, change_note, version_tag, new_hash))

        # 更新 word_count
        if chapter_id:
            conn.execute("UPDATE chapters SET word_count = ?, updated_at = datetime('now','localtime') WHERE id = ?", (total, chapter_id))

        conn.commit()
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def list_drafts(chapter_id=None, volume_id=None):
    conn = get_conn()
    if chapter_id:
        rows = conn.execute(
            "SELECT id, version_number, word_count, change_note, version_tag, is_current, created_at FROM drafts WHERE chapter_id = ? ORDER BY version_number DESC",
            (chapter_id,)
        ).fetchall()
    elif volume_id:
        rows = conn.execute(
            "SELECT id, version_number, word_count, change_note, version_tag, is_current, created_at FROM drafts WHERE volume_id = ? ORDER BY version_number DESC",
            (volume_id,)
        ).fetchall()
    else:
        rows = []
    conn.close()
    return [row_to_dict(r) for r in rows]

def get_draft(draft_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    return row_to_dict(row)

def diff_drafts(draft_id_a, draft_id_b):
    a = get_draft(draft_id_a)
    b = get_draft(draft_id_b)
    if not a or not b:
        return {"added": [], "removed": []}

    lines_a = (a["content"] or "").split("\n")
    lines_b = (b["content"] or "").split("\n")

    # LCS
    m, n = len(lines_a), len(lines_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if lines_a[i - 1] == lines_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs = []
    i, j = m, n
    while i > 0 and j > 0:
        if lines_a[i - 1] == lines_b[j - 1]:
            lcs.insert(0, lines_a[i - 1])
            i -= 1; j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    added, removed = [], []
    i = j = 0
    for line in lcs:
        while i < len(lines_a) and lines_a[i] != line:
            removed.append({"line": i + 1, "text": lines_a[i]})
            i += 1
        while j < len(lines_b) and lines_b[j] != line:
            added.append({"line": j + 1, "text": lines_b[j]})
            j += 1
        i += 1; j += 1
    while i < len(lines_a):
        removed.append({"line": i + 1, "text": lines_a[i]}); i += 1
    while j < len(lines_b):
        added.append({"line": j + 1, "text": lines_b[j]}); j += 1

    return {"added": added, "removed": removed}

def rollback_draft(draft_id):
    target = get_draft(draft_id)
    if not target:
        raise ValueError("Version not found")

    current = get_current_draft(target.get("chapter_id"), target.get("volume_id"))

    if current and current.get("content_hash") != target.get("content_hash"):
        save_draft({
            "chapter_id": target.get("chapter_id"),
            "volume_id": target.get("volume_id"),
            "content": current["content"],
            "version_tag": "rollback_backup",
            "change_note": f"回滚到 v{target['version_number']} 前自动备份",
        })

    return save_draft({
        "chapter_id": target.get("chapter_id"),
        "volume_id": target.get("volume_id"),
        "content": target["content"],
        "version_tag": "rollback",
        "change_note": f"回滚到版本 v{target['version_number']}",
    })

def delete_draft(draft_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    # 删除的是当前版本时，把同章/卷下版本号最大的剩余版本提升为 current，避免编辑器读到空
    if row and row["is_current"]:
        if row["chapter_id"]:
            nxt = conn.execute(
                "SELECT id FROM drafts WHERE chapter_id = ? ORDER BY version_number DESC LIMIT 1",
                (row["chapter_id"],)).fetchone()
        else:
            nxt = conn.execute(
                "SELECT id FROM drafts WHERE volume_id = ? ORDER BY version_number DESC LIMIT 1",
                (row["volume_id"],)).fetchone()
        if nxt:
            conn.execute("UPDATE drafts SET is_current = 1 WHERE id = ?", (nxt["id"],))
            # 同步章节字数到新 current，避免列表/目录树字数与编辑器内容不符
            if row["chapter_id"]:
                conn.execute(
                    "UPDATE chapters SET word_count = (SELECT word_count FROM drafts WHERE id = ?) WHERE id = ?",
                    (nxt["id"], row["chapter_id"]))
        elif row["chapter_id"]:
            # 草稿删光，章节字数归零
            conn.execute("UPDATE chapters SET word_count = 0 WHERE id = ?", (row["chapter_id"],))
    conn.commit()
    conn.close()

def create_snapshot(data):
    data["version_tag"] = "manual"
    data["change_note"] = data.get("change_note", "手动快照")
    return save_draft(data)

def clean_old_versions(chapter_id=None, volume_id=None, keep_count=50):
    conn = get_conn()
    # keep_count 至少为 1，防止传 0 删光全部版本
    keep_count = max(1, keep_count)
    if chapter_id:
        rows = conn.execute("SELECT id, is_current FROM drafts WHERE chapter_id = ? ORDER BY version_number DESC", (chapter_id,)).fetchall()
    elif volume_id:
        rows = conn.execute("SELECT id, is_current FROM drafts WHERE volume_id = ? ORDER BY version_number DESC", (volume_id,)).fetchall()
    else:
        rows = []
    if len(rows) <= keep_count:
        conn.close()
        return 0
    # 永不删除当前版本
    to_delete = [r["id"] for r in rows[keep_count:] if not r["is_current"]]
    for did in to_delete:
        conn.execute("DELETE FROM drafts WHERE id = ?", (did,))
    conn.commit()
    conn.close()
    return len(to_delete)
