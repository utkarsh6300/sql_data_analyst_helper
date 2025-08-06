import json
from typing import List, Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Disable ChromaDB telemetry completely
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import chromadb
import pandas as pd
from chromadb.config import Settings
from chromadb.utils import embedding_functions
# default_ef = embedding_function

from vectorDB.utils import deterministic_uuid

# # Use OpenAI embeddings for better consistency with the LLM
# openai_ef = embedding_functions.OpenAIEmbeddingFunction(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     model_name="text-embedding-ada-002"
# )

# Fallback to default if OpenAI key is not available
try:
    default_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
except Exception:
    default_ef = embedding_functions.DefaultEmbeddingFunction()


class ChromaDB_VectorStore():
    def __init__(self, config=None):
        if config is None:
            config = {} 

        path = config.get("path", ".")
        self.embedding_function = config.get("embedding_function", default_ef)
        curr_client = config.get("client", "persistent")
        collection_metadata = config.get("collection_metadata", None)
        self.n_results_sql = config.get("n_results_sql", config.get("n_results", 10))
        self.n_results_documentation = config.get("n_results_documentation", config.get("n_results", 10))
        self.n_results_ddl = config.get("n_results_ddl", config.get("n_results", 10))

        if curr_client == "persistent":
            self.chroma_client = chromadb.PersistentClient(
                path=path, settings=Settings(anonymized_telemetry=False)
            )
        elif curr_client == "in-memory":
            self.chroma_client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False)
            )
        elif isinstance(curr_client, chromadb.api.client.Client):
            # allow providing client directly
            self.chroma_client = curr_client
        else:
            raise ValueError(f"Unsupported client was set in config: {curr_client}")

        # Handle existing collections with different embedding functions
        self._initialize_collections(collection_metadata)

    def _initialize_collections(self, collection_metadata):
        """Initialize collections with proper error handling for embedding function mismatches."""
        
        # List of collection names to initialize
        collections = ["documentation", "ddl", "sql"]
        
        for collection_name in collections:
            try:
                # Try to get existing collection
                existing_collection = self.chroma_client.get_collection(name=collection_name)
                print(f"✅ Found existing collection: {collection_name}")
            except Exception:
                # Collection doesn't exist, create it
                print(f"📝 Creating new collection: {collection_name}")
                existing_collection = None
            
            # Create or recreate collection with current embedding function
            try:
                if collection_name == "documentation":
                    self.documentation_collection = self.chroma_client.get_or_create_collection(
                        name="documentation",
                        embedding_function=self.embedding_function,
                        metadata=collection_metadata,
                    )
                elif collection_name == "ddl":
                    self.ddl_collection = self.chroma_client.get_or_create_collection(
                        name="ddl",
                        embedding_function=self.embedding_function,
                        metadata=collection_metadata,
                    )
                elif collection_name == "sql":
                    self.sql_collection = self.chroma_client.get_or_create_collection(
                        name="sql",
                        embedding_function=self.embedding_function,
                        metadata=collection_metadata,
                    )
            except ValueError as e:
                if "Embedding function name mismatch" in str(e):
                    print(f"⚠️  Embedding function mismatch for {collection_name}. Recreating collection...")
                    # Delete and recreate the collection with new embedding function
                    try:
                        self.chroma_client.delete_collection(name=collection_name)
                        print(f"🗑️  Deleted old collection: {collection_name}")
                    except Exception:
                        pass
                    
                    # Recreate with new embedding function
                    if collection_name == "documentation":
                        self.documentation_collection = self.chroma_client.create_collection(
                            name="documentation",
                            embedding_function=self.embedding_function,
                            metadata=collection_metadata,
                        )
                    elif collection_name == "ddl":
                        self.ddl_collection = self.chroma_client.create_collection(
                            name="ddl",
                            embedding_function=self.embedding_function,
                            metadata=collection_metadata,
                        )
                    elif collection_name == "sql":
                        self.sql_collection = self.chroma_client.create_collection(
                            name="sql",
                            embedding_function=self.embedding_function,
                            metadata=collection_metadata,
                        )
                    print(f"✅ Recreated collection {collection_name} with new embedding function")
                else:
                    raise e

    def generate_embedding(self, data: str, **kwargs) -> List[float]:
        embedding = self.embedding_function([data])
        if len(embedding) == 1:
            return embedding[0]
        return embedding

    def add_question_sql(self, question: str, sql: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add a question-SQL pair to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            question_sql_json = json.dumps(
                {
                    "question": question,
                    "sql": sql,
                    "project_id": project_id
                },
                ensure_ascii=False,
            )
            id = deterministic_uuid(question_sql_json) + "-sql"
            self.sql_collection.add(
                documents=question_sql_json,
                embeddings=self.generate_embedding(question_sql_json),
                ids=id,
                metadatas=[{"project_id": project_id}],
            )
            return id
        except Exception as e:
            print(f"Error adding question-SQL pair: {str(e)}")
            return None

    def add_ddl(self, ddl: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add DDL statement to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            id = deterministic_uuid(ddl) + "-ddl"
            self.ddl_collection.add(
                documents=ddl,
                embeddings=self.generate_embedding(ddl),
                ids=id,
                metadatas=[{"project_id": project_id}],
            )
            return id
        except Exception as e:
            print(f"Error adding DDL: {str(e)}")
            return None

    def add_documentation(self, documentation: str, project_id: str = None, **kwargs) -> Optional[str]:
        """
        Add documentation to the vector store.
        Returns the ID if successful, None if failed.
        """
        try:
            id = deterministic_uuid(documentation) + "-doc"
            self.documentation_collection.add(
                documents=documentation,
                embeddings=self.generate_embedding(documentation),
                ids=id,
                metadatas=[{"project_id": project_id}],
            )
            return id
        except Exception as e:
            print(f"Error adding documentation: {str(e)}")
            return None

    def get_training_data(self, **kwargs) -> pd.DataFrame:
        sql_data = self.sql_collection.get()

        df = pd.DataFrame()

        if sql_data is not None:
            # Extract the documents and ids
            documents = [json.loads(doc) for doc in sql_data["documents"]]
            ids = sql_data["ids"]

            # Create a DataFrame
            df_sql = pd.DataFrame(
                {
                    "id": ids,
                    "question": [doc["question"] for doc in documents],
                    "content": [doc["sql"] for doc in documents],
                }
            )

            df_sql["training_data_type"] = "sql"

            df = pd.concat([df, df_sql])

        ddl_data = self.ddl_collection.get()

        if ddl_data is not None:
            # Extract the documents and ids
            documents = [doc for doc in ddl_data["documents"]]
            ids = ddl_data["ids"]

            # Create a DataFrame
            df_ddl = pd.DataFrame(
                {
                    "id": ids,
                    "question": [None for doc in documents],
                    "content": [doc for doc in documents],
                }
            )

            df_ddl["training_data_type"] = "ddl"

            df = pd.concat([df, df_ddl])

        doc_data = self.documentation_collection.get()

        if doc_data is not None:
            # Extract the documents and ids
            documents = [doc for doc in doc_data["documents"]]
            ids = doc_data["ids"]

            # Create a DataFrame
            df_doc = pd.DataFrame(
                {
                    "id": ids,
                    "question": [None for doc in documents],
                    "content": [doc for doc in documents],
                }
            )

            df_doc["training_data_type"] = "documentation"

            df = pd.concat([df, df_doc])

        return df

    def remove_training_data(self, id: str, **kwargs) -> bool:
        if id.endswith("-sql"):
            self.sql_collection.delete(ids=id)
            return True
        elif id.endswith("-ddl"):
            self.ddl_collection.delete(ids=id)
            return True
        elif id.endswith("-doc"):
            self.documentation_collection.delete(ids=id)
            return True
        else:
            return False

    def remove_collection(self, collection_name: str) -> bool:
        """
        This function can reset the collection to empty state.

        Args:
            collection_name (str): sql or ddl or documentation

        Returns:
            bool: True if collection is deleted, False otherwise
        """
        if collection_name == "sql":
            self.chroma_client.delete_collection(name="sql")
            self.sql_collection = self.chroma_client.create_collection(
                name="sql", embedding_function=self.embedding_function
            )
            return True
        elif collection_name == "ddl":
            self.chroma_client.delete_collection(name="ddl")
            self.ddl_collection = self.chroma_client.create_collection(
                name="ddl", embedding_function=self.embedding_function
            )
            return True
        elif collection_name == "documentation":
            self.chroma_client.delete_collection(name="documentation")
            self.documentation_collection = self.chroma_client.create_collection(
                name="documentation", embedding_function=self.embedding_function
            )
            return True
        else:
            return False

    @staticmethod
    def _extract_documents(query_results) -> list:
        """
        Static method to extract the documents from the results of a query.

        Args:
            query_results (pd.DataFrame): The dataframe to use.

        Returns:
            List[str] or None: The extracted documents, or an empty list or
            single document if an error occurred.
        """
        if query_results is None:
            return []

        if "documents" in query_results:
            documents = query_results["documents"]

            if len(documents) == 1 and isinstance(documents[0], list):
                try:
                    documents = [json.loads(doc) for doc in documents[0]]
                except Exception as e:
                    return documents[0]

            return documents

    def get_similar_question_sql(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get similar SQL queries for a given question.
        Includes error handling and validation.
        """
        try:
            # Only apply project_id filter if it's provided
            where = {"project_id": project_id} if project_id is not None else None
            results = self.sql_collection.query(
                query_texts=[question],
                n_results=self.n_results_sql,
                where=where
            )
            return ChromaDB_VectorStore._extract_documents(results)
        except Exception as e:
            print(f"Error retrieving similar queries: {str(e)}")
            return []

    def get_related_ddl(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get related DDL statements for a given question.
        Includes error handling and validation.
        """
        try:
            # Only apply project_id filter if it's provided
            where = {"project_id": project_id} if project_id is not None else None
            results = self.ddl_collection.query(
                query_texts=[question],
                n_results=self.n_results_ddl,
                where=where
            )
            return ChromaDB_VectorStore._extract_documents(results)
        except Exception as e:
            print(f"Error retrieving DDL context: {str(e)}")
            return []

    def get_related_documentation(self, question: str, project_id: str = None, **kwargs) -> list:
        """
        Get related documentation for a given question.
        Includes error handling and validation.
        """
        try:
            # Only apply project_id filter if it's provided
            where = {"project_id": project_id} if project_id is not None else None
            results = self.documentation_collection.query(
                query_texts=[question],
                n_results=self.n_results_documentation,
                where=where
            )
            return ChromaDB_VectorStore._extract_documents(results)
        except Exception as e:
            print(f"Error retrieving documentation: {str(e)}")
            return []

    def migrate_embeddings(self, new_embedding_function=None):
        """
        Migrate existing collections to use a new embedding function.
        This will recreate all collections with the new embedding function.
        
        Args:
            new_embedding_function: The new embedding function to use. If None, uses the current one.
        
        Returns:
            bool: True if migration was successful, False otherwise
        """
        if new_embedding_function:
            self.embedding_function = new_embedding_function
        
        try:
            print("🔄 Starting embedding function migration...")
            
            # Get existing data before deleting collections
            existing_data = {}
            
            # Backup SQL data
            try:
                sql_data = self.sql_collection.get()
                if sql_data and sql_data.get("documents"):
                    existing_data["sql"] = sql_data
                    print(f"📋 Backed up {len(sql_data['documents'])} SQL entries")
            except Exception as e:
                print(f"⚠️  Could not backup SQL data: {e}")
            
            # Backup DDL data
            try:
                ddl_data = self.ddl_collection.get()
                if ddl_data and ddl_data.get("documents"):
                    existing_data["ddl"] = ddl_data
                    print(f"📋 Backed up {len(ddl_data['documents'])} DDL entries")
            except Exception as e:
                print(f"⚠️  Could not backup DDL data: {e}")
            
            # Backup documentation data
            try:
                doc_data = self.documentation_collection.get()
                if doc_data and doc_data.get("documents"):
                    existing_data["documentation"] = doc_data
                    print(f"📋 Backed up {len(doc_data['documents'])} documentation entries")
            except Exception as e:
                print(f"⚠️  Could not backup documentation data: {e}")
            
            # Delete and recreate collections
            collections = ["sql", "ddl", "documentation"]
            for collection_name in collections:
                try:
                    self.chroma_client.delete_collection(name=collection_name)
                    print(f"🗑️  Deleted collection: {collection_name}")
                except Exception as e:
                    print(f"⚠️  Could not delete collection {collection_name}: {e}")
            
            # Recreate collections with new embedding function
            self._initialize_collections(None)
            
            # Restore data with new embeddings
            restored_count = 0
            
            # Restore SQL data
            if "sql" in existing_data:
                try:
                    for i, doc in enumerate(existing_data["sql"]["documents"]):
                        metadata = existing_data["sql"]["metadatas"][i] if existing_data["sql"]["metadatas"] else {}
                        self.sql_collection.add(
                            documents=doc,
                            embeddings=self.generate_embedding(doc),
                            ids=existing_data["sql"]["ids"][i],
                            metadatas=[metadata]
                        )
                    restored_count += len(existing_data["sql"]["documents"])
                    print(f"✅ Restored {len(existing_data['sql']['documents'])} SQL entries")
                except Exception as e:
                    print(f"❌ Failed to restore SQL data: {e}")
            
            # Restore DDL data
            if "ddl" in existing_data:
                try:
                    for i, doc in enumerate(existing_data["ddl"]["documents"]):
                        metadata = existing_data["ddl"]["metadatas"][i] if existing_data["ddl"]["metadatas"] else {}
                        self.ddl_collection.add(
                            documents=doc,
                            embeddings=self.generate_embedding(doc),
                            ids=existing_data["ddl"]["ids"][i],
                            metadatas=[metadata]
                        )
                    restored_count += len(existing_data["ddl"]["documents"])
                    print(f"✅ Restored {len(existing_data['ddl']['documents'])} DDL entries")
                except Exception as e:
                    print(f"❌ Failed to restore DDL data: {e}")
            
            # Restore documentation data
            if "documentation" in existing_data:
                try:
                    for i, doc in enumerate(existing_data["documentation"]["documents"]):
                        metadata = existing_data["documentation"]["metadatas"][i] if existing_data["documentation"]["metadatas"] else {}
                        self.documentation_collection.add(
                            documents=doc,
                            embeddings=self.generate_embedding(doc),
                            ids=existing_data["documentation"]["ids"][i],
                            metadatas=[metadata]
                        )
                    restored_count += len(existing_data["documentation"]["documents"])
                    print(f"✅ Restored {len(existing_data['documentation']['documents'])} documentation entries")
                except Exception as e:
                    print(f"❌ Failed to restore documentation data: {e}")
            
            print(f"🎉 Migration completed! Restored {restored_count} total entries")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False