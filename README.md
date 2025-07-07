# Analyst Helper

A full-stack application that helps analysts generate SQL queries using natural language. The application combines a React frontend with a FastAPI backend and uses ChromaDB for vector storage and similarity search.

## Features

- **Natural Language to SQL**: Convert natural language queries to SQL using AI
- **Project Management**: Organize queries by projects with documentation and schema
- **Vector Search**: Use ChromaDB for similarity search across documentation and sample queries
- **Feedback System**: Provide feedback on generated SQL to improve future results
- **Sample Queries**: Store and reuse sample queries for better context

## Tech Stack

### Backend
- **FastAPI**: Modern Python web framework
- **SQLAlchemy**: Database ORM
- **ChromaDB**: Vector database for similarity search
- **OpenAI**: AI model for SQL generation
- **SQLite**: Local database storage

### Frontend
- **React 19**: Modern React with hooks
- **Material-UI**: UI component library
- **Vite**: Build tool and dev server
- **React Router**: Client-side routing

## Project Structure

```
analyst-helper/
├── server/                 # FastAPI backend
│   ├── main.py            # Main application entry point
│   ├── models.py          # SQLAlchemy models
│   ├── schemas.py         # Pydantic schemas
│   ├── database.py        # Database configuration
│   ├── config.py          # Application configuration
│   ├── services/          # Business logic
│   │   └── sql_generator.py
│   └── vectorDB/          # Vector database utilities
│       ├── chroma.py
│       └── utils.py
├── UI/                    # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── services/      # API services
│   │   └── main.jsx       # App entry point
│   ├── package.json
│   └── vite.config.js
├── requirements.txt       # Python dependencies
└── README.md
```

## Setup and Installation

### Prerequisites

- Python 3.8+
- Node.js 18+
- npm or yarn

### Backend Setup

1. Navigate to the project root:
   ```bash
   cd analyst-helper
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key and other configurations
   ```

5. Run the backend server:
   ```bash
   cd server
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend Setup

1. Navigate to the UI directory:
   ```bash
   cd UI
   ```

2. Install Node.js dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

The frontend will be available at `http://localhost:5173` and the backend API at `http://localhost:8000`.

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=sqlite:///./data/sql_app.db
CHROMA_DB_PATH=./chroma_db
```

## OpenAI Embeddings Configuration

The application uses OpenAI embeddings for vector similarity search to ensure consistency with the LLM used for SQL generation. This provides better semantic understanding and more accurate retrieval of relevant context.

### Testing OpenAI Embeddings

To verify that OpenAI embeddings are working correctly:

```bash
cd server
python test_openai_embeddings.py
```

This test script will:
1. Check if your OpenAI API key is configured
2. Initialize ChromaDB with OpenAI embeddings
3. Test storing and retrieving documentation, DDL, and sample queries
4. Verify similarity search functionality

### Migrating Existing Data

If you have existing ChromaDB data created with the default embeddings, you'll need to migrate it to use OpenAI embeddings:

```bash
cd server
python migrate_to_openai_embeddings.py
```

This migration script will:
1. Create a backup of your existing ChromaDB data
2. Detect embedding function mismatches
3. Automatically migrate all collections to use OpenAI embeddings
4. Restore all your existing data with new embeddings
5. Provide detailed progress feedback

**Note**: The migration process will temporarily recreate your collections, but all your data will be preserved and restored with the new embeddings.

### Fallback Configuration

If OpenAI embeddings are not available (e.g., API key missing or network issues), the system will automatically fall back to default sentence transformer embeddings. You'll see a warning message in the logs when this happens.

### Benefits of OpenAI Embeddings

- **Consistency**: Same embedding model as the LLM for better semantic alignment
- **Quality**: More sophisticated understanding of text similarity
- **Performance**: Better retrieval of relevant context for SQL generation

## API Endpoints

### Projects
- `POST /projects/` - Create a new project
- `GET /projects/` - List all projects
- `GET /projects/{project_id}` - Get project details
- `POST /projects/{project_id}/documentation` - Add project documentation
- `POST /projects/{project_id}/sample-queries` - Add sample queries
- `POST /projects/{project_id}/schema` - Add database schema

### Chats
- `GET /projects/{project_id}/chats` - Get project chats
- `POST /projects/{project_id}/chats` - Create a new chat
- `POST /chats/{chat_id}/generate` - Generate SQL from natural language
- `POST /chats/{chat_id}/feedback` - Provide feedback on generated SQL

## Usage

1. **Create a Project**: Start by creating a new project and adding your database schema
2. **Add Documentation**: Provide documentation about your database structure and business logic
3. **Add Sample Queries**: Include example queries to help the AI understand your data patterns
4. **Generate SQL**: Use natural language to describe what you want to query
5. **Provide Feedback**: Rate the generated SQL to improve future results

## Development

### Running Tests

```bash
# Backend tests
cd server
pytest

# Frontend tests
cd UI
npm test
```

### Code Formatting

```bash
# Python
black server/
isort server/

# JavaScript/React
cd UI
npm run lint
npm run format
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 