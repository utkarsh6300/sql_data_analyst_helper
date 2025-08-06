from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from db.config import DATABASE_TYPE
from db.database import create_all_tables
from services.vector_service import VectorService

# Import routes
from routes import projects, chats, project_chats

# Initialize database tables
create_all_tables()

# Initialize vector store
VectorService.initialize()

app = FastAPI(title="Analyst Helper API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router)
app.include_router(chats.router)
app.include_router(project_chats.router)

@app.get("/")
def read_root():
    """Root endpoint"""
    return {"message": "Analyst Helper API", "version": "1.0.0"}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "database": DATABASE_TYPE.upper(),
        "vector_database": VectorService.get_vector_db_type().upper()
    }