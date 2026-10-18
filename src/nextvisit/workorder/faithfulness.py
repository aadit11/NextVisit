"""Check a work order against the predicted codes and the city's codebook."""

from dataclasses import dataclass

STATIONS = frozenset(
    {
        "cold_holding",
        "hot_holding",
        "handwashing",
        "food_contact",
        "pests",
        "plumbing",
        "supervision",
        "other",
    }
)


@dataclass(frozen=True)
class WorkOrderItem:
    station: str
    violation_code: str
    source_span: str
    step: str


def faithfulness_errors(
    *,
    predicted_codes: list[str],
    codebook: dict[str, str],
    cuisine: str | None,
    items: list[WorkOrderItem],
    require_cuisine: bool,
) -> list[str]:
    errors: list[str] = []
    returned = [item.violation_code for item in items]
    if sorted(returned) != sorted(predicted_codes):
        errors.append("Work order codes must match the predicted codes exactly once each.")
    if len(returned) != len(set(returned)):
        errors.append("A violation code appears more than once.")

    for item in items:
        if item.station not in STATIONS:
            errors.append(f"Unknown station {item.station!r}.")
        description = codebook.get(item.violation_code)
        if description is None:
            errors.append(f"No official description for {item.violation_code}.")
            continue
        if not item.source_span.strip() or item.source_span not in description:
            errors.append(f"source_span for {item.violation_code} is not in the official description.")
        if item.source_span not in item.step:
            errors.append(f"Step for {item.violation_code} drops the official span.")
        if require_cuisine and cuisine and cuisine not in item.step:
            errors.append(f"Step for {item.violation_code} omits the cuisine.")
    return errors
