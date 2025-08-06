from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import schemas.schemas as schemas
from db.database import get_db
from services.project_service import ProjectService
from services.vector_service import VectorService
from vectorDB.factory import VectorStoreFactory

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project"""
    return ProjectService.create_project(db, project)

@router.get("/", response_model=List[schemas.Project])
def get_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all projects with pagination"""
    return ProjectService.get_projects(db, skip, limit)

@router.get("/{project_id}", response_model=schemas.Project)
def get_project(project_id: int, db: Session = Depends(get_db)):
    """Get a specific project by ID"""
    return ProjectService.get_project(db, project_id)

@router.post("/{project_id}/documentation")
def update_documentation(project_id: int, request: schemas.DocumentationRequest, db: Session = Depends(get_db)):
    """Update project documentation"""
    return ProjectService.update_documentation(db, project_id, request)

@router.post("/{project_id}/sample-queries")
def add_sample_queries(project_id: int, request: schemas.SampleQueriesRequest, db: Session = Depends(get_db)):
    """Add sample queries to a project"""
    return ProjectService.add_sample_queries(db, project_id, request)

@router.post("/{project_id}/schema")
def add_ddl(project_id: int, request: schemas.SchemaRequest, db: Session = Depends(get_db)):
    """Add DDL schema to a project"""
    return ProjectService.add_ddl(db, project_id, request)
