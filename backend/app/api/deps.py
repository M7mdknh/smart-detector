from collections.abc import Generator

from sqlalchemy.orm import Session

from app.logging_config import correlation_id_var, new_correlation_id
from app.storage.db import get_session


def db_session() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def correlation_id() -> str:
    cid = correlation_id_var.get("")
    if not cid:
        cid = new_correlation_id()
        correlation_id_var.set(cid)
    return cid
