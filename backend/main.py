from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List
import shutil
import os
from . import models, database
from .classifier import Classifier
from pydantic import BaseModel

# Ensure data directory exists before DB creation (if using file-based SQLite inside it)
os.makedirs("data", exist_ok=True)

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()
classifier = Classifier()

# Mount the data directory so we can serve files if needed (optional, careful with security)
# app.mount("/files", StaticFiles(directory="data"), name="files")

# Mount frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return FileResponse('frontend/index.html')

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Sanitize filename
    filename = os.path.basename(file.filename)
    file_location = f"data/{filename}"

    # Handle duplicate filenames by appending a counter
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(file_location):
        file_location = f"data/{base}_{counter}{ext}"
        counter += 1

    # Save the file
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)

    # Get file size
    file_size = os.path.getsize(file_location)

    # Classify
    category = classifier.classify(file.filename, file.content_type)

    # Save metadata
    db_file = models.FileMetadata(
        filename=os.path.basename(file_location),
        filepath=file_location,
        category=category,
        content_type=file.content_type,
        size=file_size
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return {"info": f"file '{file.filename}' saved at '{file_location}'", "category": category, "id": db_file.id}

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    files = db.query(models.FileMetadata).all()

    category_counts = {}
    total_size = 0

    for file in files:
        cat = file.category
        category_counts[cat] = category_counts.get(cat, 0) + 1
        total_size += file.size

    return {
        "category_counts": category_counts,
        "total_files": len(files),
        "total_size": total_size
    }

@app.get("/download/{file_id}")
def download_file(file_id: int, db: Session = Depends(get_db)):
    db_file = db.query(models.FileMetadata).filter(models.FileMetadata.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(db_file.filepath):
        raise HTTPException(status_code=404, detail="File on disk not found")

    media_type = db_file.content_type or 'application/octet-stream'
    return FileResponse(path=db_file.filepath, filename=db_file.filename, media_type=media_type)

class TagUpdate(BaseModel):
    tags: str

@app.patch("/files/{file_id}")
def update_file_tags(file_id: int, tag_update: TagUpdate, db: Session = Depends(get_db)):
    db_file = db.query(models.FileMetadata).filter(models.FileMetadata.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    db_file.tags = tag_update.tags
    db.commit()
    db.refresh(db_file)
    return {"id": db_file.id, "tags": db_file.tags}

class RenameRequest(BaseModel):
    new_filename: str

@app.put("/files/{file_id}/rename")
def rename_file(file_id: int, request: RenameRequest, db: Session = Depends(get_db)):
    db_file = db.query(models.FileMetadata).filter(models.FileMetadata.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Sanitize new filename
    new_filename = os.path.basename(request.new_filename)
    if not new_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Determine new path
    old_path = db_file.filepath
    dir_name = os.path.dirname(old_path)
    new_path = os.path.join(dir_name, new_filename)

    # Check if new path exists
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="File with this name already exists")

    # Rename on disk
    try:
        os.rename(old_path, new_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not rename file: {str(e)}")

    # Update DB
    db_file.filename = new_filename
    db_file.filepath = new_path
    db.commit()
    db.refresh(db_file)

    return {"id": db_file.id, "filename": db_file.filename}

class BatchDeleteRequest(BaseModel):
    file_ids: List[int]

@app.post("/files/delete-batch")
def delete_batch_files(request: BatchDeleteRequest, db: Session = Depends(get_db)):
    files_to_delete = db.query(models.FileMetadata).filter(models.FileMetadata.id.in_(request.file_ids)).all()

    deleted_ids = []
    for db_file in files_to_delete:
        # Remove from disk
        if os.path.exists(db_file.filepath):
            try:
                os.remove(db_file.filepath)
            except OSError:
                continue # Skip if cannot delete, maybe log it

        # Remove from DB
        db.delete(db_file)
        deleted_ids.append(db_file.id)

    db.commit()

    return {"deleted_ids": deleted_ids}

@app.delete("/files/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db)):
    db_file = db.query(models.FileMetadata).filter(models.FileMetadata.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from disk
    if os.path.exists(db_file.filepath):
        os.remove(db_file.filepath)

    # Remove from DB
    db.delete(db_file)
    db.commit()

    return {"detail": "File deleted successfully"}

@app.get("/files")
def get_files(category: str = None, search: str = None, tag: str = None, sort_by: str = 'date', order: str = 'desc', db: Session = Depends(get_db)):
    query = db.query(models.FileMetadata)

    if category:
        query = query.filter(models.FileMetadata.category == category)

    if search:
        query = query.filter(models.FileMetadata.filename.contains(search))

    if tag:
        query = query.filter(models.FileMetadata.tags.contains(tag))

    if sort_by == 'size':
        if order == 'asc':
            query = query.order_by(models.FileMetadata.size.asc())
        else:
            query = query.order_by(models.FileMetadata.size.desc())
    else: # date
        if order == 'asc':
            query = query.order_by(models.FileMetadata.upload_date.asc())
        else:
            query = query.order_by(models.FileMetadata.upload_date.desc())

    files = query.all()
    return [{
        "id": f.id,
        "filename": f.filename,
        "category": f.category,
        "size": f.size,
        "upload_date": f.upload_date,
        "tags": f.tags,
        "content_type": f.content_type
    } for f in files]
