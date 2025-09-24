import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DB_URL")

with psycopg.connect(DB_URL, sslmode="disable") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
        print(cur.fetchone())  # (1,)
