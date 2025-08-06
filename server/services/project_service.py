from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List
import models.models as models
import schemas.schemas as schemas
from services.vector_service import VectorService
from db.repositories import ProjectRepository

class ProjectService:
    @staticmethod
    def create_project(db: Session, project: schemas.ProjectCreate):
        """Create a new project"""
        project_data = project.model_dump(by_alias=False)
        return ProjectRepository.create_project(db, **project_data)

    @staticmethod
    def get_projects(db: Session, skip: int = 0, limit: int = 100):
        """Get all projects with chat count"""
        return ProjectRepository.get_all_projects(db, skip, limit)

    @staticmethod
    def get_project(db: Session, project_id: int):
        """Get a specific project by ID"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @staticmethod
    def update_documentation(db: Session, project_id: int, request: schemas.DocumentationRequest):
        """Update project documentation"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Store in both SQL database and vector store
        ProjectRepository.update_project(db, project, documentation=request.documentation)
        
        # Store in ChromaDB
        print(f"💾 Storing documentation in vector store for project {project_id}...")
        doc_id = VectorService.add_documentation(request.documentation, project_id=str(project_id))
        if not doc_id:
            raise HTTPException(status_code=500, detail="Failed to store documentation in vector database")
        
        print(f"✅ Documentation stored successfully with ID: {doc_id}")
        return {"status": "success", "vector_store_id": doc_id}

    @staticmethod
    def add_sample_queries(db: Session, project_id: int, request: schemas.SampleQueriesRequest):
        """Add sample queries to a project"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Store in SQL database
        current_samples = project.sample_queries or {}
        current_samples.update(request.sample_queries)
        ProjectRepository.update_project(db, project, sample_queries=current_samples)
        
        # Store in ChromaDB
        print(f"💾 Storing {len(request.sample_queries)} sample queries in vector store for project {project_id}...")
        stored_ids = []
        for question, sql in request.sample_queries.items():
            print(f"   Storing Q&A pair: '{question[:50]}...' -> '{sql[:50]}...'")
            sql_id = VectorService.add_question_sql(question, sql, project_id=str(project_id))
            if sql_id:
                stored_ids.append(sql_id)
                print(f"   ✅ Stored with ID: {sql_id}")
            else:
                print(f"   ❌ Failed to store Q&A pair")
        
        if not stored_ids:
            raise HTTPException(status_code=500, detail="Failed to store sample queries in vector database")
        
        print(f"✅ Successfully stored {len(stored_ids)} sample queries in vector store")
        return {"status": "success", "vector_store_ids": stored_ids}

    @staticmethod
    def add_ddl(db: Session, project_id: int, request: schemas.SchemaRequest):
        """Add DDL schema to a project"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Store in both SQL database and vector store
        ProjectRepository.update_project(db, project, schema=request.db_schema)
        
        # Store in ChromaDB
        print(f"💾 Storing DDL in vector store for project {project_id}...")
        ddl_id = VectorService.add_ddl(request.db_schema, project_id=str(project_id))
        if not ddl_id:
            raise HTTPException(status_code=500, detail="Failed to store DDL in vector database")
        
        print(f"✅ DDL stored successfully with ID: {ddl_id}")
        return {"status": "success", "vector_store_id": ddl_id} 