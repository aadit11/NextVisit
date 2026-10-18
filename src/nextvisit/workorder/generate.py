"""One JSON call per city that publishes violation text. Austin returns an empty order."""

import json
import os
from dataclasses import dataclass

import httpx

from nextvisit.cities import get_city
from nextvisit.workorder.faithfulness import STATIONS, WorkOrderItem, faithfulness_errors

_SETTINGS = ("WORKORDER_API_KEY", "WORKORDER_BASE_URL", "WORKORDER_MODEL")
_ITEM_FIELDS = ("station", "violation_code", "source_span", "step")


@dataclass(frozen=True)
class ClosingWorkOrder:
    items: list[WorkOrderItem]
    reason: str | None = None


def build_work_order(
    city_id: str,
    *,
    cuisine: str | None,
    predicted_codes: list[str],
    codebook: dict[str, str],
    client: httpx.Client | None = None,
) -> list[WorkOrderItem]:
    return closing_work_order(
        city_id,
        cuisine=cuisine,
        predicted_codes=predicted_codes,
        codebook=codebook,
        client=client,
    ).items


def closing_work_order(
    city_id: str,
    *,
    cuisine: str | None,
    predicted_codes: list[str],
    codebook: dict[str, str],
    client: httpx.Client | None = None,
) -> ClosingWorkOrder:
    spec = get_city(city_id)
    if not spec.has_work_order or not predicted_codes:
        return ClosingWorkOrder([])

    missing = [code for code in predicted_codes if not codebook.get(code)]
    if missing:
        return ClosingWorkOrder([], f"No official description for {missing[0]}.")

    settings = _settings()
    if settings is None:
        return ClosingWorkOrder(
            [],
            "WORKORDER_API_KEY, WORKORDER_BASE_URL, and WORKORDER_MODEL are unset.",
        )
    api_key, base_url, model = settings

    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _instructions()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "cuisine": cuisine,
                        "codes": [
                            {
                                "violation_code": code,
                                "official_description": codebook[code],
                            }
                            for code in predicted_codes
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        body = _post(client, _completions_url(base_url), api_key, payload)
    except httpx.HTTPStatusError as exc:
        return ClosingWorkOrder([], f"Work-order call failed (HTTP {exc.response.status_code}).")
    except httpx.HTTPError:
        return ClosingWorkOrder([], "Work-order call failed.")

    try:
        items = _parse_items(body)
    except ValueError as exc:
        return ClosingWorkOrder([], str(exc))

    errors = faithfulness_errors(
        predicted_codes=predicted_codes,
        codebook=codebook,
        cuisine=cuisine,
        items=items,
        require_cuisine=spec.cuisine_in_source,
    )
    if errors:
        return ClosingWorkOrder([], " ".join(errors))
    return ClosingWorkOrder(items)


def _settings() -> tuple[str, str, str] | None:
    values = [os.environ.get(name, "").strip() for name in _SETTINGS]
    if not all(values):
        return None
    return values[0], values[1], values[2]


def _completions_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def _instructions() -> str:
    stations = ", ".join(sorted(STATIONS))
    return (
        "Return one JSON object with the key items. "
        "Each item has station, violation_code, source_span, and step. "
        "Include each given violation code once and no other code. "
        f"station must be one of: {stations}. "
        "Set source_span to the official_description copied exactly. "
        "The step must contain that same source_span unchanged. "
        "If cuisine is not null, every step must contain that cuisine string unchanged."
    )


def _post(
    client: httpx.Client | None,
    url: str,
    api_key: str,
    payload: dict[str, object],
) -> object:
    headers = {"Authorization": f"Bearer {api_key}"}
    if client is None:
        with httpx.Client(timeout=90) as owned:
            response = owned.post(url, headers=headers, json=payload)
    else:
        response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def _complete_item(row: dict[str, object]) -> bool:
    for field in _ITEM_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _parse_items(body: object) -> list[WorkOrderItem]:
    if not isinstance(body, dict):
        raise ValueError("Work order response was not JSON.")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Work order response was not JSON.") from exc
    if not isinstance(content, str):
        raise ValueError("Work order response was not JSON.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Work order response was not JSON.") from exc
    rows = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Work order response did not include an items list.")
    items: list[WorkOrderItem] = []
    for row in rows:
        if not isinstance(row, dict) or not _complete_item(row):
            raise ValueError("Work order item is missing station, violation_code, source_span, or step.")
        items.append(
            WorkOrderItem(
                station=row["station"],
                violation_code=row["violation_code"],
                source_span=row["source_span"],
                step=row["step"],
            )
        )
    return items
