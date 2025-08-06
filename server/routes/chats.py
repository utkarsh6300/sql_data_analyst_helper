from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import schemas.schemas as schemas
from db.database import get_db
from services.chat_service import ChatService
import uuid

router = APIRouter(prefix="/chats", tags=["chats"])

# Create a single instance of ChatService
chat_service = ChatService()

@router.get("/{chat_id}", response_model=schemas.Chat)
def get_chat(chat_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific chat by ID"""
    return chat_service.get_chat(db, chat_id)

@router.post("/", response_model=schemas.Chat)
def create_chat(chat: schemas.ChatCreate, db: Session = Depends(get_db)):
    """Create a new chat"""
    return chat_service.create_chat(db, chat)

@router.post("/{chat_id}/generate")
def generate_sql(chat_id: uuid.UUID, query: schemas.QueryRequest, db: Session = Depends(get_db)):
    """Generate SQL for a query in a chat"""
    return chat_service.generate_sql(db, chat_id, query)

@router.post("/{chat_id}/feedback")
def provide_feedback(chat_id: uuid.UUID, feedback: schemas.FeedbackRequest, db: Session = Depends(get_db)):
    """Provide feedback for a generated SQL query"""
    return chat_service.provide_feedback(db, chat_id, feedback)

@router.patch("/{chat_id}")
def update_chat(chat_id: uuid.UUID, update: dict, db: Session = Depends(get_db)):
    """Update chat settings"""
    return chat_service.update_chat(db, chat_id, update) 