from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from agent_setup_cli.database.models.agent import Base

DATABASE_URL = "sqlite:///./agent_setup.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
