"""全流程 API 调试脚本：在干净数据库上逐步调用所有核心接口"""
import sys, threading, time, json, urllib.request, urllib.error
sys.path.insert(0, ".")

BASE = "http://localhost:5290"
fails = []

def call(method, path, data=None, expect=200):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        code, text = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        code, text = e.code, e.read().decode()
    except Exception as e:
        fails.append((method, path, f"EXCEPTION {e}"))
        return None
    ok = code == expect
    tag = "OK " if ok else "FAIL"
    if not ok:
        fails.append((method, path, f"{code} != {expect}: {text[:300]}"))
    print(f"[{tag}] {method} {path} -> {code} {text[:120] if not ok else ''}")
    try:
        return json.loads(text)
    except Exception:
        return text

import app as appmod
from database import init_db
init_db()
t = threading.Thread(target=appmod.app.run, kwargs={"host": "127.0.0.1", "port": 5290}, daemon=True)
t.start()
time.sleep(2.5)

print("== 版本 ==")
call("GET", "/api/version")
call("GET", "/")

print("== 项目 ==")
p = call("POST", "/api/projects", {"title": "测试小说", "author": "调试", "projectType": "novel"}, 201)
pid = p["id"]
call("GET", "/api/projects")
call("GET", f"/api/projects/{pid}")
call("PUT", f"/api/projects/{pid}", {"subtitle": "副标题"})
call("GET", f"/api/projects/{pid}/stats")

print("== 卷/章 ==")
v = call("POST", "/api/volumes", {"projectId": pid, "title": "第一卷"}, 201)
vid = v["id"]
call("GET", f"/api/volumes?projectId={pid}")
call("PUT", f"/api/volumes/{vid}", {"title": "第一卷·改"})
c = call("POST", "/api/chapters", {"volumeId": vid, "projectId": pid, "title": "第一章"}, 201)
cid = c["id"]
call("GET", f"/api/chapters?volumeId={vid}")
call("GET", f"/api/chapters/{cid}")
call("POST", "/api/chapters/reorder", {"volumeId": vid, "orderedIds": [cid]})

print("== 草稿 ==")
call("GET", f"/api/drafts/current?chapterId={cid}")
d = call("POST", "/api/drafts", {"chapterId": cid, "content": "正文内容测试", "versionTag": "auto"})
call("GET", f"/api/drafts/current?chapterId={cid}")
call("GET", f"/api/drafts/list?chapterId={cid}")
d2 = call("POST", "/api/drafts", {"chapterId": cid, "content": "正文内容测试 v2"})
call("POST", "/api/drafts/diff", {"draftIdA": d["id"], "draftIdB": d2["id"]})
call("POST", f"/api/drafts/{d['id']}/rollback")
call("POST", "/api/drafts/snapshot", {"chapterId": cid, "changeNote": "快照"})
call("POST", "/api/drafts/clean", {"chapterId": cid, "keepCount": 50})

print("== 卷前言 ==")
call("PUT", f"/api/volumes/{vid}/preface", {"content": "卷前言内容"})
call("GET", f"/api/volumes/{vid}/preface-versions")

print("== 大纲 ==")
o = call("POST", "/api/outlines", {"projectId": pid, "title": "大纲节点1", "content": "内容"}, 201)
oid = o["id"]
call("GET", f"/api/outlines?projectId={pid}")
call("PUT", f"/api/outlines/{oid}", {"title": "大纲节点1·改"})
call("POST", f"/api/outlines/{oid}/link", {"chapterId": cid})
call("POST", "/api/outlines/reorder", {"projectId": pid, "orderedIds": [oid]})

print("== 角色 ==")
ch = call("POST", "/api/characters", {"projectId": pid, "name": "主角"}, 201)
chid = ch["id"]
call("GET", f"/api/characters?projectId={pid}")
f = call("POST", "/api/characters/fields", {"characterId": chid, "fieldName": "外貌", "content": "高"}, 201)
call("PUT", f"/api/characters/fields/{f['id']}", {"content": "很高"})
call("POST", f"/api/characters/{chid}/fields/reorder", {"orderedIds": [f["id"]]})
call("PUT", f"/api/characters/{chid}/appearances", {"appearances": [{"chapterId": cid, "note": "登场"}]})
call("GET", f"/api/characters/{chid}")

