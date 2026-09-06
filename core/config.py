from core.database import get_conn

DEFAULTS = {
    "autoSaveInterval": "300",
    "versionRetention": "50",
    "recycleRetentionDays": "30",
    "editorFontSize": "16",
    "theme": "light",
    "defaultExportPath": "",
}

def get_config():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_config").fetchall()
    config = dict(DEFAULTS)
    for r in rows:
        config[r["key"]] = r["value"]
    conn.close()
    return config

def set_config(fields):
    conn = get_conn()
    for k, v in fields.items():
        conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()
