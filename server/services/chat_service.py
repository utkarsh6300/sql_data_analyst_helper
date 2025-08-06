from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import models.models as models
import schemas.schemas as schemas
from services.generic.sql_generator import generate_sql_query, regenerate_sql_query
from services.vector_service import VectorService
from db.repositories import ChatRepository, ProjectRepository

class ChatService:
    @staticmethod
    def get_chat(db: Session, chat_id: int):
        """Get a specific chat by ID"""
        chat = ChatRepository.get_chat_by_id(db, chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        return chat

    @staticmethod
    def create_chat(db: Session, chat: schemas.ChatCreate):
        """Create a new chat"""
        project = ProjectRepository.get_project_by_id(db, chat.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return ChatRepository.create_chat(db, **chat.dict())

    @staticmethod
    def generate_sql(db: Session, chat_id: int, query: schemas.QueryRequest):
        """Generate SQL for a query in a chat"""
        chat = ChatRepository.get_chat_by_id(db, chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        project = chat.project
        
        print(f"🔍 Generating SQL for query: '{query.text}' in project {project.id}")
        
        # Get similar content from vector store
        print(f"📚 Fetching related documentation from vector store for project {project.id}...")
        similar_docs = VectorService.get_related_documentation(query.text, project_id=str(project.id))
        print(f"📄 Found {len(similar_docs) if similar_docs else 0} related documentation items")
        if similar_docs:
            print(f"   Documentation preview: {str(similar_docs)[:200]}...")
        
        print(f"🏗️  Fetching related DDL from vector store for project {project.id}...")
        similar_schema = VectorService.get_related_ddl(query.text, project_id=str(project.id))
        print(f"📋 Found {len(similar_schema) if similar_schema else 0} related DDL items")
        if similar_schema:
            print(f"   DDL preview: {str(similar_schema)[:200]}...")
        
        print(f"❓ Fetching similar question-SQL pairs from vector store for project {project.id}...")
        similar_queries = VectorService.get_similar_question_sql(query.text, project_id=str(project.id))
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
        ChatRepository.update_chat(db, chat, query_history=history)
        
        return {"sql": generated_sql, "chat_id": chat_id}

    @staticmethod
    def provide_feedback(db: Session, chat_id: int, feedback: schemas.FeedbackRequest):
        """Provide feedback for a generated SQL query"""
        chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        
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
            sql_id = VectorService.add_question_sql(last_query["text"], last_query["sql"], project_id=str(project.id))
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
            similar_docs = VectorService.get_related_documentation(query_text, project_id=str(project.id))
            print(f"📄 Found {len(similar_docs) if similar_docs else 0} related documentation items for regeneration")
            
            print(f"🏗️  Fetching related DDL for regeneration...")
            similar_ddl = VectorService.get_related_ddl(query_text, project_id=str(project.id))
            print(f"📋 Found {len(similar_ddl) if similar_ddl else 0} related DDL items for regeneration")
            
            print(f"❓ Fetching similar question-SQL pairs for regeneration...")
            similar_queries = VectorService.get_similar_question_sql(query_text, project_id=str(project.id))
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

    @staticmethod
    def update_chat(db: Session, chat_id: int, update: dict):
        """Update chat settings"""
        chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        if "feedback_enabled" in update:
            chat.feedback_enabled = update["feedback_enabled"]
            
        db.commit()
        db.refresh(chat)
        return chat 