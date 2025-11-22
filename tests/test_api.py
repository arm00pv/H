import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from backend.main import app, get_db
from backend.database import Base
import os
import shutil
from unittest.mock import patch

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

# Use a temporary directory for file uploads during tests
@pytest.fixture(scope="function", autouse=True)
def setup_teardown(tmp_path):
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create a temporary directory for data
    d = tmp_path / "data"
    d.mkdir()

    # Patch the 'data' directory path in the application (if it was hardcoded)
    # But since the app uses string literals "data/...", we can't easily patch it
    # without changing the app code to use a config.
    # Instead, we will change the CWD to the tmp_path so "data/" resolves to our tmp dir.
    # OR we can just mock os.path and open calls, but that's messy.
    # Best approach: change CWD.

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    # Re-create data dir in the new CWD just in case
    os.makedirs("data", exist_ok=True)

    yield

    # Drop tables
    Base.metadata.drop_all(bind=engine)

    # Restore CWD
    os.chdir(original_cwd)

def test_read_root():
    # We need to ensure frontend/index.html exists relative to tmp_path or mock it
    # Since we changed CWD, the app won't find 'frontend/index.html' unless we copy it
    # or patch FileResponse.
    # Let's mock FileResponse or just copy the frontend dir.
    os.makedirs("frontend", exist_ok=True)
    with open("frontend/index.html", "w") as f:
        f.write("<html></html>")

    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_upload_file():
    # Create a dummy file
    filename = "test_doc.txt"
    content = b"This is a test document."

    files = {'file': (filename, content, 'text/plain')}
    response = client.post("/upload/", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Document"
    assert "id" in data

    # Verify file exists in our tmp data dir
    assert os.path.exists(f"data/{filename}")

def test_stats():
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_files"] == 0

def test_files_list():
    response = client.get("/files")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_download_and_delete():
    # 1. Upload
    filename = "test_doc.txt"
    content = b"This is a test document."
    files = {'file': (filename, content, 'text/plain')}
    upload_res = client.post("/upload/", files=files)
    file_id = upload_res.json()["id"]

    # 2. Download
    download_res = client.get(f"/download/{file_id}")
    assert download_res.status_code == 200
    assert download_res.content == content

    # 3. Delete
    delete_res = client.delete(f"/files/{file_id}")
    assert delete_res.status_code == 200

    # 4. Verify Deletion
    # Check DB
    get_res = client.get("/files")
    files_list = get_res.json()
    assert len([f for f in files_list if f["id"] == file_id]) == 0
    # Check Disk
    assert not os.path.exists(f"data/{filename}")

def test_search_and_sort():
    # Upload A (Zebra)
    client.post("/upload/", files={'file': ("zebra.txt", b"Z", 'text/plain')})
    # Upload B (Apple)
    client.post("/upload/", files={'file': ("apple.txt", b"A", 'text/plain')})

    # Test Search
    res = client.get("/files?search=apple")
    data = res.json()
    assert len(data) == 1
    assert data[0]["filename"] == "apple.txt"

    # Test Sort
    res = client.get("/files?sort_by=size&order=asc")
    assert res.status_code == 200
