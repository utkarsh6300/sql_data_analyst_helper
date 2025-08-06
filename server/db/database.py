from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.config import DATABASE_CONFIG, DATABASE_TYPE

# Import Base from models
from models.base import Base

# Import all models to ensure they are registered with SQLAlchemy
from models.models import Project, Chat
from models.vectorDbModels import SQLQuery, DDLStatement, DocumentationItem

# Select database configuration based on DATABASE_TYPE
db_config = DATABASE_CONFIG[DATABASE_TYPE]

engine = create_engine(
    db_config['url'],
    connect_args=db_config['connect_args']
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_all_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

def drop_all_tables():
    """Drop all database tables"""
    Base.metadata.drop_all(bind=engine)