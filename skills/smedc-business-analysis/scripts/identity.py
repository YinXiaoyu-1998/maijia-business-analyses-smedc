"""Identity helpers for SMEDC report presentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ORGANIZATION_ERROR = (
    "SMEDC account organization is missing or invalid. "
    "Ask an administrator to correct the account organization before generating the report."
)


def unwrap_mcp_payload(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "result" in value and len([key for key in ("result", "payload", "content") if key in value]) == 1:
        return value["result"]
    if "payload" in value and len([key for key in ("result", "payload", "content") if key in value]) == 1:
        return value["payload"]
    content = value.get("content")
    if isinstance(content, list) and len(content) == 1:
        item = content[0]
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                return value
    return value


def organization_name_from_current_user_payload(value: Any) -> str:
    payload = unwrap_mcp_payload(value)
    user = payload.get("user") if isinstance(payload, dict) else None
    organization_name = user.get("organizationName") if isinstance(user, dict) else None
    if not isinstance(organization_name, str) or organization_name.strip() == "":
        raise ValueError(ORGANIZATION_ERROR)
    return organization_name


def organization_name_from_current_user_file(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"current user response not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"current user response is not valid JSON: {path}: {exc}") from exc
    return organization_name_from_current_user_payload(payload)


def organization_name_from_metadata(value: Any) -> str:
    metadata = value.get("metadata") if isinstance(value, dict) else None
    meta = value.get("meta") if isinstance(value, dict) else None
    organization_name = metadata.get("organization_name") if isinstance(metadata, dict) else None
    if organization_name is None and isinstance(meta, dict):
        organization_name = meta.get("organization_name")
    if not isinstance(organization_name, str) or organization_name.strip() == "":
        raise ValueError(ORGANIZATION_ERROR)
    return organization_name
