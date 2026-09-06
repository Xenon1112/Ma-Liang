import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from core.database import get_conn, get_user_data_dir
from core import config as config_service

# ====== 歌曲乐谱（MuseScore .mscz 文件，调起本机 MuseScore 编辑） ======

# 最小 .mscx 模板：参照 MuseScore 4.7 自带 Treble Clef 模板（单个高音谱表、4/4、空小节）
# __TITLE__ 占位符替换为歌名（XML 转义后）
_MSCX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.70">
  <Score>
    <LayerTag id="0" tag="default"></LayerTag>
    <currentLayer>0</currentLayer>
    <Division>480</Division>
    <showInvisible>1</showInvisible>
    <showUnprintable>1</showUnprintable>
    <showFrames>1</showFrames>
    <showMargins>0</showMargins>
    <metaTag name="arranger"></metaTag>
    <metaTag name="composer"></metaTag>
    <metaTag name="copyright"></metaTag>
    <metaTag name="lyricist"></metaTag>
    <metaTag name="movementNumber"></metaTag>
    <metaTag name="movementTitle"></metaTag>
    <metaTag name="source"></metaTag>
    <metaTag name="translator"></metaTag>
    <metaTag name="workNumber"></metaTag>
    <metaTag name="workTitle">__TITLE__</metaTag>
    <Part>
      <Staff id="1">
        <StaffType group="pitched">
          <name>stdNormal</name>
          </StaffType>
        <barLineSpan>1</barLineSpan>
        </Staff>
      <trackName>Piano</trackName>
      <Instrument id="piano">
        <longName>Piano</longName>
        <shortName>Pno.</shortName>
        <trackName>Piano</trackName>
        <minPitchP>21</minPitchP>
        <maxPitchP>108</maxPitchP>
        <minPitchA>21</minPitchA>
        <maxPitchA>108</maxPitchA>
        <instrumentId>keyboard.piano</instrumentId>
        <singleNoteDynamics>0</singleNoteDynamics>
        <Channel>
          <program value="0"/>
          <synti>Fluid</synti>
          </Channel>
        </Instrument>
      </Part>
    <Staff id="1">
      <VBox>
        <height>10</height>
        <Text>
          <style>title</style>
          <text>__TITLE__</text>
          </Text>
        </VBox>
      <Measure>
        <voice>
          <TimeSig>
            <sigN>4</sigN>
            <sigD>4</sigD>
            </TimeSig>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          </voice>
        </Measure>
      <Measure>
        <voice>
          <Rest>
            <durationType>measure</durationType>
            <duration>4/4</duration>
            </Rest>
          <BarLine>
            <subtype>end</subtype>
            </BarLine>
          </voice>
        </Measure>
      </Staff>
    </Score>
  </museScore>
"""

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container>
  <rootfiles>
    <rootfile full-path="score.mscx">
      </rootfile>
    </rootfiles>
  </container>
"""


