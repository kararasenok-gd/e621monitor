from sqlalchemy import Column, Integer, String

from utils.database import Base


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    lang = Column(String(3), nullable=False, default="en")