from vectorDB.factory import VectorStoreFactory
from db.config import VECTOR_DB_TYPE
import uuid

class VectorService:
    _vector_store = None
    _vector_db_type = None
    
    @classmethod
    def initialize(cls, vector_db_type=None, config=None):
        """
        Initialize the vector store
        
        Args:
            vector_db_type: Type of vector database ('postgres')
            config: Additional configuration for the vector store
        """
        if vector_db_type is None:
            vector_db_type = VECTOR_DB_TYPE
            
        try:
            cls._vector_store = VectorStoreFactory.create_vector_store(vector_db_type, config)
            cls._vector_db_type = vector_db_type
            print(f"✅ {vector_db_type.upper()} vector database initialized successfully")
        except Exception as e:
            print(f"⚠️  Warning: Failed to initialize {vector_db_type} vector database: {e}")
            print("🔄 Falling back to default vector database...")
            # Try to fall back to postgres
            try:
                cls._vector_store = VectorStoreFactory.create_vector_store('postgres', config)
                cls._vector_db_type = 'postgres'
                print(f"✅ Fallback to POSTGRES vector database successful")
            except Exception as fallback_error:
                print(f"❌ Failed to initialize fallback vector database: {fallback_error}")
                raise
    
    @classmethod
    def get_vector_store(cls):
        """Get the vector store instance"""
        if cls._vector_store is None:
            cls.initialize()
        return cls._vector_store
    
    @classmethod
    def get_vector_db_type(cls):
        """Get the current vector database type"""
        if cls._vector_store is None:
            cls.initialize()
        return cls._vector_db_type
    
    @classmethod
    def add_documentation(cls, documentation: str, project_id: str):
        """Add documentation to vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.add_documentation(documentation, project_id=project_id)
    
    @classmethod
    def add_question_sql(cls, question: str, sql: str, project_id: str):
        """Add question-SQL pair to vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.add_question_sql(question, sql, project_id=project_id)
    
    @classmethod
    def add_ddl(cls, ddl: str, project_id: str):
        """Add DDL to vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.add_ddl(ddl, project_id=project_id)
    
    @classmethod
    def get_related_documentation(cls, query: str, project_id: str):
        """Get related documentation from vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_related_documentation(query, project_id=project_id)
    
    @classmethod
    def get_related_ddl(cls, query: str, project_id: str):
        """Get related DDL from vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_related_ddl(query, project_id=project_id)
    
    @classmethod
    def get_similar_question_sql(cls, query: str, project_id: str):
        """Get similar question-SQL pairs from vector store"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_similar_question_sql(query, project_id=project_id)
    
    @classmethod
    def delete_project(cls, project_id: str):
        """Delete all vector data for a project"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.delete_project(project_id)
    
    @classmethod
    def get_all_documentation(cls, project_id: str):
        """Get all documentation items for a project"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_all_documentation(project_id=project_id)
    
    @classmethod
    def get_all_question_sql(cls, project_id: str):
        """Get all question-SQL pairs for a project"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_all_question_sql(project_id=project_id)
    
    @classmethod
    def get_all_ddl(cls, project_id: str):
        """Get all DDL statements for a project"""
        vector_store = cls.get_vector_store()
        # Convert string project_id to UUID if needed
        if isinstance(project_id, str):
            try:
                project_id = uuid.UUID(project_id)
            except ValueError:
                pass  # Keep as string if not a valid UUID
        return vector_store.get_all_ddl(project_id=project_id)
    
    @classmethod
    def delete_documentation(cls, item_id: str):
        """Delete a specific documentation item by ID"""
        vector_store = cls.get_vector_store()
        return vector_store.remove_training_data(item_id)
    
    @classmethod
    def delete_question_sql(cls, item_id: str):
        """Delete a specific question-SQL pair by ID"""
        vector_store = cls.get_vector_store()
        return vector_store.remove_training_data(item_id)
    
    @classmethod
    def delete_ddl(cls, item_id: str):
        """Delete a specific DDL statement by ID"""
        vector_store = cls.get_vector_store()
        return vector_store.remove_training_data(item_id) 