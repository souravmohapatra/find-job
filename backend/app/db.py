from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().sqlalchemy_url(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
        pool_timeout=10,
    )


def get_db() -> Generator[Session, None, None]:
    with sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
