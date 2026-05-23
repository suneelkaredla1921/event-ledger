import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from gateway.config import get_settings
from gateway.models import Base, EventModel


@dataclass
class EventRecord:
    event_id: str
    account_id: str
    type: str
    amount: float
    currency: str
    event_timestamp: str
    metadata: dict[str, Any] | None = None


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _database_url() -> str:
    return get_settings().gateway_database_url


def configure_database(database_url: str | None = None, *, reset: bool = False) -> None:
    """Initialize or reconfigure the SQLite engine (used at startup and in tests)."""
    global _engine, _session_factory

    if _engine is not None:
        _engine.dispose()

    url = database_url or _database_url()
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    if reset:
        Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)


def init_db() -> None:
    configure_database(reset=False)


def _session() -> Session:
    if _session_factory is None:
        init_db()
    return _session_factory()


def _to_record(row: EventModel) -> EventRecord:
    metadata = json.loads(row.metadata_json) if row.metadata_json else None
    return EventRecord(
        event_id=row.event_id,
        account_id=row.account_id,
        type=row.type,
        amount=row.amount,
        currency=row.currency,
        event_timestamp=row.event_timestamp,
        metadata=metadata,
    )


class Database:
    def is_connected(self) -> bool:
        try:
            if _engine is None:
                init_db()
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_event(self, event_id: str) -> EventRecord | None:
        with _session() as session:
            row = session.get(EventModel, event_id)
            return _to_record(row) if row else None

    def save_event(self, event: EventRecord) -> None:
        with _session() as session:
            session.merge(
                EventModel(
                    event_id=event.event_id,
                    account_id=event.account_id,
                    type=event.type,
                    amount=event.amount,
                    currency=event.currency,
                    event_timestamp=event.event_timestamp,
                    metadata_json=json.dumps(event.metadata) if event.metadata else None,
                )
            )
            session.commit()

    def list_by_account(self, account_id: str) -> list[EventRecord]:
        with _session() as session:
            rows = (
                session.query(EventModel)
                .filter(EventModel.account_id == account_id)
                .order_by(EventModel.event_timestamp.asc())
                .all()
            )
            return [_to_record(row) for row in rows]


db = Database()
