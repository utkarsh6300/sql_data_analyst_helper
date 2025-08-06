from typing import Optional, Dict, Any
from db.config import VECTOR_DB_TYPE, VECTOR_DB_CONFIG

class VectorStoreFactory:
    """Factory class for creating vector store instances"""
    
    @staticmethod
    def create_vector_store(vector_db_type: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Create a vector store instance based on the specified type
        
        Args:
            vector_db_type: Type of vector database ('postgres')
            config: Additional configuration for the vector store
            
        Returns:
            Vector store instance
        """
        if vector_db_type is None:
            vector_db_type = VECTOR_DB_TYPE
            
        if config is None:
            config = VECTOR_DB_CONFIG.get(vector_db_type, {})
        
        if vector_db_type == 'postgres':
            from vectorDB.postgres import PostgresDB_VectorStore
            return PostgresDB_VectorStore(config=config)
        else:
            raise ValueError(f"Unsupported vector database type: {vector_db_type}")
    
    @staticmethod
    def get_supported_types():
        """Get list of supported vector database types"""
        return ['postgres'] 