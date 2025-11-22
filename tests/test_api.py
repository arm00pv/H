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

def test_tags_update_and_filter():
    # Upload
    filename = "tagged_doc.txt"
    client.post("/upload/", files={'file': (filename, b"content", 'text/plain')})

    # Get file ID
    files = client.get("/files").json()
    file_id = files[0]["id"]

    # Update Tags
    new_tags = "important, work"
    res = client.patch(f"/files/{file_id}", json={"tags": new_tags})
    assert res.status_code == 200
    assert res.json()["tags"] == new_tags

    # Filter by Tag
    res = client.get("/files?tag=important")
    data = res.json()
    assert len(data) == 1
    assert data[0]["filename"] == filename

    res = client.get("/files?tag=personal")
    data = res.json()
    assert len(data) == 0

def test_content_type_storage():
    # Upload with specific mime type
    client.post("/upload/", files={'file': ("image.png", b"fakeimage", 'image/png')})

    files = client.get("/files").json()
    assert files[0]["content_type"] == "image/png"

    # Download should have correct header
    res = client.get(f"/download/{files[0]['id']}")
    assert res.headers["content-type"] == "image/png"

def test_rename_file():
    # Upload
    client.post("/upload/", files={'file': ("old.txt", b"content", 'text/plain')})
    file_id = client.get("/files").json()[0]["id"]

    # Rename
    res = client.put(f"/files/{file_id}/rename", json={"new_filename": "new.txt"})
    assert res.status_code == 200
    assert res.json()["filename"] == "new.txt"

    # Check DB
    db_file = client.get("/files").json()[0]
    assert db_file["filename"] == "new.txt"

    # Check Disk
    assert not os.path.exists("data/old.txt")
    assert os.path.exists("data/new.txt")

def test_batch_delete():
    # Upload 3 files
    ids = []
    for i in range(3):
        client.post("/upload/", files={'file': (f"file{i}.txt", b"content", 'text/plain')})
        files = client.get("/files").json()
        # Assuming the last one added is at the end or we find it by name
        ids.append(files[-1]["id"]) # This is risky if sort order changes, let's be specific

    # Get actual IDs map
    all_files = client.get("/files").json()
    target_ids = [f["id"] for f in all_files if f["filename"] in ["file0.txt", "file1.txt"]]

    # Delete 2 of them
    res = client.post("/files/delete-batch", json={"file_ids": target_ids})
    assert res.status_code == 200
    assert len(res.json()["deleted_ids"]) == 2

    # Verify
    remaining = client.get("/files").json()
    remaining_names = [f["filename"] for f in remaining]
    assert "file0.txt" not in remaining_names
    assert "file1.txt" not in remaining_names
    assert "file2.txt" in remaining_names

    # Check Disk
    assert not os.path.exists("data/file0.txt")
    assert os.path.exists("data/file2.txt")

def test_integration_workflow():
    # 1. Create Mock Integration
    config = "{}"
    res = client.post("/integrations", json={"provider": "mock", "name": "Test Cloud", "config": config})
    assert res.status_code == 200
    account_id = res.json()["id"]

    # 2. Sync
    res = client.post(f"/integrations/{account_id}/sync")
    assert res.status_code == 200
    assert res.json()["synced_files"] > 0

    # 3. Verify files in DB
    files = client.get("/files").json()
    cloud_files = [f for f in files if f["source"] == "mock"]
    assert len(cloud_files) > 0
    filenames = [f["filename"] for f in cloud_files]
    assert "mock_report.pdf" in filenames

    # 4. Delete Integration
    res = client.delete(f"/integrations/{account_id}")
    assert res.status_code == 200

    # 5. Verify files removed
    files = client.get("/files").json()
    cloud_files = [f for f in files if f["source"] == "mock"]
    assert len(cloud_files) == 0

def test_cloud_download_and_duplicates():
    # 1. Create TWO Mock Integrations
    config = "{}"
    res1 = client.post("/integrations", json={"provider": "mock", "name": "Cloud A", "config": config})
    id1 = res1.json()["id"]
    res2 = client.post("/integrations", json={"provider": "mock", "name": "Cloud B", "config": config})
    id2 = res2.json()["id"]

    # 2. Sync both (they have same file paths)
    client.post(f"/integrations/{id1}/sync")
    client.post(f"/integrations/{id2}/sync")

    # 3. Verify duplicates exist (same filename, different accounts)
    files = client.get("/files").json()
    mock_reports = [f for f in files if f["filename"] == "mock_report.pdf"]
    assert len(mock_reports) >= 2

    # 4. Test Download
    file_id = mock_reports[0]["id"]
    res = client.get(f"/download/{file_id}")
    if res.status_code != 200:
        print(res.json())
    assert res.status_code == 200
    assert b"%PDF" in res.content # Check for mock content
