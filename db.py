import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "/tmp"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "hotel_db"),
    "user": os.getenv("DB_USER", "agent_ro"),
    "password": os.getenv("DB_PASSWORD", ""),
}

STATEMENT_TIMEOUT_MS = 5000


def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (STATEMENT_TIMEOUT_MS,))
    return conn


def run_query(sql, max_rows=100):
    """Run a SELECT and return (columns, rows). Raises on error."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows)
        return columns, rows
    finally:
        conn.close()


if __name__ == "__main__":
    cols, rows = run_query("SELECT count(*) FROM room")
    print(cols)
    print(rows)
