from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, delete, insert, inspect, select
from sqlalchemy import Column, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class SQLMetadataStore:
    def __init__(self, dsn: str) -> None:
        if dsn.startswith("sqlite:///"):
            sqlite_path = dsn.removeprefix("sqlite:///")
            parent = Path(sqlite_path).expanduser().resolve().parent
            parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(dsn, future=True)
        self._meta = MetaData()

        self._documents = Table(
            "documents",
            self._meta,
            Column("uri", String(512), primary_key=True),
            Column("workspace_id", String(256), nullable=False, index=True),
            Column("payload_json", Text, nullable=False),
        )
        self._chunks = Table(
            "chunks",
            self._meta,
            Column("uri", String(512), primary_key=True),
            Column("doc_uri", String(512), nullable=False, index=True),
            Column("workspace_id", String(256), nullable=False, index=True),
            Column("payload_json", Text, nullable=False),
        )
        self._entities = Table(
            "entities",
            self._meta,
            Column("uri", String(512), primary_key=True),
            Column("workspace_id", String(256), primary_key=True, nullable=False, index=True),
            Column("payload_json", Text, nullable=False),
        )
        self._memory = Table(
            "memory_items",
            self._meta,
            Column("uri", String(512), primary_key=True),
            Column("workspace_id", String(256), nullable=False, index=True),
            Column("subject", String(256), nullable=False, index=True),
            Column("payload_json", Text, nullable=False),
        )
        self._checksums = Table(
            "ingest_checksums",
            self._meta,
            Column("workspace_id", String(256), primary_key=True),
            Column("source_path", Text, primary_key=True),
            Column("checksum", String(256), nullable=False),
        )

        try:
            self._meta.create_all(self._engine)
            self._migrate_entities_primary_key_if_needed()
        except SQLAlchemyError as exc:
            if self._engine.dialect.name == "postgresql":
                message = str(exc).lower()
                if "permission denied" in message or "insufficient privilege" in message:
                    username = self._engine.url.username or "<app_user>"
                    raise RuntimeError(
                        "Postgres metadata init failed due to insufficient privileges. "
                        "Grant permissions and retry. Suggested SQL: "
                        f"GRANT USAGE, CREATE ON SCHEMA public TO {username}; "
                        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {username}; "
                        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {username};"
                    ) from exc
            raise

    def _migrate_entities_primary_key_if_needed(self) -> None:
        inspector = inspect(self._engine)
        if "entities" not in set(inspector.get_table_names()):
            return

        pk = inspector.get_pk_constraint("entities")
        constrained = list(pk.get("constrained_columns") or [])
        if constrained == ["uri", "workspace_id"]:
            return

        if self._engine.dialect.name == "postgresql":
            pk_name = pk.get("name")
            with self._engine.begin() as conn:
                if isinstance(pk_name, str) and pk_name:
                    safe_pk = pk_name.replace('"', '""')
                    conn.exec_driver_sql(
                        f'ALTER TABLE entities DROP CONSTRAINT IF EXISTS "{safe_pk}"'
                    )
                conn.exec_driver_sql(
                    "ALTER TABLE entities ADD CONSTRAINT entities_pkey PRIMARY KEY (uri, workspace_id)"
                )
            return

        if self._engine.dialect.name != "sqlite":
            return

        with self._engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS entities__new ("
                "uri VARCHAR(512) NOT NULL, "
                "workspace_id VARCHAR(256) NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "PRIMARY KEY (uri, workspace_id)"
                ")"
            )
            conn.exec_driver_sql(
                "INSERT INTO entities__new (uri, workspace_id, payload_json) "
                "SELECT uri, workspace_id, payload_json FROM entities"
            )
            conn.exec_driver_sql("DROP TABLE entities")
            conn.exec_driver_sql("ALTER TABLE entities__new RENAME TO entities")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_entities_workspace_id ON entities (workspace_id)"
            )

    @staticmethod
    def _encode(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _decode(raw: str) -> dict[str, Any]:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}

    def _upsert(self, table: Table, key_cols: dict[str, Any], payload: dict[str, Any]) -> None:
        with self._engine.begin() as conn:
            conn.execute(delete(table).where(*[table.c[k] == v for k, v in key_cols.items()]))
            row = dict(key_cols)
            row["payload_json"] = self._encode(payload)
            conn.execute(insert(table).values(**row))

    def put_doc(self, uri: str, data: dict[str, Any]) -> None:
        self._upsert(
            self._documents,
            {"uri": uri, "workspace_id": str(data.get("workspace_id", ""))},
            data,
        )

    def put_chunk(self, uri: str, data: dict[str, Any]) -> None:
        self._upsert(
            self._chunks,
            {
                "uri": uri,
                "doc_uri": str(data.get("doc_uri", "")),
                "workspace_id": str(data.get("workspace_id", "")),
            },
            data,
        )

    def put_entity(self, uri: str, data: dict[str, Any]) -> None:
        self._upsert(
            self._entities,
            {"uri": uri, "workspace_id": str(data.get("workspace_id", ""))},
            data,
        )

    def put_memory(self, uri: str, data: dict[str, Any]) -> None:
        self._upsert(
            self._memory,
            {
                "uri": uri,
                "workspace_id": str(data.get("workspace_id", "")),
                "subject": str(data.get("subject", "")),
            },
            data,
        )

    def _get_payload(self, table: Table, *, uri: str) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(table.c.payload_json).where(table.c.uri == uri).limit(1)
            ).first()
        if row is None:
            return None
        return self._decode(str(row.payload_json))

    def get_doc(self, uri: str) -> dict[str, Any] | None:
        return self._get_payload(self._documents, uri=uri)

    def get_chunk(self, uri: str) -> dict[str, Any] | None:
        return self._get_payload(self._chunks, uri=uri)

    def get_entity(self, uri: str) -> dict[str, Any] | None:
        return self._get_payload(self._entities, uri=uri)

    def get_memory(self, uri: str) -> dict[str, Any] | None:
        return self._get_payload(self._memory, uri=uri)

    def delete_memory(self, uri: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(delete(self._memory).where(self._memory.c.uri == uri))
        return result.rowcount > 0

    def list_memory(self, *, workspace_id: str, subject: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(self._memory.c.payload_json).where(
                    self._memory.c.workspace_id == workspace_id,
                    self._memory.c.subject == subject,
                )
            )
            for row in rows:
                out.append(self._decode(str(row.payload_json)))
        return out

    def list_chunks_by_doc(self, *, doc_uri: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(self._chunks.c.payload_json).where(self._chunks.c.doc_uri == doc_uri)
            )
            for row in rows:
                out.append(self._decode(str(row.payload_json)))
        return out

    def delete_chunk(self, *, uri: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(delete(self._chunks).where(self._chunks.c.uri == uri))
        return result.rowcount > 0

    def get_checksum(self, *, workspace_id: str, source_path: str) -> str | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(self._checksums.c.checksum).where(
                    self._checksums.c.workspace_id == workspace_id,
                    self._checksums.c.source_path == source_path,
                )
            ).first()
        if row is None:
            return None
        return str(row.checksum)

    def set_checksum(self, *, workspace_id: str, source_path: str, checksum: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                delete(self._checksums).where(
                    self._checksums.c.workspace_id == workspace_id,
                    self._checksums.c.source_path == source_path,
                )
            )
            conn.execute(
                insert(self._checksums).values(
                    workspace_id=workspace_id,
                    source_path=source_path,
                    checksum=checksum,
                )
            )
