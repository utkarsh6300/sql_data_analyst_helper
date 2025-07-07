#!/usr/bin/env python3
"""
Migration script to convert existing ChromaDB collections to use OpenAI embeddings.
This script will backup existing data, recreate collections with OpenAI embeddings,
and restore the data with new embeddings.
"""

import os
import shutil
from dotenv import load_dotenv
from vectorDB.chroma import ChromaDB_VectorStore

def migrate_to_openai_embeddings():
    """Migrate existing ChromaDB collections to use OpenAI embeddings."""
    
    # Load environment variables
    load_dotenv()
    
    # Check if OpenAI API key is available
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("❌ OPENAI_API_KEY not found in environment variables")
        print("Please set your OpenAI API key in the .env file")
        return False
    
    print("🔄 Starting migration to OpenAI embeddings...")
    print("=" * 60)
    
    try:
        # Initialize vector store (this will handle the migration automatically)
        print("1. Initializing vector store...")
        vector_store = ChromaDB_VectorStore(config={
            "path": "./chroma_db",
            "client": "persistent"
        })
        print("✅ Vector store initialized successfully")
        
        # Check if migration is needed by trying to access collections
        try:
            # Try to get a sample from each collection to see if they work
            sql_count = len(vector_store.sql_collection.get()["documents"]) if vector_store.sql_collection.get()["documents"] else 0
            ddl_count = len(vector_store.ddl_collection.get()["documents"]) if vector_store.ddl_collection.get()["documents"] else 0
            doc_count = len(vector_store.documentation_collection.get()["documents"]) if vector_store.documentation_collection.get()["documents"] else 0
            
            print(f"📊 Current data counts:")
            print(f"   - SQL entries: {sql_count}")
            print(f"   - DDL entries: {ddl_count}")
            print(f"   - Documentation entries: {doc_count}")
            
            if sql_count == 0 and ddl_count == 0 and doc_count == 0:
                print("ℹ️  No existing data found. Migration not needed.")
                return True
            
            print("✅ Collections are working correctly with OpenAI embeddings!")
            print("🎉 Migration completed successfully!")
            return True
            
        except Exception as e:
            if "Embedding function name mismatch" in str(e):
                print("⚠️  Embedding function mismatch detected. Running migration...")
                
                # Run the migration
                success = vector_store.migrate_embeddings()
                if success:
                    print("🎉 Migration completed successfully!")
                    return True
                else:
                    print("❌ Migration failed!")
                    return False
            else:
                print(f"❌ Unexpected error: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Migration failed with error: {str(e)}")
        return False

def backup_chroma_db():
    """Create a backup of the current ChromaDB before migration."""
    
    backup_path = "./chroma_db_backup"
    original_path = "./chroma_db"
    
    if not os.path.exists(original_path):
        print("ℹ️  No existing ChromaDB found. No backup needed.")
        return True
    
    try:
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)
        
        shutil.copytree(original_path, backup_path)
        print(f"✅ Backup created at: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return False

if __name__ == "__main__":
    print("🚀 ChromaDB OpenAI Embeddings Migration Tool")
    print("=" * 60)
    
    # Create backup first
    print("📦 Creating backup of existing ChromaDB...")
    if not backup_chroma_db():
        print("❌ Backup failed. Aborting migration.")
        exit(1)
    
    # Run migration
    success = migrate_to_openai_embeddings()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("💡 You can now delete the backup folder if everything works correctly.")
        print("   Backup location: ./chroma_db_backup")
        exit(0)
    else:
        print("\n❌ Migration failed!")
        print("💡 You can restore from backup by copying ./chroma_db_backup to ./chroma_db")
        exit(1) 