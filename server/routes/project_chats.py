from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import schemas.schemas as schemas
from db.database import get_db
from services.project_chat_service import ProjectChatService
import uuid

router = APIRouter(prefix="/projects/{project_id}/chats", tags=["project-chats"])

@router.get("/", response_model=List[schemas.Chat])
def get_project_chats(project_id: uuid.UUID, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Get all chats for a specific project"""
    return ProjectChatService.get_project_chats(db, project_id, skip, limit)

@router.post("/", response_model=schemas.Chat)
def create_project_chat(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Create a new chat for a specific project"""
    return ProjectChatService.create_project_chat(db, project_id) 