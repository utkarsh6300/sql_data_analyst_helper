from sqlalchemy.orm import Session
from typing import List, Optional
import models.models as models
from db.operations import DatabaseOperations

class ProjectRepository:
    """Repository for Project model operations"""
    
    @staticmethod
    def create_project(db: Session, **kwargs) -> models.Project:
        """Create a new project"""
        return DatabaseOperations.create(db, models.Project, **kwargs)
    
    @staticmethod
    def get_project_by_id(db: Session, project_id: int) -> Optional[models.Project]:
        """Get project by ID"""
        return DatabaseOperations.get_by_id(db, models.Project, project_id)
    
    @staticmethod
    def get_all_projects(db: Session, skip: int = 0, limit: int = 100) -> List[models.Project]:
        """Get all projects with chat count"""
        projects = DatabaseOperations.get_all(db, models.Project, skip, limit)
        for project in projects:
            project.chatsCount = DatabaseOperations.count(db, models.Chat, project_id=project.id)
        return projects
    
    @staticmethod
    def update_project(db: Session, project: models.Project, **kwargs) -> models.Project:
        """Update project"""
        return DatabaseOperations.update(db, project, **kwargs)
    
    @staticmethod
    def delete_project(db: Session, project: models.Project) -> bool:
        """Delete project"""
        return DatabaseOperations.delete(db, project)

class ChatRepository:
    """Repository for Chat model operations"""
    
    @staticmethod
    def create_chat(db: Session, **kwargs) -> models.Chat:
        """Create a new chat"""
        return DatabaseOperations.create(db, models.Chat, **kwargs)
    
    @staticmethod
    def get_chat_by_id(db: Session, chat_id: int) -> Optional[models.Chat]:
        """Get chat by ID"""
        return DatabaseOperations.get_by_id(db, models.Chat, chat_id)
    
    @staticmethod
    def get_chats_by_project(db: Session, project_id: int, skip: int = 0, limit: int = 50) -> List[models.Chat]:
        """Get all chats for a specific project"""
        return db.query(models.Chat)\
            .filter(models.Chat.project_id == project_id)\
            .order_by(models.Chat.id.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    @staticmethod
    def update_chat(db: Session, chat: models.Chat, **kwargs) -> models.Chat:
        """Update chat"""
        return DatabaseOperations.update(db, chat, **kwargs)
    
    @staticmethod
    def delete_chat(db: Session, chat: models.Chat) -> bool:
        """Delete chat"""
        return DatabaseOperations.delete(db, chat)
    
    @staticmethod
    def count_chats_by_project(db: Session, project_id: int) -> int:
        """Count chats for a specific project"""
        return DatabaseOperations.count(db, models.Chat, project_id=project_id) 