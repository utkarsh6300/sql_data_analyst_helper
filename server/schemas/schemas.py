from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime
import uuid

class ProjectBase(BaseModel):
    name: str

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: uuid.UUID
    created_at: str
    chatsCount: int = 0

    class Config:
        from_attributes = True

# New schema for project with related data
class ProjectDetail(ProjectBase):
    id: uuid.UUID
    created_at: str
    chatsCount: int = 0
    documentation_items: List[Dict[str, Any]] = []
    question_sql_pairs: List[Dict[str, Any]] = []
    ddl_statements: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    project_id: uuid.UUID
    query_history: Optional[List[Dict[str, Any]]] = None
    feedback_enabled: Optional[bool] = None

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: uuid.UUID
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

# New schemas for individual items
class DDLItem(BaseModel):
    ddl: str
    metadata: Optional[Dict[str, Any]] = None

class DocumentationItem(BaseModel):
    documentation: str
    metadata: Optional[Dict[str, Any]] = None

class QuestionSQLPair(BaseModel):
    question: str
    sql: str
    metadata: Optional[Dict[str, Any]] = None

class DDLListRequest(BaseModel):
    ddl_statements: List[DDLItem]

class DocumentationListRequest(BaseModel):
    documentation_items: List[DocumentationItem]

class QuestionSQLListRequest(BaseModel):
    question_sql_pairs: List[QuestionSQLPair]

# New schemas for deletion responses
class DeleteResponse(BaseModel):
    status: str
    message: str
    deleted_id: Optional[str] = None