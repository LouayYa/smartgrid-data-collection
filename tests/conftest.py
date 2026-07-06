import os

import pytest

# Point the app at a throwaway SQLite DB before app.database (which reads
# DATABASE_URL and connects at import time) ever gets imported. load_dotenv()
# does not override an already-set env var, so this wins over .env.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, SessionLocal, get_db, engine
from app.events import get_publisher


class FakePublisher:
    """In-memory stand-in for the Kafka producer: records what was published."""

    def __init__(self):
        self.published = []

    def publish(self, readings):
        items = list(readings)
        self.published.extend(items)
        return len(items)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def fake_publisher():
    return FakePublisher()


@pytest.fixture(scope="function")
def client(db, fake_publisher):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_publisher] = lambda: fake_publisher
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
