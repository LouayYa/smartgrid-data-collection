import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

# Fall back to a local SQLite file so the service can run without any env setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data_collection.db")

SSL_ARGS = {}
if "mysql" in DATABASE_URL:
    import ssl
    ssl_ctx = ssl.create_default_context()
    SSL_ARGS = {"connect_args": {"ssl": ssl_ctx}}

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, **SSL_ARGS)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
