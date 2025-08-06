from sqlalchemy.orm import Session
from typing import List, Optional, TypeVar, Generic
from models.base import Base

T = TypeVar('T', bound=Base)

class DatabaseOperations:
    """Generic database operations for all models"""
    
    @staticmethod
    def create(db: Session, model_class: type[T], **kwargs) -> T:
        """Create a new record"""
        db_obj = model_class(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    @staticmethod
    def get_by_id(db: Session, model_class: type[T], id: int) -> Optional[T]:
        """Get a record by ID"""
        return db.query(model_class).filter(model_class.id == id).first()
    
    @staticmethod
    def get_all(db: Session, model_class: type[T], skip: int = 0, limit: int = 100) -> List[T]:
        """Get all records with pagination"""
        return db.query(model_class).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, obj: T, **kwargs) -> T:
        """Update a record"""
        for key, value in kwargs.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj
    
    @staticmethod
    def delete(db: Session, obj: T) -> bool:
        """Delete a record"""
        db.delete(obj)
        db.commit()
        return True
    
    @staticmethod
    def filter_by(db: Session, model_class: type[T], **kwargs) -> List[T]:
        """Filter records by given criteria"""
        return db.query(model_class).filter_by(**kwargs).all()
    
    @staticmethod
    def count(db: Session, model_class: type[T], **kwargs) -> int:
        """Count records by given criteria"""
        query = db.query(model_class)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query.count() 