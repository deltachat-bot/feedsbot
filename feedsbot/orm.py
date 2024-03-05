"""database"""

from contextlib import contextmanager
from threading import Lock
from typing import Any, Generator

from sqlalchemy import Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

Base: Any = declarative_base()
_Session = sessionmaker(expire_on_commit=False)
_lock = Lock()


class Feed(Base):
    __tablename__ = "feeds"
    url = Column(String, primary_key=True)
    etag = Column(String)
    modified = Column(String)
    latest = Column(String)
    errors = Column(Integer, nullable=False)
    fchats = relationship("Fchat", backref="feed", cascade="all, delete, delete-orphan")

    def __init__(self, **kwargs):
        kwargs.setdefault("errors", 0)
        super().__init__(**kwargs)


class Fchat(Base):
    __tablename__ = "fchats"
    accid = Column(Integer, primary_key=True)
    gid = Column(Integer, primary_key=True)
    feed_url = Column(String, ForeignKey("feeds.url"), primary_key=True)
    filter = Column(String)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    with _lock:
        session: Session = _Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def init(path: str, debug: bool = False) -> None:
    """Initialize engine."""
    engine = create_engine(path, echo=debug)
    Base.metadata.create_all(engine)
    _Session.configure(bind=engine)
