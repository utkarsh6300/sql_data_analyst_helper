# Analyst Helper API

A FastAPI-based application that provides SQL generation capabilities using AI and vector search.

## Project Structure

The project has been refactored into a clean, modular architecture with clear separation of concerns:

```
server/
├── main.py                 # Application entry point
├── routes/                 # API route handlers
│   ├── __init__.py
│   ├── projects.py         # Project-related endpoints
│   ├── chats.py           # Chat-related endpoints
│   └── project_chats.py   # Project-specific chat endpoints
├── services/              # Business logic layer
│   ├── __init__.py
│   ├── project_service.py    # Project business logic
│   ├── chat_service.py       # Chat business logic
│   ├── project_chat_service.py # Project chat business logic
│   ├── vector_service.py     # Vector database operations
│   ├── sql_generator.py      # SQL generation logic
│   └── llm.py               # LLM integration
├── db/                    # Database layer
│   ├── __init__.py
│   ├── config.py          # Database configuration
│   ├── database.py        # Database connection setup
│   ├── operations.py      # Generic database operations
│   └── repositories.py    # Model-specific database operations
├── models/                # Data models
│   ├── base.py           # Base model class
│   ├── models.py         # SQLAlchemy models
│   └── vectorDbModels.py # Vector database models
├── schemas/               # Pydantic schemas
│   └── schemas.py        # Request/response schemas
├── vectorDB/             # Vector database integration
│   ├── chroma.py         # ChromaDB integration
│   ├── postgres.py       # PostgreSQL vector integration
│   └── utils.py          # Vector utilities
└── requirements.txt      # Python dependencies
```

## Architecture Overview

### 1. Routes Layer (`routes/`)
- **Purpose**: Handle HTTP requests and responses
- **Responsibilities**: 
  - Input validation
  - Request routing
  - Response formatting
  - Error handling
- **Files**:
  - `projects.py`: Project CRUD operations
  - `chats.py`: Chat operations and SQL generation
  - `project_chats.py`: Project-specific chat management

### 2. Services Layer (`services/`)
- **Purpose**: Business logic and orchestration
- **Responsibilities**:
  - Business rules implementation
  - Data transformation
  - External service integration
  - Transaction management
- **Files**:
  - `project_service.py`: Project business logic
  - `chat_service.py`: Chat and SQL generation logic
  - `project_chat_service.py`: Project chat operations
  - `vector_service.py`: Vector database operations
  - `sql_generator.py`: SQL generation using LLM
  - `llm.py`: LLM integration

### 3. Database Layer (`db/`)
- **Purpose**: Data persistence and access
- **Responsibilities**:
  - Database connections
  - CRUD operations
  - Query optimization
  - Transaction management
- **Files**:
  - `config.py`: Database configuration
  - `database.py`: Database connection setup
  - `operations.py`: Generic database operations
  - `repositories.py`: Model-specific operations

### 4. Models Layer (`models/`)
- **Purpose**: Data structure definitions
- **Responsibilities**:
  - Database schema definition
  - Data validation
  - Relationship mapping
- **Files**:
  - `base.py`: Base model class
  - `models.py`: SQLAlchemy ORM models
  - `vectorDbModels.py`: Vector database models

### 5. Schemas Layer (`schemas/`)
- **Purpose**: API request/response validation
- **Responsibilities**:
  - Input validation
  - Response serialization
  - API documentation
- **Files**:
  - `schemas.py`: Pydantic schemas for all endpoints

## Key Design Patterns

### Repository Pattern
- **Location**: `db/repositories.py`
- **Purpose**: Abstract database operations
- **Benefits**: 
  - Testability
  - Code reusability
  - Separation of concerns

### Service Layer Pattern
- **Location**: `services/`
- **Purpose**: Encapsulate business logic
- **Benefits**:
  - Business rule centralization
  - Transaction management
  - External service integration

### Dependency Injection
- **Usage**: Throughout the application
- **Purpose**: Loose coupling between components
- **Benefits**:
  - Testability
  - Flexibility
  - Maintainability

## API Endpoints

### Projects
- `POST /projects/` - Create a new project
- `GET /projects/` - Get all projects
- `GET /projects/{project_id}` - Get a specific project
- `POST /projects/{project_id}/documentation` - Update project documentation
- `POST /projects/{project_id}/sample-queries` - Add sample queries
- `POST /projects/{project_id}/schema` - Add DDL schema

### Chats
- `GET /chats/{chat_id}` - Get a specific chat
- `POST /chats/` - Create a new chat
- `POST /chats/{chat_id}/generate` - Generate SQL for a query
- `POST /chats/{chat_id}/feedback` - Provide feedback on generated SQL
- `PATCH /chats/{chat_id}` - Update chat settings

### Project Chats
- `GET /projects/{project_id}/chats` - Get all chats for a project
- `POST /projects/{project_id}/chats` - Create a new chat for a project

## Vector Database Configuration

The application supports multiple vector database backends for storing and searching embeddings:

### Supported Vector Databases

1. **PostgreSQL with pgvector** (Default)
   - Uses PostgreSQL with the pgvector extension
   - Configured via `VECTOR_DATABASE_URL` environment variable
   - Falls back to `DATABASE_URL` if not specified

2. **ChromaDB**
   - Local file-based vector database
   - Stores data in `./chroma_db` directory by default

### Configuration

Set the vector database type using environment variables:

```bash
# Use PostgreSQL (default)
VECTOR_DB_TYPE=postgres

# Use ChromaDB
VECTOR_DB_TYPE=chroma
```

### Runtime Switching

You can switch vector databases at runtime using the API:

```bash
# Switch to ChromaDB
curl -X POST "http://localhost:8000/projects/switch-vector-db" \
  -H "Content-Type: application/json" \
  -d '{"vector_db_type": "chroma"}'

# Switch to PostgreSQL
curl -X POST "http://localhost:8000/projects/switch-vector-db" \
  -H "Content-Type: application/json" \
  -d '{"vector_db_type": "postgres"}'

# Get current vector database info
curl "http://localhost:8000/projects/vector-db-info"
```

### Health Check

The health check endpoint shows the current vector database:

```bash
curl "http://localhost:8000/health"
# Returns: {"status": "healthy", "database": "POSTGRESQL", "vector_database": "POSTGRES"}
```

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Run the application:
   ```bash
   uvicorn main:app --reload
   ```

4. Access the API documentation:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Benefits of Refactoring

1. **Maintainability**: Clear separation of concerns makes the code easier to maintain
2. **Testability**: Each layer can be tested independently
3. **Scalability**: New features can be added without affecting existing code
4. **Reusability**: Common operations are abstracted into reusable components
5. **Readability**: Code is organized logically and easy to navigate
6. **Flexibility**: Easy to swap implementations (e.g., different databases, LLM providers) 