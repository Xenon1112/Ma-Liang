import shutil
import os
from datetime import datetime
from database import get_db_path, get_conn

def create_backup(backup_path=None):
    src = get_db_path()
    if not os.path.exists(src):
        raise FileNotFoundError("Database file not found")
    if not backup_path:
        home = os.path.expanduser("~")
        # 精确到秒，避免同日重复备份互相覆盖
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(home, f"novel-writer-backup-{ts}.db")
    # WAL 模式下先 checkpoint，把 wal 中已提交的数据写回主文件再复制
    conn = get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copy2(src, backup_path)
    return {"filePath": backup_path}

def restore_backup(backup_file_path):
    if not os.path.exists(backup_file_path):
        raise FileNotFoundError("Backup file not found")
    dest = get_db_path()
    # 先 checkpoint 并关闭连接，再随覆盖清理旧 WAL/SHM，避免重启后旧日志被重放到新库
    conn = get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copy2(backup_file_path, dest)
    for suffix in ("-wal", "-shm"):
        sidecar = dest + suffix
        if os.path.exists(sidecar):
            os.remove(sidecar)
    return {"success": True, "message": "备份已恢复，请重启应用"}

def get_backup_info(backup_file_path):
    if not os.path.exists(backup_file_path):
        raise FileNotFoundError("Backup file not found")
    stat = os.stat(backup_file_path)
    return {
        "filePath": backup_file_path,
        "fileSize": stat.st_size,
        "date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }

def list_backups():
    # 列出用户目录下由本应用创建的备份文件（与 create_backup 的命名规则一致），新的在前
    home = os.path.expanduser("~")
    items = []
    for name in os.listdir(home):
        if name.startswith("novel-writer-backup-") and name.endswith(".db"):
            path = os.path.join(home, name)
            stat = os.stat(path)
            items.append({
                "filePath": path,
                "fileSize": stat.st_size,
                "date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    items.sort(key=lambda x: x["date"], reverse=True)
    return items
