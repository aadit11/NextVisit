from pydantic import BaseModel


class WorkOrderItemOut(BaseModel):
    station: str
    violation_code: str
    source_span: str
    step: str


class HistoryCode(BaseModel):
    code: str
    description: str | None = None


class RestaurantHit(BaseModel):
    restaurant_id: str
    name: str
    area: str | None = None
    address: str | None = None


class RestaurantOut(BaseModel):
    city: str
    restaurant_id: str
    name: str | None = None
    address: str | None = None
    cuisine: str | None = None
    abstained: bool
    probability: float | None = None
    label: str
    codes: list[HistoryCode]
    work_order: list[WorkOrderItemOut]
    work_order_reason: str | None = None
