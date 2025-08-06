from sqlalchemy import Column, String, ForeignKey, JSON, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .base import Base
from .vectorDbModels import SQLQuery, DDLStatement, DocumentationItem


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    
    chats = relationship("Chat", back_populates="project")
    # Relationships
    sql_queries = relationship("SQLQuery", back_populates="project", cascade="all, delete-orphan")
    ddl_statements = relationship("DDLStatement", back_populates="project", cascade="all, delete-orphan")
    documentation_items = relationship("DocumentationItem", back_populates="project", cascade="all, delete-orphan")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    query_history = Column(JSON, nullable=True)  # Store conversation history
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    feedback_enabled = Column(Boolean, default=None, nullable=True)  # Flag to enable/disable feedback
    
    project = relationship("Project", back_populates="chats")