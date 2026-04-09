from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "warehouse.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
SEED_PATH = BASE_DIR / "seed.sql"


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def run_sql_file(conn, file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        sql_script = file.read()
    conn.executescript(sql_script)


def initialize_database():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {SCHEMA_PATH}")

    conn = get_connection()

    try:
        run_sql_file(conn, SCHEMA_PATH)

        if SEED_PATH.exists():
            run_sql_file(conn, SEED_PATH)

        conn.commit()
        print("Database initialized successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Database initialization failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    initialize_database()

if __name__ == "__main__":
    initialize_database()