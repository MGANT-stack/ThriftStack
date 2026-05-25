from pathlib import Path

from sqlalchemy import text

from utils.db import engine

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
SEED_PATH = BASE_DIR / "seed.sql"


def run_sql_file(file_path):
    sql_script = file_path.read_text()

    statements = [
        stmt.strip()
        for stmt in sql_script.split(";")
        if stmt.strip()
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def initialize_database():
    run_sql_file(SCHEMA_PATH)
    run_sql_file(SEED_PATH)

    print("Database initialized successfully.")


if __name__ == "__main__":
    initialize_database()