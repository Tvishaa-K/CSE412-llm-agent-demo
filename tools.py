from db import run_query

BLOCKED = [
    "insert", "update", "delete", "drop", "alter", "create",
    "truncate", "grant", "revoke", "copy",
]


def get_database_schema():
    """Return every table, its columns and types, plus foreign keys."""
    cols_sql = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    fk_sql = """
        SELECT conrelid::regclass AS table_name,
               pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE contype = 'f'
          AND connamespace = 'public'::regnamespace
        ORDER BY conrelid::regclass::text
    """

    _, col_rows = run_query(cols_sql, max_rows=500)
    _, fk_rows = run_query(fk_sql, max_rows=200)

    tables = {}
    for table, column, dtype in col_rows:
        tables.setdefault(table, []).append(f"{column} {dtype}")

    lines = []
    for table, columns in tables.items():
        lines.append(f"TABLE {table} ({', '.join(columns)})")

    for table, definition in fk_rows:
        lines.append(f"FK {table}: {definition}")

    return "\n".join(lines)


def is_safe_sql(sql):
    """Return (ok, reason). Only single SELECT or WITH statements pass."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False, "empty query"
    if ";" in cleaned:
        return False, "multiple statements are not allowed"

    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False, "only SELECT queries are allowed"

    words = lowered.replace("(", " ").replace(")", " ").split()
    for word in words:
        if word in BLOCKED:
            return False, f"'{word}' is not allowed"

    return True, ""


def execute_sql(sql, max_rows=100):
    """Run a read-only SELECT. Returns a printable string."""
    ok, reason = is_safe_sql(sql)
    if not ok:
        return f"REJECTED: {reason}"

    try:
        columns, rows = run_query(sql, max_rows=max_rows)
    except Exception as e:
        return f"ERROR: {e}"

    if not rows:
        return "No rows returned."

    lines = [" | ".join(columns)]
    for row in rows:
        lines.append(" | ".join(str(v) for v in row))
    lines.append(f"({len(rows)} rows)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_database_schema())
    print()
    print(execute_sql("SELECT roomid, floor, status FROM room LIMIT 5"))
    print()
    print(execute_sql("DELETE FROM room WHERE roomid = 1"))
