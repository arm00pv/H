from sqlalchemy import Column, Integer, String, DateTime, BigInteger, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True) # e.g., 'google', 'dropbox', 'nextcloud'
    name = Column(String) # User friendly name
    config = Column(String) # JSON string of credentials/config
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

class FileMetadata(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String, index=True) # Removed unique=True to allow same path in different accounts
    category = Column(String, index=True)
    content_type = Column(String)
    tags = Column(String, default="")
    size = Column(BigInteger)
    upload_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    source = Column(String, default="local") # 'local', 'nextcloud', etc.
    cloud_account_id = Column(Integer, ForeignKey("cloud_accounts.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
