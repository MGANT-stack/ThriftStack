import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///warehouse.db"
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

def get_connection():
    return engine.connect()