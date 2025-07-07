#!/usr/bin/env python3
"""
Test script to verify OpenAI embeddings integration with ChromaDB.
"""

import os
import shutil
from dotenv import load_dotenv
from vectorDB.chroma import ChromaDB_VectorStore

def test_openai_embeddings():
    """Test OpenAI embeddings integration."""
    
    # Load environment variables
    load_dotenv()
    
    # Check if OpenAI API key is available
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("❌ OPENAI_API_KEY not found in environment variables")
        print("Please set your OpenAI API key in the .env file")
        return False
    
    # Test configuration
    test_db_path = "./test_openai_chroma_db"
    
    # Clean up any existing test database
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)
    
    print("🧪 Testing OpenAI Embeddings Integration")
    print("=" * 50)
    
    try:
        # Initialize vector store
        print("1. Initializing vector store with OpenAI embeddings...")
        vector_store = ChromaDB_VectorStore(config={
            "path": test_db_path,
            "client": "persistent"
        })
        print("✅ Vector store initialized successfully")
        
        # Test data
        test_documentation = "This is a test documentation about customer data. It contains information about user profiles and purchase history."
        test_ddl = "CREATE TABLE customers (id INT PRIMARY KEY, name VARCHAR(100), email VARCHAR(255), created_at TIMESTAMP);"
        test_question = "How many customers do we have?"
        test_sql = "SELECT COUNT(*) FROM customers;"
        
        # Test adding documentation
        print("2. Testing documentation storage...")
        doc_id = vector_store.add_documentation(test_documentation, project_id="test_project")
        if doc_id:
            print(f"✅ Documentation stored with ID: {doc_id}")
        else:
            print("❌ Failed to store documentation")
            return False
        
        # Test adding DDL
        print("3. Testing DDL storage...")
        ddl_id = vector_store.add_ddl(test_ddl, project_id="test_project")
        if ddl_id:
            print(f"✅ DDL stored with ID: {ddl_id}")
        else:
            print("❌ Failed to store DDL")
            return False
        
        # Test adding question-SQL pair
        print("4. Testing question-SQL storage...")
        sql_id = vector_store.add_question_sql(test_question, test_sql, project_id="test_project")
        if sql_id:
            print(f"✅ Question-SQL pair stored with ID: {sql_id}")
        else:
            print("❌ Failed to store question-SQL pair")
            return False
        
        # Test retrieval
        print("5. Testing similarity search...")
        query = "Show me the total number of users"
        
        # Test documentation retrieval
        similar_docs = vector_store.get_related_documentation(query, project_id="test_project")
        print(f"✅ Retrieved {len(similar_docs)} similar documentation entries")
        
        # Test DDL retrieval
        similar_ddl = vector_store.get_related_ddl(query, project_id="test_project")
        print(f"✅ Retrieved {len(similar_ddl)} similar DDL entries")
        
        # Test SQL retrieval
        similar_sql = vector_store.get_similar_question_sql(query, project_id="test_project")
        print(f"✅ Retrieved {len(similar_sql)} similar SQL queries")
        
        # Clean up
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)
            print("🧹 Test database cleaned up")
        
        print("\n🎉 All tests passed! OpenAI embeddings are working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        # Clean up on error
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)
        return False

if __name__ == "__main__":
    success = test_openai_embeddings()
    exit(0 if success else 1) 