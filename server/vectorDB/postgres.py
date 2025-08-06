import json
from typing import List, Optional, Dict, Any
import os
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, Text, Float, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.exc import SQLAlchemyError
import uuid
from langchain_huggingface import HuggingFaceEmbeddings

# Load environment variables
load_dotenv()

# Initialize embedding function
embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

from vectorDB.utils import deterministic_uuid

class PostgresDB_VectorStore():
    def __init__(self, config=None):
        if config is None:
            config = {}
        
        # Database configuration
        db_url = config.get("database_url", os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/analyst_helper'))
        self.embedding_function = config.get("embedding_function", embedding_function)
        self.n_results_sql = config.get("n_results_sql", config.get("n_results", 10))
        self.n_results_documentation = config.get("n_results_documentation", config.get("n_results", 10))
        self.n_results_ddl = config.get("n_results_ddl", config.get("n_results", 10))
        
        # Initialize database connection
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables and enable pgvector extension
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize the database with pgvector extension and create tables"""
        try:
            # Enable pgvector extension
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            
            # Create tables
            Base.metadata.create_all(bind=self.engine)
            print("✅ PostgreSQL vector database initialized successfully")
            
        except SQLAlchemyError as e:
            print(f"❌ Database initialization failed: {e}")
            raise
    
    def _get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def generate_embedding(self, data: str, **kwargs) -> List[float]:
        """Generate embedding for the given text"""
        try:
            embedding = self.embedding_function.embed_query(data)
            return embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return []
    
    def create_project(self, project_id: str, name: str, description: str = None) -> bool:
        """Create a new project"""
        try:
            with self._get_session() as session:
                project = Project(
                    id=project_id,
                    name=name,
                    description=description,
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(project)
                session.commit()
                return True
        except Exception as e:
            print(f"Error creating project: {e}")
            return False
    
    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project details"""
        try:
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if project:
                    return {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                        "created_at": project.created_at
                    }
                return None
        except Exception as e:
            print(f"Error getting project: {e}")
            return None
    
    def list_projects(self) -> List[Dict]:
        """List all projects"""
        try:
            with self._get_session() as session:
                projects = session.query(Project).all()
                return [{
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "created_at": p.created_at
                } for p in projects]
        except Exception as e:
            print(f"Error listing projects: {e}")
            return []
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its associated data"""
        try:
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if project:
                    session.delete(project)
                    session.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False
    
    def add_question_sql(self, question: str, sql: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add a question-SQL pair to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            doc_id = deterministic_uuid(f"{question}{sql}{project_id}") + "-sql"
            embedding = self.generate_embedding(f"{question} {sql}")
            
            if not embedding:
                return None
            
            metadata = {"project_id": project_id}
            
            with self._get_session() as session:
                sql_query = SQLQuery(
                    id=doc_id,
                    project_id=project_id,
                    question=question,
                    sql=sql,
                    embedding=embedding,
                    metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(sql_query)
                session.commit()
            
            return doc_id
            
        except Exception as e:
            print(f"Error adding question-SQL pair: {str(e)}")
            return None
    
    def add_ddl(self, ddl: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add DDL statement to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            doc_id = deterministic_uuid(f"{ddl}{project_id}") + "-ddl"
            embedding = self.generate_embedding(ddl)
            
            if not embedding:
                return None
            
            metadata = {"project_id": project_id}
            
            with self._get_session() as session:
                ddl_stmt = DDLStatement(
                    id=doc_id,
                    project_id=project_id,
                    ddl=ddl,
                    embedding=embedding,
                    metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(ddl_stmt)
                session.commit()
            
            return doc_id
            
        except Exception as e:
            print(f"Error adding DDL: {str(e)}")
            return None
    
    def add_documentation(self, documentation: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add documentation to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            doc_id = deterministic_uuid(f"{documentation}{project_id}") + "-doc"
            embedding = self.generate_embedding(documentation)
            
            if not embedding:
                return None
            
            metadata = {"project_id": project_id}
            
            with self._get_session() as session:
                doc_item = DocumentationItem(
                    id=doc_id,
                    project_id=project_id,
                    documentation=documentation,
                    embedding=embedding,
                    metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(doc_item)
                session.commit()
            
            return doc_id
            
        except Exception as e:
            print(f"Error adding documentation: {str(e)}")
            return None
    
    def get_training_data(self, project_id: str = None, **kwargs) -> pd.DataFrame:
        """Get all training data as a DataFrame, optionally filtered by project"""
        try:
            with self._get_session() as session:
                df = pd.DataFrame()
                
                # Get SQL data
                sql_query = session.query(SQLQuery)
                if project_id:
                    sql_query = sql_query.filter(SQLQuery.project_id == project_id)
                sql_results = sql_query.all()
                
                if sql_results:
                    sql_data = [{
                        "id": doc.id,
                        "question": doc.question,
                        "content": doc.sql,
                        "training_data_type": "sql",
                        "project_id": doc.project_id
                    } for doc in sql_results]
                    df = pd.concat([df, pd.DataFrame(sql_data)])
                
                # Get DDL data
                ddl_query = session.query(DDLStatement)
                if project_id:
                    ddl_query = ddl_query.filter(DDLStatement.project_id == project_id)
                ddl_results = ddl_query.all()
                
                if ddl_results:
                    ddl_data = [{
                        "id": doc.id,
                        "question": None,
                        "content": doc.ddl,
                        "training_data_type": "ddl",
                        "project_id": doc.project_id
                    } for doc in ddl_results]
                    df = pd.concat([df, pd.DataFrame(ddl_data)])
                
                # Get documentation data
                doc_query = session.query(DocumentationItem)
                if project_id:
                    doc_query = doc_query.filter(DocumentationItem.project_id == project_id)
                doc_results = doc_query.all()
                
                if doc_results:
                    doc_data = [{
                        "id": doc.id,
                        "question": None,
                        "content": doc.documentation,
                        "training_data_type": "documentation",
                        "project_id": doc.project_id
                    } for doc in doc_results]
                    df = pd.concat([df, pd.DataFrame(doc_data)])
                
                return df
            
        except Exception as e:
            print(f"Error getting training data: {e}")
            return pd.DataFrame()
    
    def remove_training_data(self, id: str, **kwargs) -> bool:
        """Remove training data by ID"""
        try:
            with self._get_session() as session:
                # Try to find in each table
                result = session.query(SQLQuery).filter(SQLQuery.id == id).delete()
                if result == 0:
                    result = session.query(DDLStatement).filter(DDLStatement.id == id).delete()
                if result == 0:
                    result = session.query(DocumentationItem).filter(DocumentationItem.id == id).delete()
                
                session.commit()
                return result > 0
        except Exception as e:
            print(f"Error removing training data: {e}")
            return False
    
    def remove_collection(self, collection_name: str, project_id: str = None) -> bool:
        """
        Remove all data from a specific collection, optionally filtered by project.
        
        Args:
            collection_name (str): sql, ddl, or documentation
            project_id (str): Optional project filter
            
        Returns:
            bool: True if collection is cleared, False otherwise
        """
        try:
            with self._get_session() as session:
                if collection_name == "sql":
                    query = session.query(SQLQuery)
                    if project_id:
                        query = query.filter(SQLQuery.project_id == project_id)
                    result = query.delete()
                elif collection_name == "ddl":
                    query = session.query(DDLStatement)
                    if project_id:
                        query = query.filter(DDLStatement.project_id == project_id)
                    result = query.delete()
                elif collection_name == "documentation":
                    query = session.query(DocumentationItem)
                    if project_id:
                        query = query.filter(DocumentationItem.project_id == project_id)
                    result = query.delete()
                else:
                    return False
                
                session.commit()
                print(f"🗑️  Cleared {result} entries from {collection_name} collection")
                return True
        except Exception as e:
            print(f"Error removing collection {collection_name}: {e}")
            return False
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        except Exception:
            return 0.0
    
    def _get_similar_sql_queries(self, query_embedding: List[float], project_id: str, 
                               n_results: int) -> List[Dict]:
        """Get similar SQL queries using cosine similarity"""
        try:
            with self._get_session() as session:
                queries = session.query(SQLQuery).filter(
                    SQLQuery.project_id == project_id
                ).all()
                
                if not queries:
                    return []
                
                # Calculate similarities
                similarities = []
                for query in queries:
                    similarity = self._cosine_similarity(query_embedding, query.embedding)
                    similarities.append((similarity, {
                        "question": query.question,
                        "sql": query.sql,
                        "project_id": query.project_id
                    }))
                
                # Sort by similarity (descending) and return top results
                similarities.sort(key=lambda x: x[0], reverse=True)
                return [doc for _, doc in similarities[:n_results]]
                
        except Exception as e:
            print(f"Error getting similar SQL queries: {e}")
            return []
    
    def _get_similar_ddl_statements(self, query_embedding: List[float], project_id: str, 
                                  n_results: int) -> List[str]:
        """Get similar DDL statements using cosine similarity"""
        try:
            with self._get_session() as session:
                statements = session.query(DDLStatement).filter(
                    DDLStatement.project_id == project_id
                ).all()
                
                if not statements:
                    return []
                
                # Calculate similarities
                similarities = []
                for stmt in statements:
                    similarity = self._cosine_similarity(query_embedding, stmt.embedding)
                    similarities.append((similarity, stmt.ddl))
                
                # Sort by similarity (descending) and return top results
                similarities.sort(key=lambda x: x[0], reverse=True)
                return [doc for _, doc in similarities[:n_results]]
                
        except Exception as e:
            print(f"Error getting similar DDL statements: {e}")
            return []
    
    def _get_similar_documentation(self, query_embedding: List[float], project_id: str, 
                                 n_results: int) -> List[str]:
        """Get similar documentation using cosine similarity"""
        try:
            with self._get_session() as session:
                docs = session.query(DocumentationItem).filter(
                    DocumentationItem.project_id == project_id
                ).all()
                
                if not docs:
                    return []
                
                # Calculate similarities
                similarities = []
                for doc in docs:
                    similarity = self._cosine_similarity(query_embedding, doc.embedding)
                    similarities.append((similarity, doc.documentation))
                
                # Sort by similarity (descending) and return top results
                similarities.sort(key=lambda x: x[0], reverse=True)
                return [doc for _, doc in similarities[:n_results]]
                
        except Exception as e:
            print(f"Error getting similar documentation: {e}")
            return []
    
    def get_similar_question_sql(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get similar SQL queries for a given question.
        Includes error handling and validation.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            query_embedding = self.generate_embedding(question)
            if not query_embedding:
                return []
            
            return self._get_similar_sql_queries(query_embedding, project_id, self.n_results_sql)
            
        except Exception as e:
            print(f"Error retrieving similar queries: {str(e)}")
            return []
    
    def get_related_ddl(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get related DDL statements for a given question.
        Includes error handling and validation.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            query_embedding = self.generate_embedding(question)
            if not query_embedding:
                return []
            
            return self._get_similar_ddl_statements(query_embedding, project_id, self.n_results_ddl)
            
        except Exception as e:
            print(f"Error retrieving DDL context: {str(e)}")
            return []
    
    def get_related_documentation(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get related documentation for a given question.
        Includes error handling and validation.
        """
        try:
            if not project_id:
                raise ValueError("project_id is required")
            
            query_embedding = self.generate_embedding(question)
            if not query_embedding:
                return []
            
            return self._get_similar_documentation(query_embedding, project_id, self.n_results_documentation)
            
        except Exception as e:
            print(f"Error retrieving documentation: {str(e)}")
            return []
    
    def migrate_embeddings(self, new_embedding_function=None):
        """
        Migrate existing collections to use a new embedding function.
        This will regenerate all embeddings with the new function.
        
        Args:
            new_embedding_function: The new embedding function to use. If None, uses the current one.
        
        Returns:
            bool: True if migration was successful, False otherwise
        """
        if new_embedding_function:
            self.embedding_function = new_embedding_function
        
        try:
            print("🔄 Starting embedding function migration...")
            
            with self._get_session() as session:
                # Get all documents from all tables
                sql_queries = session.query(SQLQuery).all()
                ddl_statements = session.query(DDLStatement).all()
                documentation_items = session.query(DocumentationItem).all()
                
                all_documents = []
                all_documents.extend([(q, "sql") for q in sql_queries])
                all_documents.extend([(d, "ddl") for d in ddl_statements])
                all_documents.extend([(doc, "doc") for doc in documentation_items])
                
                if not all_documents:
                    print("ℹ️  No documents to migrate")
                    return True
                
                print(f"📋 Found {len(all_documents)} documents to migrate")
                
                migrated_count = 0
                for doc, doc_type in all_documents:
                    try:
                        if doc_type == "sql":
                            text_to_embed = f"{doc.question} {doc.sql}"
                        elif doc_type == "ddl":
                            text_to_embed = doc.ddl
                        else:  # doc
                            text_to_embed = doc.documentation
                        
                        # Generate new embedding
                        new_embedding = self.generate_embedding(text_to_embed)
                        if new_embedding:
                            doc.embedding = new_embedding
                            migrated_count += 1
                    except Exception as e:
                        print(f"⚠️  Failed to migrate document {doc.id}: {e}")
                
                session.commit()
                print(f"✅ Migration completed! Migrated {migrated_count} documents")
                return True
                
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False
    
    def get_collection_stats(self, project_id: str = None) -> Dict[str, Any]:
        """Get statistics about all collections, optionally filtered by project"""
        try:
            with self._get_session() as session:
                stats = {}
                
                # SQL queries stats
                sql_query = session.query(SQLQuery)
                if project_id:
                    sql_query = sql_query.filter(SQLQuery.project_id == project_id)
                stats["sql"] = sql_query.count()
                
                # DDL statements stats
                ddl_query = session.query(DDLStatement)
                if project_id:
                    ddl_query = ddl_query.filter(DDLStatement.project_id == project_id)
                stats["ddl"] = ddl_query.count()
                
                # Documentation stats
                doc_query = session.query(DocumentationItem)
                if project_id:
                    doc_query = doc_query.filter(DocumentationItem.project_id == project_id)
                stats["documentation"] = doc_query.count()
                
                return stats
                
        except Exception as e:
            print(f"Error getting collection stats: {e}")
            return {}
    
    def close(self):
        """Close database connections"""
        try:
            self.engine.dispose()
        except Exception as e:
            print(f"Error closing database connections: {e}") 