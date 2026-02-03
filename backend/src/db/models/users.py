from sqlalchemy import Column, Integer, String, DateTime, Boolean

from src.db.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    role = Column(String)
    name = Column(String)
    description = Column(String)
    pass_hash = Column(String)
    email = Column(String, unique=True)
    created = Column(DateTime)
    deleted = Column(DateTime)
    blocked = Column(Boolean)
    created_by = Column(Integer)
