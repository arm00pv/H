import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from backend.main import app, get_db
from backend.database import Base
import os

# Setup in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    yield
    # Drop tables
    Base.metadata.drop_all(bind=engine)
    # Clean up any files created in data/
    # In a real scenario, we might want to use a temporary directory for file storage too.
    if os.path.exists("data/test_doc.txt"):
        os.remove("data/test_doc.txt")

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_upload_file():
    # Create a dummy file
    filename = "test_doc.txt"
    content = b"This is a test document."

    # Ensure the file doesn't exist before test to avoid side effects from previous failed runs
    if os.path.exists(f"data/{filename}"):
        os.remove(f"data/{filename}")

    files = {'file': (filename, content, 'text/plain')}
    response = client.post("/upload/", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Document"
    assert "id" in data

    # Verify file exists
    assert os.path.exists(f"data/{filename}")

def test_stats():
    # Populate some data
    db = TestingSessionLocal()
    # ... add data if needed, or just rely on previous tests if not using clean db per test
    # But we are using a clean DB per test (or we should be).
    # With the current setup_teardown, we drop tables after each test yield?
    # Wait, autouse=True with yield does setup before and teardown after each test function.
    # So the DB is empty here.

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_files"] == 0

def test_files_list():
    response = client.get("/files")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
