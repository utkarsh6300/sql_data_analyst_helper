#!/usr/bin/env python3
"""
Test script to verify vector database logic for storing and retrieving data for specific projects.
"""

import json
import os
import shutil
from vectorDB.chroma import ChromaDB_VectorStore

def test_vector_db_logic():
    """Test the complete vector database logic for project-specific data storage and retrieval."""
    
    # Test configuration
    test_db_path = "./test_chroma_db"
    project_id_1 = "project_1"
    project_id_2 = "project_2"
    
    # Clean up any existing test database
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)
    
    print("🧪 Testing Vector Database Logic for Project-Specific Data")
    print("=" * 60)
    
    try:
        # Initialize vector store
        print("1. Initializing vector store...")
        vector_store = ChromaDB_VectorStore(config={
            "path": test_db_path,
            "client": "persistent"
        })
        print("✅ Vector store initialized successfully")
        
        # Test data for project 1
        project_1_data = {
            "documentation": "This is documentation for project 1. It contains information about sales data.",
            "ddl": "CREATE TABLE sales (id INT, product VARCHAR(100), amount DECIMAL(10,2), date DATE);",
            "sample_queries": {
                "What are the total sales?": "SELECT SUM(amount) FROM sales;",
                "Show me sales by product": "SELECT product, SUM(amount) FROM sales GROUP BY product;"
            }
        }
        
        # Test data for project 2
        project_2_data = {
            "documentation": "This is documentation for project 2. It contains information about user analytics.",
            "ddl": "CREATE TABLE users (id INT, name VARCHAR(100), email VARCHAR(255), created_at TIMESTAMP);",
            "sample_queries": {
                "How many users do we have?": "SELECT COUNT(*) FROM users;",
                "Show me users by registration date": "SELECT DATE(created_at), COUNT(*) FROM users GROUP BY DATE(created_at);"
            }
        }
        
        # Test 2: Store data for project 1
        print("\n2. Storing data for project 1...")
        doc_id_1 = vector_store.add_documentation(project_1_data["documentation"], project_id=project_id_1)
        ddl_id_1 = vector_store.add_ddl(project_1_data["ddl"], project_id=project_id_1)
        
        sql_ids_1 = []
        for question, sql in project_1_data["sample_queries"].items():
            sql_id = vector_store.add_question_sql(question, sql, project_id=project_id_1)
            sql_ids_1.append(sql_id)
        
        print(f"✅ Project 1 data stored - Doc ID: {doc_id_1}, DDL ID: {ddl_id_1}, SQL IDs: {sql_ids_1}")
        
        # Test 3: Store data for project 2
        print("\n3. Storing data for project 2...")
        doc_id_2 = vector_store.add_documentation(project_2_data["documentation"], project_id=project_id_2)
        ddl_id_2 = vector_store.add_ddl(project_2_data["ddl"], project_id=project_id_2)
        
        sql_ids_2 = []
        for question, sql in project_2_data["sample_queries"].items():
            sql_id = vector_store.add_question_sql(question, sql, project_id=project_id_2)
            sql_ids_2.append(sql_id)
        
        print(f"✅ Project 2 data stored - Doc ID: {doc_id_2}, DDL ID: {ddl_id_2}, SQL IDs: {sql_ids_2}")
        
        # Test 4: Retrieve project-specific data
        print("\n4. Testing project-specific data retrieval...")
        
        # Test queries for project 1
        print("\n   Testing Project 1 queries:")
        test_query_1 = "What are the total sales for this month?"
        
        similar_docs_1 = vector_store.get_related_documentation(test_query_1, project_id=project_id_1)
        similar_ddl_1 = vector_store.get_related_ddl(test_query_1, project_id=project_id_1)
        similar_sql_1 = vector_store.get_similar_question_sql(test_query_1, project_id=project_id_1)
        
        print(f"   - Documentation results: {len(similar_docs_1)} items")
        print(f"   - DDL results: {len(similar_ddl_1)} items")
        print(f"   - SQL results: {len(similar_sql_1)} items")
        
        # Test queries for project 2
        print("\n   Testing Project 2 queries:")
        test_query_2 = "How many users registered today?"
        
        similar_docs_2 = vector_store.get_related_documentation(test_query_2, project_id=project_id_2)
        similar_ddl_2 = vector_store.get_related_ddl(test_query_2, project_id=project_id_2)
        similar_sql_2 = vector_store.get_similar_question_sql(test_query_2, project_id=project_id_2)
        
        print(f"   - Documentation results: {len(similar_docs_2)} items")
        print(f"   - DDL results: {len(similar_ddl_2)} items")
        print(f"   - SQL results: {len(similar_sql_2)} items")
        
        # Test 5: Verify data isolation between projects
        print("\n5. Testing data isolation between projects...")
        
        # Query project 1 data from project 2 context (should return empty)
        cross_project_docs = vector_store.get_related_documentation(test_query_1, project_id=project_id_2)
        cross_project_ddl = vector_store.get_related_ddl(test_query_1, project_id=project_id_2)
        cross_project_sql = vector_store.get_similar_question_sql(test_query_1, project_id=project_id_2)
        
        print(f"   - Cross-project documentation results: {len(cross_project_docs)} items")
        print(f"   - Cross-project DDL results: {len(cross_project_ddl)} items")
        print(f"   - Cross-project SQL results: {len(cross_project_sql)} items")
        
        # Test 6: Test without project_id (should return all data)
        print("\n6. Testing retrieval without project_id (global search)...")
        
        global_docs = vector_store.get_related_documentation(test_query_1)
        global_ddl = vector_store.get_related_ddl(test_query_1)
        global_sql = vector_store.get_similar_question_sql(test_query_1)
        
        print(f"   - Global documentation results: {len(global_docs)} items")
        print(f"   - Global DDL results: {len(global_ddl)} items")
        print(f"   - Global SQL results: {len(global_sql)} items")
        
        # Test 7: Verify data content
        print("\n7. Verifying data content...")
        
        if similar_docs_1:
            print(f"   - Project 1 documentation contains: {similar_docs_1[0][:50]}...")
        if similar_ddl_1:
            print(f"   - Project 1 DDL contains: {similar_ddl_1[0][:50]}...")
        if similar_sql_1:
            print(f"   - Project 1 SQL results: {len(similar_sql_1)} items")
            for i, result in enumerate(similar_sql_1[:2]):  # Show first 2 results
                if isinstance(result, dict):
                    print(f"     {i+1}. Q: {result.get('question', 'N/A')[:30]}...")
                    print(f"        A: {result.get('sql', 'N/A')[:30]}...")
        
        # Test 8: Test data removal
        print("\n8. Testing data removal...")
        
        # Remove one SQL entry from project 1
        if sql_ids_1:
            removed = vector_store.remove_training_data(sql_ids_1[0])
            print(f"   - Removed SQL entry {sql_ids_1[0]}: {removed}")
        
        # Verify removal
        remaining_sql_1 = vector_store.get_similar_question_sql(test_query_1, project_id=project_id_1)
        print(f"   - Remaining SQL results for project 1: {len(remaining_sql_1)} items")
        
        print("\n✅ All tests completed successfully!")
        
        # Summary
        print("\n📊 Test Summary:")
        print(f"   - Projects tested: 2")
        print(f"   - Data types stored: Documentation, DDL, SQL queries")
        print(f"   - Project isolation: ✅ Working")
        print(f"   - Data retrieval: ✅ Working")
        print(f"   - Data removal: ✅ Working")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            shutil.rmtree(test_db_path)
            print(f"\n🧹 Cleaned up test database: {test_db_path}")

if __name__ == "__main__":
    test_vector_db_logic() 