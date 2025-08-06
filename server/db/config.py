import os
import dotenv

dotenv.load_dotenv()

# Database configuration
DATABASE_CONFIG = {
    'postgresql': {
        'url': os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/analyst_helper'),
        'connect_args': {}
    }
}

# Vector database configuration
VECTOR_DB_CONFIG = {
    'postgres': {
        'type': 'postgres',
        'database_url': os.getenv('VECTOR_DATABASE_URL', os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/analyst_helper')),
        'n_results': 10,
        'n_results_sql': 10,
        'n_results_documentation': 10,
        'n_results_ddl': 10
    }
}

# Database type selection - only supports 'postgresql'
# Set via environment variable DATABASE_TYPE, defaults to 'postgresql'
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'postgresql').lower()

# Vector database type selection - only supports 'postgres'
# Set via environment variable VECTOR_DB_TYPE, defaults to 'postgres'
VECTOR_DB_TYPE = os.getenv('VECTOR_DB_TYPE', 'postgres').lower()