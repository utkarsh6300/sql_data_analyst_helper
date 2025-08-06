from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import schemas.schemas as schemas
from db.database import get_db
from services.project_service import ProjectService
from services.vector_service import VectorService
from vectorDB.factory import VectorStoreFactory
import uuid

router = APIRouter(prefix="/projects", tags=["projects"])

# Create a single instance of ProjectService
project_service = ProjectService()

@router.post("/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project"""
    return project_service.create_project(db, project)

@router.get("/", response_model=List[schemas.Project])
def get_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all projects with pagination"""
    return project_service.get_projects(db, skip, limit)

@router.get("/{project_id}", response_model=schemas.ProjectDetail)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific project by ID"""
    return project_service.get_project(db, project_id)

@router.delete("/{project_id}")
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a project and all its associated data"""
    return project_service.delete_project(db, project_id)

# Routes for adding multiple items
@router.post("/{project_id}/documentation-items")
def add_documentation_items(project_id: uuid.UUID, request: schemas.DocumentationListRequest, db: Session = Depends(get_db)):
    """Add multiple documentation items to a project"""
    return project_service.add_documentation_items(db, project_id, request)

@router.post("/{project_id}/question-sql-pairs")
def add_question_sql_pairs(project_id: uuid.UUID, request: schemas.QuestionSQLListRequest, db: Session = Depends(get_db)):
    """Add multiple question-SQL pairs to a project"""
    return project_service.add_question_sql_pairs(db, project_id, request)

@router.post("/{project_id}/ddl-statements")
def add_ddl_statements(project_id: uuid.UUID, request: schemas.DDLListRequest, db: Session = Depends(get_db)):
    """Add multiple DDL statements to a project"""
    return project_service.add_ddl_statements(db, project_id, request)

# Routes for deleting individual items
@router.delete("/documentation/{item_id}", response_model=schemas.DeleteResponse)
def delete_documentation_item(item_id: str):
    """Delete a specific documentation item by ID"""
    return project_service.delete_documentation_item(item_id)

@router.delete("/question-sql/{item_id}", response_model=schemas.DeleteResponse)
def delete_question_sql_item(item_id: str):
    """Delete a specific question-SQL pair by ID"""
    return project_service.delete_question_sql_item(item_id)

@router.delete("/ddl/{item_id}", response_model=schemas.DeleteResponse)
def delete_ddl_item(item_id: str):
    """Delete a specific DDL statement by ID"""
    return project_service.delete_ddl_item(item_id)