def _scores_dir(project_id):
    d = get_user_data_dir() / "scores" / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect_musescore_path():
    """自动探测常见安装路径，找不到返回 None"""
    candidates = []
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe",
        ]
        for name in ("MuseScore4.exe", "mscore.exe"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    elif sys.platform == "darwin":
        candidates = ["/Applications/MuseScore 4.app/Contents/MacOS/mscore"]
    else:
        for name in ("mscore", "musescore4", "musescore"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


def get_musescore_path():
    """配置优先，其次自动探测；均失败返回 None"""
    configured = (config_service.get_config().get("musescorePath") or "").strip()
    if configured and Path(configured).exists():
        return configured
    return detect_musescore_path()


def _locate_song(conn, project_id, element_id, floating_song_id):
    """校验目标歌曲存在且属于该项目，返回 (table, row)"""
    if element_id:
        row = conn.execute(
            """SELECT se.* FROM script_elements se
               JOIN scenes s ON se.scene_id = s.id
               WHERE se.id = ? AND s.project_id = ? AND se.element_type = 'song'""",
            (element_id, project_id)).fetchone()
        if not row:
            raise ValueError("歌曲不存在或不属于该项目")
        return "script_elements", row
    if floating_song_id:
        row = conn.execute(
            "SELECT * FROM floating_songs WHERE id = ? AND project_id = ?",
            (floating_song_id, project_id)).fetchone()
        if not row:
            raise ValueError("游离歌曲不存在或不属于该项目")
        return "floating_songs", row
    raise ValueError("缺少 elementId 或 floatingSongId")


def _score_filename(element_id, floating_song_id):
    return f"element_{element_id}.mscz" if element_id else f"floating_{floating_song_id}.mscz"


def create_score_file(project_id, element_id, floating_song_id, song_title):
    """按歌名生成最小 .mscz，返回绝对路径"""
    mscx = _MSCX_TEMPLATE.replace("__TITLE__", escape(song_title or "未命名歌曲"))
    path = _scores_dir(project_id) / _score_filename(element_id, floating_song_id)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("score.mscx", mscx)
    return path


def _score_abs_path(project_id, filename):
    return _scores_dir(project_id) / filename


def get_score_info(project_id, element_id=None, floating_song_id=None):
    conn = get_conn()
    table, row = _locate_song(conn, project_id, element_id, floating_song_id)
    conn.close()
    filename = row["score_file"]
    if not filename:
        return {"exists": False}
    path = _score_abs_path(project_id, filename)
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {"exists": True, "fileSize": stat.st_size, "updatedAt": int(stat.st_mtime)}


def open_score(project_id, element_id=None, floating_song_id=None, song_title=None):
    """无乐谱则生成模板，然后调起本机 MuseScore 打开。返回 (created, path)"""
    musescore = get_musescore_path()
    if not musescore:
        raise ValueError("未找到 MuseScore。请先从 musescore.org 安装 MuseScore 4，或在设置中配置 MuseScore 路径")

    conn = get_conn()
    table, row = _locate_song(conn, project_id, element_id, floating_song_id)
    created = False
    filename = row["score_file"]
    path = _score_abs_path(project_id, filename) if filename else None
    if not filename or not path.exists():
        title = song_title or row["song_title"] or "未命名歌曲"
        path = create_score_file(project_id, element_id, floating_song_id, title)
        conn.execute(
            f"UPDATE {table} SET score_file = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (path.name, row["id"]))
        conn.commit()
        created = True
    conn.close()

    subprocess.Popen([musescore, str(path)])
    return created, str(path)


def delete_score(project_id, element_id=None, floating_song_id=None):
    conn = get_conn()
    table, row = _locate_song(conn, project_id, element_id, floating_song_id)
    filename = row["score_file"]
    if filename:
        path = _score_abs_path(project_id, filename)
        if path.exists():
            path.unlink()
        conn.execute(
            f"UPDATE {table} SET score_file = NULL, updated_at = datetime('now','localtime') WHERE id = ?",
            (row["id"],))
        conn.commit()
    conn.close()


def discard_score_file(project_id, filename):
    """歌曲被删除时清理乐谱文件（文件不存在则忽略）"""
    if project_id and filename:
        path = _score_abs_path(project_id, filename)
        if path.exists():
            path.unlink()


def transfer_score(project_id, filename, element_id=None, floating_song_id=None):
    """歌曲互转（正文 ↔ 游离）时把乐谱文件改名并挂到新行上"""
    if not filename:
        return
    src = _score_abs_path(project_id, filename)
    if not src.exists():
        return
    new_name = _score_filename(element_id, floating_song_id)
    dst = _score_abs_path(project_id, new_name)
    if src != dst:
        src.replace(dst)
    table = "script_elements" if element_id else "floating_songs"
    conn = get_conn()
    conn.execute(f"UPDATE {table} SET score_file = ? WHERE id = ?",
                 (new_name, element_id or floating_song_id))
    conn.commit()
    conn.close()


def read_score_bytes(project_id, filename):
    """读取乐谱文件内容（JSON 导出用），文件丢失返回 None"""
    if not filename:
        return None
    path = _score_abs_path(project_id, filename)
    if not path.exists():
        return None
    return path.read_bytes()


def write_score_file(project_id, filename, data):
    """写入乐谱文件（JSON 导入用；数据库列由调用方在自己的事务里更新），返回文件名"""
    path = _score_abs_path(project_id, filename)
    path.write_bytes(data)
    return filename
