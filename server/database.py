from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import DATABASE_CONFIG

Base = declarative_base()

engine = create_engine(
    DATABASE_CONFIG['sqlite']['url'],
    connect_args=DATABASE_CONFIG['sqlite']['connect_args']
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()