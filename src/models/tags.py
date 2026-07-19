from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime

from utils.database import Base


class Tags(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    unique_id = Column(String(16), unique=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    tags = Column(String, nullable=False, unique=True)
    is_exclude = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))