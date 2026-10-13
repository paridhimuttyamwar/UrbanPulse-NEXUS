import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from database.connection import get_db_cursor

with get_db_cursor(commit=False) as cursor:
    cursor.execute("SHOW TABLES;")
    tables = [list(r.values())[0] for r in cursor.fetchall()]
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) AS c FROM {t};")
        cnt = cursor.fetchone()["c"]
        print(f"| {t} | {cnt} |")
