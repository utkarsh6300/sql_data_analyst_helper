from sqlalchemy import Column, Integer, String, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    schema = Column(Text, nullable=False)  # Database schema
    documentation = Column(Text, nullable=True)  # Project documentation
    sample_queries = Column(JSON, nullable=True)  # Sample text-to-SQL mappings
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    
    chats = relationship("Chat", back_populates="project")
    # Relationships
    sql_queries = relationship("SQLQuery", back_populates="project", cascade="all, delete-orphan")
    ddl_statements = relationship("DDLStatement", back_populates="project", cascade="all, delete-orphan")
    documentation_items = relationship("DocumentationItem", back_populates="project", cascade="all, delete-orphan")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    query_history = Column(JSON, nullable=True)  # Store conversation history
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    feedback_enabled = Column(Boolean, default=None, nullable=True)  # Flag to enable/disable feedback
    
    project = relationship("Project", back_populates="chats")