print("== 世界观 ==")
w = call("POST", "/api/world-settings", {"projectId": pid, "category": "地理", "title": "大陆"}, 201)
call("GET", f"/api/world-settings?projectId={pid}")
call("PUT", f"/api/world-settings/{w['id']}", {"content": "设定内容"})

print("== 灵感 ==")
i = call("POST", "/api/inspirations", {"projectId": pid, "title": "灵感1", "type": "inspiration"}, 201)
call("GET", f"/api/inspirations?projectId={pid}")
call("PUT", f"/api/inspirations/{i['id']}", {"content": "灵感内容"})

print("== 剧本模式 ==")
sp = call("POST", "/api/projects", {"title": "测试剧本", "projectType": "play"}, 201)
spid = sp["id"]
a = call("POST", "/api/acts", {"projectId": spid, "title": "第一幕"}, 201)
aid = a["id"]
call("GET", f"/api/acts?projectId={spid}")
sc = call("POST", "/api/scenes", {"actId": aid, "projectId": spid, "title": "第一场"}, 201)
scid = sc["id"]
call("GET", f"/api/scenes?actId={aid}")
call("PUT", f"/api/scenes/{scid}/characters", {"characterIds": []})
el = call("POST", "/api/elements", {"sceneId": scid, "elementType": "dialogue", "content": "台词"}, 201)
eid = el["id"]
call("GET", f"/api/elements?sceneId={scid}")
call("PUT", f"/api/elements/{eid}", {"content": "台词改"})
call("POST", "/api/elements/reorder", {"sceneId": scid, "parentId": None, "orderedIds": [eid]})
call("POST", f"/api/elements/{eid}/move", {"parentId": None})

print("== 乐谱（MuseScore） ==")
mel = call("POST", "/api/elements", {"sceneId": scid, "elementType": "song", "songTitle": "测试歌曲"}, 201)
meid = mel["id"]
info = call("GET", f"/api/score?projectId={spid}&elementId={meid}")
detect = call("GET", "/api/score/detect-path")
if detect and not detect.get("current"):
    # 无 MuseScore 环境：open 应返回 400 引导安装
    call("POST", "/api/score/open", {"projectId": spid, "elementId": meid, "songTitle": "测试歌曲"}, 400)
else:
    # 有 MuseScore 环境时不实际拉起 GUI，仅验证路径探测
    print("[OK ] 检测到 MuseScore，跳过 open 实测:", detect.get("current"))
call("POST", "/api/score/delete", {"projectId": spid, "elementId": meid})
fs = call("POST", "/api/floating-songs", {"projectId": spid, "songTitle": "游离测试歌"}, 201)
call("GET", f"/api/score?projectId={spid}&floatingSongId={fs['id']}")
call("POST", "/api/score/delete", {"projectId": spid, "floatingSongId": fs["id"]})

print("== 搜索/配置/导出/备份/回收站 ==")
import urllib.parse
call("GET", f"/api/search?projectId={pid}&keyword=" + urllib.parse.quote("测试"))
call("GET", "/api/config")
call("PUT", "/api/config", {"theme": "dark"})
import tempfile, os
tmp = tempfile.mkdtemp()
call("POST", "/api/export/txt", {"projectId": pid, "outputPath": os.path.join(tmp, "out.txt")})
call("POST", "/api/export/docx", {"projectId": pid, "outputPath": os.path.join(tmp, "out.docx")})
call("POST", "/api/backup", {})
call("GET", "/api/backup/db-path")
call("DELETE", f"/api/chapters/{cid}")
call("GET", "/api/recycle")
call("POST", "/api/recycle/restore", {"entityType": "chapter", "entityId": cid})
call("POST", "/api/recycle/clean")
call("DELETE", f"/api/projects/{spid}")

print()
if fails:
    print(f"!! 共 {len(fails)} 个失败：")
    for m, p, msg in fails:
        print(f"  {m} {p}: {msg}")
    sys.exit(1)
print("全部通过，无失败项")
