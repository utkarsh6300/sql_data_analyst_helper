from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import models
import schemas
from database import engine, get_db
from services.sql_generator import generate_sql_query, regenerate_sql_query
from vectorDB.chroma import ChromaDB_VectorStore

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Initialize ChromaDB with OpenAI embeddings
try:
    vector_store = ChromaDB_VectorStore(config={
        "path": "./chroma_db",
        "client": "persistent"
    })
    print("✅ ChromaDB initialized with OpenAI embeddings")
except Exception as e:
    print(f"⚠️  Warning: Failed to initialize ChromaDB with OpenAI embeddings: {e}")
    print("🔄 Falling back to default embeddings...")
    # The ChromaDB class will automatically fall back to default embeddings
    vector_store = ChromaDB_VectorStore(config={
        "path": "./chroma_db",
        "client": "persistent"
    })

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/projects/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = models.Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@app.get("/projects/", response_model=List[schemas.Project])
def get_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    projects = db.query(models.Project).offset(skip).limit(limit).all()
    for project in projects:
        project.chatsCount = db.query(models.Chat).filter(models.Chat.project_id == project.id).count()
    return projects

@app.get("/projects/{project_id}", response_model=schemas.Project)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # # Load associated chats
    # project.chats = db.query(models.Chat).filter(models.Chat.project_id == project_id).all()
    return project

