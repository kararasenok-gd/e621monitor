from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from datetime import datetime, timezone
from utils.database import Base


class Art(Base):
    __tablename__ = "arts"

    id = Column(Integer, primary_key=True)
    source_id = Column(String, unique=True, index=True)
    url = Column(String, nullable=False)
    sent = Column(Boolean, default=False)
    sent_to = Column(JSON, default=list, nullable=False)
    sent_to_channel = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    extra = Column(JSON)