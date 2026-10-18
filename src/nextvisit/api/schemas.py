from pydantic import BaseModel


class WorkOrderItemOut(BaseModel):
    station: str
    violation_code: str
    source_span: str
    step: str


class RestaurantOut(BaseModel):
    city: str
    restaurant_id: str
    name: str | None = None
    cuisine: str | None = None
    abstained: bool
    probability: float | None = None
    label: str
    codes: list[str]
    work_order: list[WorkOrderItemOut]