@app.post("/projects/{project_id}/documentation")
def update_documentation(project_id: int, request: schemas.DocumentationRequest, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Store in both SQL database and vector store
    project.documentation = request.documentation
    db.commit()
    
    # Store in ChromaDB
    print(f"💾 Storing documentation in vector store for project {project_id}...")
    doc_id = vector_store.add_documentation(request.documentation, project_id=str(project_id))
    if not doc_id:
        raise HTTPException(status_code=500, detail="Failed to store documentation in vector database")
    
    print(f"✅ Documentation stored successfully with ID: {doc_id}")
    return {"status": "success", "vector_store_id": doc_id}

@app.post("/projects/{project_id}/sample-queries")
def add_sample_queries(project_id: int, request: schemas.SampleQueriesRequest, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Store in SQL database
    current_samples = project.sample_queries or {}
    current_samples.update(request.sample_queries)
    project.sample_queries = current_samples
    db.commit()
    
    # Store in ChromaDB
    print(f"💾 Storing {len(request.sample_queries)} sample queries in vector store for project {project_id}...")
    stored_ids = []
    for question, sql in request.sample_queries.items():
        print(f"   Storing Q&A pair: '{question[:50]}...' -> '{sql[:50]}...'")
        sql_id = vector_store.add_question_sql(question, sql, project_id=str(project_id))
        if sql_id:
            stored_ids.append(sql_id)
            print(f"   ✅ Stored with ID: {sql_id}")
        else:
            print(f"   ❌ Failed to store Q&A pair")
    
    if not stored_ids:
        raise HTTPException(status_code=500, detail="Failed to store sample queries in vector database")
    
    print(f"✅ Successfully stored {len(stored_ids)} sample queries in vector store")
    return {"status": "success", "vector_store_ids": stored_ids}

@app.post("/projects/{project_id}/schema")
def add_ddl(project_id: int, request: schemas.SchemaRequest, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Store in both SQL database and vector store
    project.schema = request.schema
    db.commit()
    
    # Store in ChromaDB
    print(f"💾 Storing DDL in vector store for project {project_id}...")
    ddl_id = vector_store.add_ddl(request.schema, project_id=str(project_id))
    if not ddl_id:
        raise HTTPException(status_code=500, detail="Failed to store DDL in vector database")
    
    print(f"✅ DDL stored successfully with ID: {ddl_id}")
    return {"status": "success", "vector_store_id": ddl_id}

@app.get("/projects/{project_id}/chats", response_model=List[schemas.Chat])
def get_project_chats(project_id: int, skip: int = 0, limit: int = 50,  db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    chats = db.query(models.Chat)\
        .filter(models.Chat.project_id == project_id)\
        .order_by(models.Chat.id.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    return chats or []

@app.post("/projects/{project_id}/chats", response_model=schemas.Chat)
def create_project_chat(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db_chat = models.Chat(project_id=project_id)
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat

@app.post("/chats/", response_model=schemas.Chat)
def create_chat(chat: schemas.ChatCreate, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == chat.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db_chat = models.Chat(**chat.dict())
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat

@app.get("/chats/{chat_id}", response_model=schemas.Chat)
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@app.post("/chats/{chat_id}/generate")
def generate_sql(chat_id: int, query: schemas.QueryRequest, db: Session = Depends(get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    project = chat.project
    
    print(f"🔍 Generating SQL for query: '{query.text}' in project {project.id}")
    
    # Get similar content from vector store
    print(f"📚 Fetching related documentation from vector store for project {project.id}...")
    similar_docs = vector_store.get_related_documentation(query.text, project_id=str(project.id))
    print(f"📄 Found {len(similar_docs) if similar_docs else 0} related documentation items")
    if similar_docs:
        print(f"   Documentation preview: {str(similar_docs)[:200]}...")
    
    print(f"🏗️  Fetching related DDL from vector store for project {project.id}...")
    similar_schema = vector_store.get_related_ddl(query.text, project_id=str(project.id))
    print(f"📋 Found {len(similar_schema) if similar_schema else 0} related DDL items")
    if similar_schema:
        print(f"   DDL preview: {str(similar_schema)[:200]}...")
    
    print(f"❓ Fetching similar question-SQL pairs from vector store for project {project.id}...")
    similar_queries = vector_store.get_similar_question_sql(query.text, project_id=str(project.id))
    print(f"🔗 Found {len(similar_queries) if similar_queries else 0} similar question-SQL pairs")
    if similar_queries:
        print(f"   Similar queries preview: {str(similar_queries)[:200]}...")
    
    # Extract sample queries from similar results
    additional_samples = {}
    for result in similar_queries:
        if isinstance(result, dict) and "question" in result and "sql" in result:
            additional_samples[result["question"]] = result["sql"]
    
    # Combine project samples with similar samples
    all_samples = {**(project.sample_queries or {}), **additional_samples}
    
    # Convert list responses to strings for SQL generator
    schema_text = similar_schema[0] if similar_schema and len(similar_schema) > 0 else ""
    documentation_text = similar_docs[0] if similar_docs and len(similar_docs) > 0 else ""
    
    print(f"📋 Schema text length: {len(schema_text)} characters")
    print(f"📚 Documentation text length: {len(documentation_text)} characters")
    print(f"❓ Sample queries count: {len(all_samples)}")
    print(f"🔄 Query history length: {len(chat.query_history) if chat.query_history else 0}")
    
    # Generate SQL using all available context
    generated_sql = generate_sql_query(
        query_text=query.text,
        schema=schema_text,
        documentation=documentation_text,
        sample_queries=all_samples,
        query_history=chat.query_history,
    )
    
    # Update query history
    history = chat.query_history or []
    history.append({
        "text": query.text,
        "sql": generated_sql,
        "timestamp": datetime.utcnow().isoformat()
    })
    chat.query_history = history
    db.commit()
    
    return {"sql": generated_sql, "chat_id": chat_id}

@app.post("/chats/{chat_id}/feedback")
def provide_feedback(
    chat_id: int,
    feedback: schemas.FeedbackRequest,
    db: Session = Depends(get_db)
):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # if not chat.feedback_enabled:
    #     raise HTTPException(status_code=403, detail="Feedback is disabled for this chat")
    
    history = chat.query_history
    if not history:
        raise HTTPException(status_code=400, detail="No queries in chat history")
    
    last_query = history[-1]
    last_query["is_correct"] = feedback.is_correct
    if feedback.is_correct:
        chat.feedback_enabled = False  # Disable feedback for this chat after correction
    if feedback.is_correct and feedback.add_to_samples:
        project = chat.project
        current_samples = project.sample_queries or {}
        current_samples[last_query["text"]] = last_query["sql"]
        project.sample_queries = current_samples
        # Also add to vector store for future similarity searches
        print(f"💾 Adding corrected Q&A pair to vector store for project {project.id}...")
        print(f"   Question: '{last_query['text'][:50]}...'")
        print(f"   SQL: '{last_query['sql'][:50]}...'")
        sql_id = vector_store.add_question_sql(last_query["text"], last_query["sql"], project_id=str(project.id))
        if sql_id:
            print(f"   ✅ Added to vector store with ID: {sql_id}")
        else:
            print(f"   ❌ Failed to add to vector store")
        
    chat.query_history = history
    db.commit()
    
    if not feedback.is_correct:
        # Get similar content from vector store for regeneration
        project = chat.project
        query_text = last_query["text"]
        
        print(f"🔄 Regenerating SQL for incorrect query: '{query_text}' in project {project.id}")
        
        print(f"📚 Fetching related documentation for regeneration...")
        similar_docs = vector_store.get_related_documentation(query_text, project_id=str(project.id))
        print(f"📄 Found {len(similar_docs) if similar_docs else 0} related documentation items for regeneration")
        
        print(f"🏗️  Fetching related DDL for regeneration...")
        similar_ddl = vector_store.get_related_ddl(query_text, project_id=str(project.id))
        print(f"📋 Found {len(similar_ddl) if similar_ddl else 0} related DDL items for regeneration")
        
        print(f"❓ Fetching similar question-SQL pairs for regeneration...")
        similar_queries = vector_store.get_similar_question_sql(query_text, project_id=str(project.id))
        print(f"🔗 Found {len(similar_queries) if similar_queries else 0} similar question-SQL pairs for regeneration")
        
        # Extract sample queries from similar results
        additional_samples = {}
        for result in similar_queries:
            if isinstance(result, dict) and "question" in result and "sql" in result:
                additional_samples[result["question"]] = result["sql"]
        
        # Combine project samples with similar samples
        all_samples = {**(project.sample_queries or {}), **additional_samples}
        
        # Convert list responses to strings for SQL generator
        ddl_text = similar_ddl[0] if similar_ddl and len(similar_ddl) > 0 else ""
        docs_text = similar_docs[0] if similar_docs and len(similar_docs) > 0 else ""
        
        print(f"📋 DDL text length for regeneration: {len(ddl_text)} characters")
        print(f"📚 Documentation text length for regeneration: {len(docs_text)} characters")
        print(f"❓ Sample queries count for regeneration: {len(all_samples)}")
        print(f"🔄 Query history length for regeneration: {len(history)}")
        
        # Regenerate SQL using all available context
        new_sql = regenerate_sql_query(
            query_text=query_text,
            schema=ddl_text,
            documentation=docs_text,
            sample_queries=all_samples,
            query_history=history
        )
        
        history.append({
            "text": last_query["text"],
            "sql": new_sql,
            "timestamp": datetime.utcnow().isoformat()
        })
        chat.query_history = history
        db.commit()
        return {"sql": new_sql, "chat_id": chat_id, "feedback_enabled": chat.feedback_enabled}
    
    return {"status": "success", "feedback_enabled": chat.feedback_enabled}

@app.patch("/chats/{chat_id}")
def update_chat(chat_id: int, update: dict, db: Session = Depends(get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if "feedback_enabled" in update:
        chat.feedback_enabled = update["feedback_enabled"]
        
    db.commit()
    db.refresh(chat)
    return chat