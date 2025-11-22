import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import shutil

# Set env var BEFORE importing backend.main (which imports database)
TEST_DB_FILE = "/tmp/datavault_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"

from backend.main import app
import backend.database

client = TestClient(app)

@pytest.fixture(scope="function", autouse=True)
def setup_teardown(tmp_path):
    # Ensure clean state
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except:
            pass

    # Create tables using the engine from the app
    backend.database.Base.metadata.create_all(bind=backend.database.engine)

    # Setup data dir
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)

    yield

    os.chdir(original_cwd)
    backend.database.engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except:
            pass

@pytest.fixture
def auth_headers():
    # Create user and return headers
    res = client.post("/auth/register", json={"email": "test@test.com", "password": "password"})
    if res.status_code != 200:
        # If it fails, maybe user exists (should not if teardown works)
        pass

    res = client.post("/auth/login", json={"email": "test@test.com", "password": "password"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_read_root():
    os.makedirs("frontend", exist_ok=True)
    with open("frontend/index.html", "w") as f:
        f.write("<html></html>")
    response = client.get("/")
    assert response.status_code == 200

def test_upload_file(auth_headers):
    filename = "test_doc.txt"
    files = {'file': (filename, b"content", 'text/plain')}
    response = client.post("/upload/", files=files, headers=auth_headers)
    assert response.status_code == 200
    assert os.path.exists(f"data/{filename}")

def test_stats(auth_headers):
    response = client.get("/stats", headers=auth_headers)
    assert response.status_code == 200

def test_files_list(auth_headers):
    response = client.get("/files", headers=auth_headers)
    assert response.status_code == 200

def test_download_and_delete(auth_headers):
    filename = "test_doc.txt"
    client.post("/upload/", files={'file': (filename, b"content", 'text/plain')}, headers=auth_headers)
    files = client.get("/files", headers=auth_headers).json()
    file_id = files[0]["id"]

    res = client.get(f"/download/{file_id}", headers=auth_headers)
    assert res.status_code == 200

    res = client.delete(f"/files/{file_id}", headers=auth_headers)
    assert res.status_code == 200

def test_search_and_sort(auth_headers):
    client.post("/upload/", files={'file': ("zebra.txt", b"Z", 'text/plain')}, headers=auth_headers)
    client.post("/upload/", files={'file': ("apple.txt", b"A", 'text/plain')}, headers=auth_headers)

    res = client.get("/files?search=apple", headers=auth_headers)
    assert len(res.json()) == 1
    assert res.json()[0]["filename"] == "apple.txt"

def test_tags_update_and_filter(auth_headers):
    client.post("/upload/", files={'file': ("tagged.txt", b"C", 'text/plain')}, headers=auth_headers)
    file_id = client.get("/files", headers=auth_headers).json()[0]["id"]

    client.patch(f"/files/{file_id}", json={"tags": "important"}, headers=auth_headers)
    res = client.get("/files?tag=important", headers=auth_headers)
    assert len(res.json()) == 1

def test_content_type_storage(auth_headers):
    client.post("/upload/", files={'file': ("img.png", b"img", 'image/png')}, headers=auth_headers)
    file = client.get("/files", headers=auth_headers).json()[0]
    assert file["content_type"] == "image/png"

def test_rename_file(auth_headers):
    client.post("/upload/", files={'file': ("old.txt", b"C", 'text/plain')}, headers=auth_headers)
    file_id = client.get("/files", headers=auth_headers).json()[0]["id"]

    res = client.put(f"/files/{file_id}/rename", json={"new_filename": "new.txt"}, headers=auth_headers)
    assert res.status_code == 200
    assert os.path.exists("data/new.txt")

def test_batch_delete(auth_headers):
    client.post("/upload/", files={'file': ("f1.txt", b"C", 'text/plain')}, headers=auth_headers)
    client.post("/upload/", files={'file': ("f2.txt", b"C", 'text/plain')}, headers=auth_headers)

    files = client.get("/files", headers=auth_headers).json()
    ids = [f["id"] for f in files]

    res = client.post("/files/delete-batch", json={"file_ids": ids}, headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()["deleted_ids"]) == 2

def test_integration_workflow(auth_headers):
    config = "{}"
    res = client.post("/integrations", json={"provider": "mock", "name": "Cloud", "config": config}, headers=auth_headers)
    assert res.status_code == 200
    acc_id = res.json()["id"]

    res = client.post(f"/integrations/{acc_id}/sync", headers=auth_headers)
    assert res.status_code == 200

    files = client.get("/files", headers=auth_headers).json()
    assert any(f["source"] == "mock" for f in files)

    client.delete(f"/integrations/{acc_id}", headers=auth_headers)
    files = client.get("/files", headers=auth_headers).json()
    assert not any(f["source"] == "mock" for f in files)

def test_cloud_download_and_duplicates(auth_headers):
    res1 = client.post("/integrations", json={"provider": "mock", "name": "A", "config": "{}"}, headers=auth_headers)
    id1 = res1.json()["id"]
    res2 = client.post("/integrations", json={"provider": "mock", "name": "B", "config": "{}"}, headers=auth_headers)
    id2 = res2.json()["id"]

    client.post(f"/integrations/{id1}/sync", headers=auth_headers)
    client.post(f"/integrations/{id2}/sync", headers=auth_headers)

    files = client.get("/files", headers=auth_headers).json()
    mock_files = [f for f in files if f["filename"] == "mock_report.pdf"]
    assert len(mock_files) >= 2

    res = client.get(f"/download/{mock_files[0]['id']}", headers=auth_headers)
    assert res.status_code == 200

def test_auth_flow():
    # Use unique email
    email = "flow@user.com"
    res = client.post("/auth/register", json={"email": email, "password": "pw"})
    if res.status_code != 200 and res.status_code != 400:
         print(f"Auth flow register failed: {res.json()}")

    res = client.post("/auth/login", json={"email": email, "password": "pw"})
    assert res.status_code == 200
    token = res.json()["access_token"]

    res = client.get("/files", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    res = client.get("/files")
    assert res.status_code == 401
