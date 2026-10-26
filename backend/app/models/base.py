from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, LargeBinary, MetaData
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import DeclarativeBase

# JSONB en Postgres, JSON en SQLite: el mismo modelo sirve para ambos.
JsonType = JSON().with_variant(JSONB(), "postgresql")
BlobType = LargeBinary().with_variant(BYTEA(), "postgresql")
TZDateTime = DateTime(timezone=True)

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JsonType,
        list[Any]: JsonType,
        bytes: BlobType,
        datetime: TZDateTime,
    }
