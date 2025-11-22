from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List
import shutil
import os
from . import models, database
from .classifier import Classifier

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

    return FileResponse(path=db_file.filepath, filename=db_file.filename, media_type='application/octet-stream')

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
def get_files(category: str = None, search: str = None, sort_by: str = 'date', order: str = 'desc', db: Session = Depends(get_db)):
    query = db.query(models.FileMetadata)

    if category:
        query = query.filter(models.FileMetadata.category == category)

    if search:
        query = query.filter(models.FileMetadata.filename.contains(search))

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
    return [{"id": f.id, "filename": f.filename, "category": f.category, "size": f.size, "upload_date": f.upload_date} for f in files]
