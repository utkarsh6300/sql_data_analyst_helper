import os
from pathlib import Path

# Get the base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DATABASE_CONFIG = {
    'sqlite': {
        'url': f"sqlite:///{BASE_DIR}/data/sql_app.db",
        'connect_args': {"check_same_thread": False}
    }
}

# Ensure data directory exists
data_dir = BASE_DIR / 'data'
data_dir.mkdir(exist_ok=True)