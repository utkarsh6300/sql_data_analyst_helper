from sqlalchemy import Column, String, Text, Integer, ForeignKey, ARRAY, Float
from sqlalchemy.orm import relationship
from .base import Base

class SQLQuery(Base):
    """SQLAlchemy model for storing SQL queries with project separation"""
    __tablename__ = 'sql_queries'
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    question = Column(Text, nullable=False)
    sql = Column(Text, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    sql_metadata = Column(Text)  # JSON string
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="sql_queries")

class DDLStatement(Base):
    """SQLAlchemy model for storing DDL statements with project separation"""
    __tablename__ = 'ddl_statements'
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    ddl = Column(Text, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    ddl_metadata = Column(Text)  # JSON string
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="ddl_statements")

class DocumentationItem(Base):
    """SQLAlchemy model for storing documentation with project separation"""
    __tablename__ = 'documentation_items'
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    documentation = Column(Text, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    documentation_metadata = Column(Text)  # JSON string
    created_at = Column(Integer)  # Unix timestamp
    
    # Relationship
    project = relationship("Project", back_populates="documentation_items")