import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableClient, TableServiceClient
from azure.identity import DefaultAzureCredential

PARTITION_KEY = "vnet"
TABLE_NAME = "vnets"


def _get_table_client() -> TableClient:
    """Open the `vnets` table, creating it if needed."""
    # Set only for local development against Azurite.
    local_connection_string = os.environ.get("STORAGE_CONNECTION_STRING")
    if local_connection_string:
        table_service = TableServiceClient.from_connection_string(local_connection_string)
    else:
        table_service = TableServiceClient(
            endpoint=os.environ["TABLE_ENDPOINT"], credential=DefaultAzureCredential()
        )
    table_service.create_table_if_not_exists(TABLE_NAME)
    return table_service.get_table_client(TABLE_NAME)


def _entity_to_record(table_entity: Mapping[str, Any]) -> dict:
    """Rebuild a VNet record from its stored table row."""
    record = json.loads(table_entity["data"])
    record["createdAt"] = table_entity["createdAt"]
    return record


def save_record(record: dict) -> None:
    """Stamp `createdAt` and upsert the record, keyed by VNet name."""
    record["createdAt"] = datetime.now(UTC).isoformat()
    record_without_timestamp = {key: value for key, value in record.items() if key != "createdAt"}
    _get_table_client().upsert_entity(
        {
            "PartitionKey": PARTITION_KEY,
            "RowKey": record["name"],
            "createdAt": record["createdAt"],
            "data": json.dumps(record_without_timestamp),
        }
    )


def get_record(vnet_name: str) -> dict | None:
    """Return the stored record for `vnet_name`, or None if it does not exist."""
    try:
        return _entity_to_record(_get_table_client().get_entity(PARTITION_KEY, vnet_name))
    except ResourceNotFoundError:
        return None


def list_records() -> list[dict]:
    """Return all stored VNet records."""
    table_entities = _get_table_client().query_entities(f"PartitionKey eq '{PARTITION_KEY}'")
    return [_entity_to_record(table_entity) for table_entity in table_entities]
