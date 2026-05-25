import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

DATABASE_URL = DATABASE_URL.replace(
    "postgresql://",
    "postgresql+psycopg://",
    1
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

def get_connection():
    return engine.connect()