from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime

class ProjectBase(BaseModel):
    name: str
    db_schema: str
    documentation: Optional[str] = None
    sample_queries: Optional[Dict[str, str]] = None

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: int
    created_at: str
    chatsCount: int = 0

    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    project_id: int
    query_history: Optional[List[Dict[str, Any]]] = None
    feedback_enabled: Optional[bool] = None

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True

class QueryRequest(BaseModel):
    text: str

class FeedbackRequest(BaseModel):
    is_correct: bool
    add_to_samples: bool = False

class DocumentationRequest(BaseModel):
    documentation: str

class SchemaRequest(BaseModel):
    db_schema: str

class SampleQueriesRequest(BaseModel):
    sample_queries: Dict[str, str]