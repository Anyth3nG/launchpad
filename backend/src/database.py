"""Database connection and ORM models for Launchpad."""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_DATABASE_URL = os.environ.get("DATABASE_URL")
if not _DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the environment")

engine = create_engine(_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class Deployment(Base):
    """Represents a container deployment managed by Launchpad.

    Tracks the lifecycle of a deployed container from creation through
    shutdown, including which image and repo it originated from and
    the host port it was assigned.
    """

    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_name = Column(String, nullable=False)
    container_id = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="running")  # 'running' | 'down'
    repo_name = Column(String, nullable=False)
    port = Column(String, nullable=True)  # host:container/proto format; null if no ports exposed
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
