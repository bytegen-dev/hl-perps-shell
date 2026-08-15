from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from hl_core.config import get_settings
from hl_core.db.exceptions import WalletDatabaseNotConfiguredError


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    url = database_url or settings.database_url
    if not url:
        raise WalletDatabaseNotConfiguredError(
            "Set HL_DATABASE_URL to use the local Postgres wallet store."
        )
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_database(database_url: str | None = None) -> None:
    from hl_core.db.models import Base

    Base.metadata.create_all(get_engine(database_url))
