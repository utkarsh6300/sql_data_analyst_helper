from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import schemas.schemas as schemas
from db.database import get_db
from services.chat_service import ChatService

router = APIRouter(prefix="/chats", tags=["chats"])

@router.get("/{chat_id}", response_model=schemas.Chat)
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    """Get a specific chat by ID"""
    return ChatService.get_chat(db, chat_id)

@router.post("/", response_model=schemas.Chat)
def create_chat(chat: schemas.ChatCreate, db: Session = Depends(get_db)):
    """Create a new chat"""
    return ChatService.create_chat(db, chat)

@router.post("/{chat_id}/generate")
def generate_sql(chat_id: int, query: schemas.QueryRequest, db: Session = Depends(get_db)):
    """Generate SQL for a query in a chat"""
    return ChatService.generate_sql(db, chat_id, query)

@router.post("/{chat_id}/feedback")
def provide_feedback(chat_id: int, feedback: schemas.FeedbackRequest, db: Session = Depends(get_db)):
    """Provide feedback for a generated SQL query"""
    return ChatService.provide_feedback(db, chat_id, feedback)

@router.patch("/{chat_id}")
def update_chat(chat_id: int, update: dict, db: Session = Depends(get_db)):
    """Update chat settings"""
    return ChatService.update_chat(db, chat_id, update) 