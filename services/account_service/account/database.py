import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from account.config import get_settings
from account.models import AccountModel, Base, TransactionModel


@dataclass
class TransactionRecord:
    event_id: str
    type: str
    amount: float
    currency: str
    event_timestamp: str
    metadata: dict[str, Any] | None = None


@dataclass
class AccountRecord:
    account_id: str
    currency: str | None = None
    transactions: dict[str, TransactionRecord] = field(default_factory=dict)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _database_url() -> str:
    return get_settings().account_database_url


def configure_database(database_url: str | None = None, *, reset: bool = False) -> None:
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


def _to_transaction(row: TransactionModel) -> TransactionRecord:
    metadata = json.loads(row.metadata_json) if row.metadata_json else None
    return TransactionRecord(
        event_id=row.event_id,
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

    def get_account(self, account_id: str) -> AccountRecord | None:
        with _session() as session:
            row = session.get(AccountModel, account_id)
            if row is None:
                return None
            txs = (
                session.query(TransactionModel)
                .filter(TransactionModel.account_id == account_id)
                .all()
            )
            return AccountRecord(
                account_id=row.account_id,
                currency=row.currency,
                transactions={tx.event_id: _to_transaction(tx) for tx in txs},
            )

    def get_transaction(self, account_id: str, event_id: str) -> TransactionRecord | None:
        with _session() as session:
            row = (
                session.query(TransactionModel)
                .filter(
                    TransactionModel.account_id == account_id,
                    TransactionModel.event_id == event_id,
                )
                .first()
            )
            return _to_transaction(row) if row else None

    def add_transaction(self, account_id: str, tx: TransactionRecord) -> bool:
        """Returns False if event_id already exists for this account."""
        with _session() as session:
            existing = (
                session.query(TransactionModel)
                .filter(
                    TransactionModel.account_id == account_id,
                    TransactionModel.event_id == tx.event_id,
                )
                .first()
            )
            if existing is not None:
                return False

            account = session.get(AccountModel, account_id)
            if account is None:
                account = AccountModel(account_id=account_id, currency=tx.currency)
                session.add(account)
            elif account.currency is None:
                account.currency = tx.currency

            session.add(
                TransactionModel(
                    event_id=tx.event_id,
                    account_id=account_id,
                    type=tx.type,
                    amount=tx.amount,
                    currency=tx.currency,
                    event_timestamp=tx.event_timestamp,
                    metadata_json=json.dumps(tx.metadata) if tx.metadata else None,
                )
            )
            session.commit()
            return True

    def compute_balance(self, account_id: str) -> float | None:
        with _session() as session:
            account = session.get(AccountModel, account_id)
            if account is None:
                return None
            txs = (
                session.query(TransactionModel)
                .filter(TransactionModel.account_id == account_id)
                .all()
            )
            total = 0.0
            for row in txs:
                if row.type == "CREDIT":
                    total += row.amount
                elif row.type == "DEBIT":
                    total -= row.amount
            return round(total, 2)

    def list_transactions(self, account_id: str) -> list[TransactionRecord]:
        with _session() as session:
            rows = (
                session.query(TransactionModel)
                .filter(TransactionModel.account_id == account_id)
                .order_by(TransactionModel.event_timestamp.asc())
                .all()
            )
            return [_to_transaction(row) for row in rows]


db = Database()
