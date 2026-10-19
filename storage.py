"""Módulo de almacenamiento (Data Layer) que implementa el patrón Singleton
para CorporateData y CorporateLog, tanto para AWS DynamoDB como para memoria.
"""

from __future__ import annotations

from decimal import Decimal
import os
import threading
from typing import Any, Protocol

if __package__:
    from .corporate_fields import CORPORATE_DATA_FIELDS
else:
    from corporate_fields import CORPORATE_DATA_FIELDS


class CorporateDataGateway(Protocol):
    """Contrato (Protocol) para el acceso a CorporateData."""

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        ...

    def merge_record(self, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_records(self) -> list[dict[str, Any]]:
        ...


class CorporateLogGateway(Protocol):
    """Contrato (Protocol) para el acceso a CorporateLog (Auditoría)."""

    def write_audit(self, *, cpu_uuid: str, session_id: str, action: str, record_id: str | None = None) -> None:
        ...


def dynamodb_to_json(value: Any) -> Any:
    """Convierte recursivamente los tipos de DynamoDB (como Decimal) a tipos estándar de Python."""
    if isinstance(value, list):
        return [dynamodb_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(k): dynamodb_to_json(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def _to_dynamo(value: Any) -> Any:
    """Convierte floats estándar a Decimal para que DynamoDB los acepte."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _blank_record(record_id: str) -> dict[str, Any]:
    """Genera un registro nuevo con todos los campos corporativos en blanco."""
    item = {field: "" for field in CORPORATE_DATA_FIELDS}
    item["id"] = record_id
    return item


def _merge_item(existing: dict[str, Any] | None, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Combina el registro existente con las actualizaciones (regla de la consigna)."""
    merged = _blank_record(record_id)
    if existing:
        merged.update({str(k): dynamodb_to_json(v) for k, v in existing.items() if k != "id"})
    merged["id"] = record_id
    for key, value in updates.items():
        if key in CORPORATE_DATA_FIELDS:
            merged[key] = value
    return merged


# ==========================================
# 1. SINGLETON PARA CORPORATE DATA (AWS)
# ==========================================
class AwsCorporateDataSingleton:
    """Patrón Singleton para el acceso físico a la tabla CorporateData en AWS DynamoDB."""

    _instance: AwsCorporateDataSingleton | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        import boto3

        self._table = boto3.resource("dynamodb").Table("CorporateData")

    @classmethod
    def instance(cls) -> AwsCorporateDataSingleton:
        """Obtiene la única instancia de CorporateData (Double-checked locking)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resetea la instancia (útil para pruebas)."""
        with cls._lock:
            cls._instance = None

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        response = self._table.get_item(Key={"id": record_id})
        item = response.get("Item")
        return dynamodb_to_json(item) if item else None

    def merge_record(self, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_record(record_id)
        merged = _merge_item(existing, record_id, updates)
        self._table.put_item(Item=_to_dynamo(merged))
        return merged

    def list_records(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        response = self._table.scan()
        items.extend(dynamodb_to_json(i) for i in response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = self._table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(dynamodb_to_json(i) for i in response.get("Items", []))
        return items


# ==========================================
# 2. SINGLETON PARA CORPORATE LOG (AWS)
# ==========================================
class AwsCorporateLogSingleton:
    """Patrón Singleton para el acceso físico a la tabla CorporateLog (Auditoría) en AWS DynamoDB."""

    _instance: AwsCorporateLogSingleton | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        import boto3

        self._table = boto3.resource("dynamodb").Table("CorporateLog")

    @classmethod
    def instance(cls) -> AwsCorporateLogSingleton:
        """Obtiene la única instancia de CorporateLog (Double-checked locking)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resetea la instancia (útil para pruebas)."""
        with cls._lock:
            cls._instance = None

    def write_audit(self, *, cpu_uuid: str, session_id: str, action: str, record_id: str | None = None) -> None:
        import uuid
        from datetime import datetime, timezone

        log_item = {
            "id": str(uuid.uuid4()),
            "CPUid": str(cpu_uuid),
            "sessionid": str(session_id),
            "action": str(action),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        if record_id is not None:
            log_item["record_id"] = str(record_id)

        self._table.put_item(Item=log_item)


# ==========================================
# 3. GATEWAYS EN MEMORIA (PARA TESTS)
# ==========================================
class MemoryCorporateDataGateway:
    """Gateway en memoria bajo patrón Singleton para pruebas sin AWS."""

    _instance: MemoryCorporateDataGateway | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    @classmethod
    def instance(cls) -> MemoryCorporateDataGateway:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._store.get(record_id)
            return dict(item) if item else None

    def merge_record(self, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            existing = self._store.get(record_id)
            merged = _merge_item(existing, record_id, updates)
            self._store[record_id] = dict(merged)
            return dict(merged)

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._store.values()]


class MemoryCorporateLogGateway:
    """Gateway de auditoría en memoria bajo patrón Singleton para pruebas sin AWS."""

    _instance: MemoryCorporateLogGateway | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    @classmethod
    def instance(cls) -> MemoryCorporateLogGateway:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def write_audit(self, *, cpu_uuid: str, session_id: str, action: str, record_id: str | None = None) -> None:
        import uuid
        from datetime import datetime, timezone

        entry = {
            "id": str(uuid.uuid4()),
            "CPUid": str(cpu_uuid),
            "sessionid": str(session_id),
            "action": str(action),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        if record_id is not None:
            entry["record_id"] = str(record_id)

        with self._lock:
            self.entries.append(entry)


# ==========================================
# 4. SELECTORES DE BACKEND (STRATEGY)
# ==========================================
def default_data_gateway() -> CorporateDataGateway:
    """Devuelve el gateway de datos según la variable de entorno TPFI_USE_MEMORY."""
    if os.environ.get("TPFI_USE_MEMORY", "").lower() in ("1", "true", "yes"):
        return MemoryCorporateDataGateway.instance()
    return AwsCorporateDataSingleton.instance()


def default_log_gateway() -> CorporateLogGateway:
    """Devuelve el gateway de log según la variable de entorno TPFI_USE_MEMORY."""
    if os.environ.get("TPFI_USE_MEMORY", "").lower() in ("1", "true", "yes"):
        return MemoryCorporateLogGateway.instance()
    return AwsCorporateLogSingleton.instance()