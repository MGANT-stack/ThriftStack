from pathlib import Path
from utils.db import engine

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
SEED_PATH = BASE_DIR / "seed.sql"


def run_sql_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    with engine.begin() as conn:
        raw = conn.connection
        with raw.cursor() as cur:
            cur.execute(sql_script)


def initialize_database():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {SCHEMA_PATH}")

    run_sql_file(SCHEMA_PATH)

    if SEED_PATH.exists():
        run_sql_file(SEED_PATH)

    print("Database initialized successfully.")


if __name__ == "__main__":
    initialize_database()