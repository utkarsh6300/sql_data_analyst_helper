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
from datetime import datetime
from langchain_huggingface import HuggingFaceEmbeddings

# Import Base and models
from models.base import Base
from models.models import Project
from models.vectorDbModels import SQLQuery, DDLStatement, DocumentationItem

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
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
                project = Project(
                    id=project_id,
                    name=name,
                    created_at=datetime.utcnow().isoformat()
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
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
                project = session.query(Project).filter(Project.id == project_id).first()
                if project:
                    return {
                        "id": str(project.id),
                        "name": project.name,
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
                    "id": str(p.id),
                    "name": p.name,
                    "created_at": p.created_at
                } for p in projects]
        except Exception as e:
            print(f"Error listing projects: {e}")
            return []
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its associated data"""
        try:
            with self._get_session() as session:
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
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
            
            # Convert project_id to UUID if it's a string
            if isinstance(project_id, str):
                try:
                    project_id = uuid.UUID(project_id)
                except ValueError:
                    raise ValueError(f"Invalid project_id format: {project_id}")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            embedding = self.generate_embedding(f"{question} {sql}")
            
            if not embedding:
                return None
            
            metadata = {"project_id": str(project_id)}
            
            with self._get_session() as session:
                sql_query = SQLQuery(
                    project_id=project_id,
                    question=question,
                    sql=sql,
                    embedding=embedding,
                    sql_metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(sql_query)
                session.commit()
                return str(sql_query.id)
            
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
            
            # Convert project_id to UUID if it's a string
            if isinstance(project_id, str):
                try:
                    project_id = uuid.UUID(project_id)
                except ValueError:
                    raise ValueError(f"Invalid project_id format: {project_id}")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            embedding = self.generate_embedding(ddl)
            
            if not embedding:
                return None
            
            metadata = {"project_id": str(project_id)}
            
            with self._get_session() as session:
                ddl_stmt = DDLStatement(
                    project_id=project_id,
                    ddl=ddl,
                    embedding=embedding,
                    ddl_metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(ddl_stmt)
                session.commit()
                return str(ddl_stmt.id)
            
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
            
            # Convert project_id to UUID if it's a string
            if isinstance(project_id, str):
                try:
                    project_id = uuid.UUID(project_id)
                except ValueError:
                    raise ValueError(f"Invalid project_id format: {project_id}")
            
            # Ensure project exists
            with self._get_session() as session:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    raise ValueError(f"Project {project_id} does not exist")
            
            embedding = self.generate_embedding(documentation)
            
            if not embedding:
                return None
            
            metadata = {"project_id": str(project_id)}
            
            with self._get_session() as session:
                doc_item = DocumentationItem(
                    project_id=project_id,
                    documentation=documentation,
                    embedding=embedding,
                    documentation_metadata=json.dumps(metadata),
                    created_at=int(pd.Timestamp.now().timestamp())
                )
                session.add(doc_item)
                session.commit()
                return str(doc_item.id)
            
        except Exception as e:
            print(f"Error adding documentation: {str(e)}")
            return None
    
    def get_training_data(self, project_id: str = None, **kwargs) -> pd.DataFrame:
        """Get all training data as a DataFrame, optionally filtered by project"""
        try:
            with self._get_session() as session:
                df = pd.DataFrame()
                
                # Convert project_id to UUID if it's a string
                if project_id and isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
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
                result = session.query(SQLQuery).filter(SQLQuery.uuid == id).delete()
                if result == 0:
                    result = session.query(DDLStatement).filter(DDLStatement.uuid == id).delete()
                if result == 0:
                    result = session.query(DocumentationItem).filter(DocumentationItem.uuid == id).delete()
                
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
                # Convert project_id to integer if it's a string
                project_id_int = int(project_id) if project_id and isinstance(project_id, str) else project_id
                
                if collection_name == "sql":
                    query = session.query(SQLQuery)
                    if project_id:
                        query = query.filter(SQLQuery.project_id == project_id_int)
                    result = query.delete()
                elif collection_name == "ddl":
                    query = session.query(DDLStatement)
                    if project_id:
                        query = query.filter(DDLStatement.project_id == project_id_int)
                    result = query.delete()
                elif collection_name == "documentation":
                    query = session.query(DocumentationItem)
                    if project_id:
                        query = query.filter(DocumentationItem.project_id == project_id_int)
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
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
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
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
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
                # Convert project_id to UUID if it's a string
                if isinstance(project_id, str):
                    try:
                        project_id = uuid.UUID(project_id)
                    except ValueError:
                        raise ValueError(f"Invalid project_id format: {project_id}")
                
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
        """Get related documentation for a given question"""
        try:
            query_embedding = self.generate_embedding(question)
            if not query_embedding:
                return []
            
            return self._get_similar_documentation(query_embedding, project_id, self.n_results_documentation)
        except Exception as e:
            print(f"Error retrieving documentation: {str(e)}")
            return []

    def get_all_documentation(self, project_id: str = None, **kwargs) -> list:
        """Get all documentation items for a project"""
        try:
            with self._get_session() as session:
                query = session.query(DocumentationItem)
                if project_id is not None:
                    # Convert project_id to UUID if it's a string
                    if isinstance(project_id, str):
                        try:
                            project_id = uuid.UUID(project_id)
                        except ValueError:
                            raise ValueError(f"Invalid project_id format: {project_id}")
                    query = query.filter(DocumentationItem.project_id == project_id)
                
                items = query.all()
                result = []
                for item in items:
                    result.append({
                        "id": str(item.id),
                        "documentation": item.documentation,
                        "metadata": {
                            "project_id": str(item.project_id),
                            "created_at": datetime.fromtimestamp(item.created_at).isoformat() if item.created_at else None
                        }
                    })
                return result
        except Exception as e:
            print(f"Error retrieving all documentation: {str(e)}")
            return []

    def get_all_question_sql(self, project_id: str = None, **kwargs) -> list:
        """Get all question-SQL pairs for a project"""
        try:
            with self._get_session() as session:
                query = session.query(SQLQuery)
                if project_id is not None:
                    # Convert project_id to UUID if it's a string
                    if isinstance(project_id, str):
                        try:
                            project_id = uuid.UUID(project_id)
                        except ValueError:
                            raise ValueError(f"Invalid project_id format: {project_id}")
                    query = query.filter(SQLQuery.project_id == project_id)
                
                items = query.all()
                result = []
                for item in items:
                    result.append({
                        "id": str(item.id),
                        "question": item.question,
                        "sql": item.sql,
                        "metadata": {
                            "project_id": str(item.project_id),
                            "created_at": datetime.fromtimestamp(item.created_at).isoformat() if item.created_at else None
                        }
                    })
                return result
        except Exception as e:
            print(f"Error retrieving all question-SQL pairs: {str(e)}")
            return []

    def get_all_ddl(self, project_id: str = None, **kwargs) -> list:
        """Get all DDL statements for a project"""
        try:
            with self._get_session() as session:
                query = session.query(DDLStatement)
                if project_id is not None:
                    # Convert project_id to UUID if it's a string
                    if isinstance(project_id, str):
                        try:
                            project_id = uuid.UUID(project_id)
                        except ValueError:
                            raise ValueError(f"Invalid project_id format: {project_id}")
                    query = query.filter(DDLStatement.project_id == project_id)
                
                items = query.all()
                result = []
                for item in items:
                    result.append({
                        "id": str(item.id),
                        "ddl": item.ddl,
                        "metadata": {
                            "project_id": str(item.project_id),
                            "created_at": datetime.fromtimestamp(item.created_at).isoformat() if item.created_at else None
                        }
                    })
                return result
        except Exception as e:
            print(f"Error retrieving all DDL statements: {str(e)}")
            return []
    
   