import shutil
import os
from datetime import datetime
from database import get_db_path

def create_backup(backup_path=None):
    src = get_db_path()
    if not os.path.exists(src):
        raise FileNotFoundError("Database file not found")
    if not backup_path:
        home = os.path.expanduser("~")
        ts = datetime.now().strftime("%Y-%m-%d")
        backup_path = os.path.join(home, f"novel-writer-backup-{ts}.db")
    shutil.copy2(src, backup_path)
    return {"filePath": backup_path}

def restore_backup(backup_file_path):
    if not os.path.exists(backup_file_path):
        raise FileNotFoundError("Backup file not found")
    dest = get_db_path()
    shutil.copy2(backup_file_path, dest)
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
