from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
import models.models as models
import schemas.schemas as schemas
from services.vector_service import VectorService
from db.repositories import ProjectRepository

class ProjectService:
    @staticmethod
    def create_project(db: Session, project: schemas.ProjectCreate):
        """Create a new project"""
        project_data = project.model_dump(by_alias=False)
        created_project = ProjectRepository.create_project(db, **project_data)
        
        # Create project in vector store
        print(f"💾 Creating project {created_project.id} in vector store...")
        try:
            # Initialize project in vector store (if needed)
            # This depends on your vector store implementation
            print(f"✅ Project {created_project.id} created successfully in vector store")
        except Exception as e:
            print(f"⚠️ Warning: Failed to create project in vector store: {e}")
            # Don't fail the entire operation if vector store fails
        
        return created_project

    @staticmethod
    def get_projects(db: Session, skip: int = 0, limit: int = 100):
        """Get all projects with chat count"""
        return ProjectRepository.get_all_projects(db, skip, limit)

    @staticmethod
    def get_project(db: Session, project_id: uuid.UUID):
        """Get a specific project by ID with all related data"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get related data from vector store
        try:
            documentation_items = VectorService.get_all_documentation(str(project_id))
            question_sql_pairs = VectorService.get_all_question_sql(str(project_id))
            ddl_statements = VectorService.get_all_ddl(str(project_id))
        except Exception as e:
            print(f"⚠️ Warning: Failed to retrieve vector data for project {project_id}: {e}")
            documentation_items = []
            question_sql_pairs = []
            ddl_statements = []
        
        # Create project detail response
        project_detail = schemas.ProjectDetail(
            id=project.id,
            name=project.name,
            created_at=project.created_at,
            chatsCount=ProjectRepository.count_chats_by_project(db, project_id),
            documentation_items=documentation_items,
            question_sql_pairs=question_sql_pairs,
            ddl_statements=ddl_statements
        )
        
        return project_detail

    @staticmethod
    def delete_project(db: Session, project_id: uuid.UUID):
        """Delete a project and all its associated data"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Delete from vector store first
        print(f"🗑️ Deleting project {project_id} from vector store...")
        try:
            VectorService.delete_project(str(project_id))
            print(f"✅ Successfully deleted project {project_id} from vector store")
        except Exception as e:
            print(f"⚠️ Warning: Failed to delete project from vector store: {e}")
            # Continue with SQL deletion even if vector store fails
        
        # Delete associated chats first (due to foreign key constraints)
        from db.repositories import ChatRepository
        chats = ChatRepository.get_chats_by_project(db, project_id)
        for chat in chats:
            ChatRepository.delete_chat(db, chat)
        print(f"🗑️ Deleted {len(chats)} associated chats for project {project_id}")
        
        # Delete from SQL database
        success = ProjectRepository.delete_project(db, project)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete project from database")
        
        return {"status": "success", "message": f"Project {project_id} deleted successfully"}

    @staticmethod
    def add_documentation_items(db: Session, project_id: uuid.UUID, request: schemas.DocumentationListRequest):
        """Add multiple documentation items to a project with embeddings"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        stored_ids = []
        print(f"💾 Storing {len(request.documentation_items)} documentation items in vector store for project {project_id}...")
        
        for item in request.documentation_items:
            # Store in vector store (which handles both data and embeddings)
            print(f"   Storing documentation: '{item.documentation[:50]}...'")
            doc_id = VectorService.add_documentation(item.documentation, project_id=str(project_id))
            if doc_id:
                stored_ids.append(doc_id)
                print(f"   ✅ Stored with ID: {doc_id}")
            else:
                print(f"   ❌ Failed to store documentation")
                raise HTTPException(status_code=500, detail="Failed to store documentation in vector database")
        
        print(f"✅ Successfully stored {len(stored_ids)} documentation items in vector store")
        return {"status": "success", "vector_store_ids": stored_ids}

    @staticmethod
    def add_question_sql_pairs(db: Session, project_id: uuid.UUID, request: schemas.QuestionSQLListRequest):
        """Add multiple question-SQL pairs to a project with embeddings"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        stored_ids = []
        print(f"💾 Storing {len(request.question_sql_pairs)} question-SQL pairs in vector store for project {project_id}...")
        
        for item in request.question_sql_pairs:
            # Store in vector store (which handles both data and embeddings)
            print(f"   Storing Q-SQL pair: '{item.question[:50]}...'")
            sql_id = VectorService.add_question_sql(item.question, item.sql, project_id=str(project_id))
            if sql_id:
                stored_ids.append(sql_id)
                print(f"   ✅ Stored with ID: {sql_id}")
            else:
                print(f"   ❌ Failed to store question-SQL pair")
                raise HTTPException(status_code=500, detail="Failed to store question-SQL pair in vector database")
        
        print(f"✅ Successfully stored {len(stored_ids)} question-SQL pairs in vector store")
        return {"status": "success", "vector_store_ids": stored_ids}

    @staticmethod
    def add_ddl_statements(db: Session, project_id: uuid.UUID, request: schemas.DDLListRequest):
        """Add multiple DDL statements to a project with embeddings"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        stored_ids = []
        print(f"💾 Storing {len(request.ddl_statements)} DDL statements in vector store for project {project_id}...")
        
        for item in request.ddl_statements:
            # Store in vector store (which handles both data and embeddings)
            print(f"   Storing DDL: '{item.ddl[:50]}...'")
            ddl_id = VectorService.add_ddl(item.ddl, project_id=str(project_id))
            if ddl_id:
                stored_ids.append(ddl_id)
                print(f"   ✅ Stored with ID: {ddl_id}")
            else:
                print(f"   ❌ Failed to store DDL statement")
                raise HTTPException(status_code=500, detail="Failed to store DDL statement in vector database")
        
        print(f"✅ Successfully stored {len(stored_ids)} DDL statements in vector store")
        return {"status": "success", "vector_store_ids": stored_ids}

    @staticmethod
    def delete_documentation_item(item_id: str):
        """Delete a specific documentation item by ID"""
        try:
            success = VectorService.delete_documentation(item_id)
            if success:
                return {"status": "success", "message": f"Documentation item {item_id} deleted successfully", "deleted_id": item_id}
            else:
                raise HTTPException(status_code=404, detail="Documentation item not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete documentation item: {str(e)}")

    @staticmethod
    def delete_question_sql_item(item_id: str):
        """Delete a specific question-SQL pair by ID"""
        try:
            success = VectorService.delete_question_sql(item_id)
            if success:
                return {"status": "success", "message": f"Question-SQL pair {item_id} deleted successfully", "deleted_id": item_id}
            else:
                raise HTTPException(status_code=404, detail="Question-SQL pair not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete question-SQL pair: {str(e)}")

    @staticmethod
    def delete_ddl_item(item_id: str):
        """Delete a specific DDL statement by ID"""
        try:
            success = VectorService.delete_ddl(item_id)
            if success:
                return {"status": "success", "message": f"DDL statement {item_id} deleted successfully", "deleted_id": item_id}
            else:
                raise HTTPException(status_code=404, detail="DDL statement not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete DDL statement: {str(e)}") 