from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Text, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base

class SQLQuery(Base):
    """SQLAlchemy model for storing SQL queries with project separation"""
    __tablename__ = 'sql_queries'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False, index=True)
    question = Column(Text, nullable=False)
    sql = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)  # Will be populated by vector service
    sql_metadata = Column(JSON, nullable=True)  # JSON object for metadata
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="sql_queries")

class DDLStatement(Base):
    """SQLAlchemy model for storing DDL statements with project separation"""
    __tablename__ = 'ddl_statements'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False, index=True)
    ddl = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)  # Will be populated by vector service
    ddl_metadata = Column(JSON, nullable=True)  # JSON object for metadata
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="ddl_statements")

class DocumentationItem(Base):
    """SQLAlchemy model for storing documentation with project separation"""
    __tablename__ = 'documentation_items'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id'), nullable=False, index=True)
    documentation = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)  # Will be populated by vector service
    documentation_metadata = Column(JSON, nullable=True)  # JSON object for metadata
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="documentation_items")