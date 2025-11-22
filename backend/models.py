from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from .database import Base
from datetime import datetime, timezone

class FileMetadata(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String, unique=True)
    category = Column(String, index=True)
    size = Column(BigInteger)
    upload_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
