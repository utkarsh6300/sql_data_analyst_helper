from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List
import models.models as models
import schemas.schemas as schemas
from db.repositories import ProjectRepository, ChatRepository
import uuid

class ProjectChatService:
    @staticmethod
    def get_project_chats(db: Session, project_id: uuid.UUID, skip: int = 0, limit: int = 50):
        """Get all chats for a specific project"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return ChatRepository.get_chats_by_project(db, project_id, skip, limit)

    @staticmethod
    def create_project_chat(db: Session, project_id: uuid.UUID):
        """Create a new chat for a specific project"""
        project = ProjectRepository.get_project_by_id(db, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return ChatRepository.create_chat(db, project_id=project_id) 