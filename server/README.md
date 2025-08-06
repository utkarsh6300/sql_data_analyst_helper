# Analyst Helper Server

A FastAPI server for managing projects with SQL query generation capabilities.

## Database Schema

### Projects
Projects now support multiple DDL statements, documentation items, and question-SQL pairs through separate tables:

- **projects**: Main project information (name, created_at)
- **sql_queries**: Stores question-SQL pairs with embeddings
- **ddl_statements**: Stores DDL statements with embeddings  
- **documentation_items**: Stores documentation with embeddings
- **chats**: Stores conversation history

### New Table Structure

#### SQLQuery Table
- `id`: Primary key
- `project_id`: Foreign key to projects
- `question`: The natural language question
- `sql`: The corresponding SQL query
- `embedding`: Vector embedding (populated by vector service)
- `sql_metadata`: JSON metadata
- `created_at`: Unix timestamp

#### DDLStatement Table
- `id`: Primary key
- `project_id`: Foreign key to projects
- `ddl`: The DDL statement
- `embedding`: Vector embedding (populated by vector service)
- `ddl_metadata`: JSON metadata
- `created_at`: Unix timestamp

#### DocumentationItem Table
- `id`: Primary key
- `project_id`: Foreign key to projects
- `documentation`: The documentation text
- `embedding`: Vector embedding (populated by vector service)
- `documentation_metadata`: JSON metadata
- `created_at`: Unix timestamp

## API Endpoints

### Legacy Endpoints (Backward Compatible)
- `POST /projects/{project_id}/documentation` - Add single documentation item
- `POST /projects/{project_id}/sample-queries` - Add sample queries as batch
- `POST /projects/{project_id}/schema` - Add single DDL statement

### New Multiple Items Endpoints
- `POST /projects/{project_id}/documentation-items` - Add multiple documentation items
- `POST /projects/{project_id}/question-sql-pairs` - Add multiple question-SQL pairs
- `POST /projects/{project_id}/ddl-statements` - Add multiple DDL statements

### Example Usage

#### Add Multiple Documentation Items
```json
POST /projects/1/documentation-items
{
  "documentation_items": [
    {
      "documentation": "This table stores user information",
      "metadata": {"category": "user_management", "version": "1.0"}
    },
    {
      "documentation": "This table stores order details",
      "metadata": {"category": "orders", "version": "1.0"}
    }
  ]
}
```

#### Add Multiple Question-SQL Pairs
```json
POST /projects/1/question-sql-pairs
{
  "question_sql_pairs": [
    {
      "question": "How many users are there?",
      "sql": "SELECT COUNT(*) FROM users",
      "metadata": {"difficulty": "easy", "category": "aggregation"}
    },
    {
      "question": "Show me all active orders",
      "sql": "SELECT * FROM orders WHERE status = 'active'",
      "metadata": {"difficulty": "medium", "category": "filtering"}
    }
  ]
}
```

#### Add Multiple DDL Statements
```json
POST /projects/1/ddl-statements
{
  "ddl_statements": [
    {
      "ddl": "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(255))",
      "metadata": {"table_name": "users", "version": "1.0"}
    },
    {
      "ddl": "CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, amount DECIMAL(10,2))",
      "metadata": {"table_name": "orders", "version": "1.0"}
    }
  ]
}
```

## Benefits of New Structure

1. **Scalability**: Support for unlimited DDL statements, documentation items, and question-SQL pairs per project
2. **Metadata**: Rich metadata support for each item
3. **Vector Search**: Each item gets its own embedding for better semantic search
4. **Backward Compatibility**: Legacy endpoints still work
5. **Atomic Operations**: Each item is stored atomically with proper error handling
6. **Better Organization**: Clear separation of concerns with dedicated tables

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Set up database configuration in `db/config.py`
3. Run the server: `python main.py`

The database tables will be created automatically when the server starts. 