"""One JSON call per city that publishes violation text. Austin returns an empty order."""

from nextvisit.cities import get_city
from nextvisit.workorder.faithfulness import WorkOrderItem


def build_work_order(
    city_id: str,
    *,
    cuisine: str | None,
    predicted_codes: list[str],
    codebook: dict[str, str],
) -> list[WorkOrderItem]:
    spec = get_city(city_id)
    if not spec.has_work_order or not predicted_codes:
        return []
    raise NotImplementedError(
        f"The hosted work-order call for {spec.name} is not wired yet. "
        "It must receive only the cuisine, the predicted codes, and the codebook text."
    )
