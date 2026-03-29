import sqlite3
import os

db_path = 'netmanager.db'
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found")
    exit(1)

con = sqlite3.connect(db_path)
cur = con.cursor()

columns = ['traffic_in', 'traffic_out']
for col in columns:
    try:
        cur.execute(f"ALTER TABLE system_metrics ADD COLUMN {col} FLOAT DEFAULT 0.0")
        print(f"Added {col} column")
    except Exception as e:
        print(f"{col} error (maybe exists): {e}")

con.commit()
con.close()
