import os
from pathlib import Path

# Get the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DATABASE_CONFIG = {
    'sqlite': {
        'url': f"sqlite:///{BASE_DIR}/data/sql_app.db",
        'connect_args': {"check_same_thread": False}
    },
    'postgresql': {
        'url': os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/analyst_helper'),
        'connect_args': {}
    }
}

# Vector database configuration
VECTOR_DB_CONFIG = {
    'chroma': {
        'type': 'chroma',
        'path': "./chroma_db",
        'client': "persistent"
    },
    'postgres': {
        'type': 'postgres',
        'database_url': os.getenv('VECTOR_DATABASE_URL', os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/analyst_helper')),
        'n_results': 10,
        'n_results_sql': 10,
        'n_results_documentation': 10,
        'n_results_ddl': 10
    }
}

# Database type selection - can be 'sqlite' or 'postgresql'
# Set via environment variable DATABASE_TYPE, defaults to 'sqlite'
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'postgresql').lower()

# Vector database type selection - can be 'chroma' or 'postgres'
# Set via environment variable VECTOR_DB_TYPE, defaults to 'postgres'
VECTOR_DB_TYPE = os.getenv('VECTOR_DB_TYPE', 'postgres').lower()

# Ensure data directory exists for SQLite
if DATABASE_TYPE == 'sqlite':
    data_dir = BASE_DIR / 'data'
    data_dir.mkdir(exist_ok=True)