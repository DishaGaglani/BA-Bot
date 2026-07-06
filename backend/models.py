from sqlalchemy import Column, Integer, Text
from database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(Text)