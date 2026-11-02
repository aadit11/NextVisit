from pydantic import BaseModel, ConfigDict, Field


class WorkOrderItemOut(BaseModel):
    station: str
    violation_code: str
    source_span: str
    step: str


class HistoryCode(BaseModel):
    code: str
    description: str | None = None


class VisitOut(BaseModel):
    date: str
    grade: str | None = None
    score: float | None = None
    codes: list[HistoryCode] = []


class MapPlaceOut(BaseModel):
    """Short keys keep a whole city's pins under the host's response limit."""

    model_config = ConfigDict(populate_by_name=True)

    restaurant_id: str = Field(alias="i")
    name: str = Field(alias="n")
    latitude: float = Field(alias="y")
    longitude: float = Field(alias="x")


class RestaurantHit(BaseModel):
    restaurant_id: str
    name: str
    area: str | None = None
    address: str | None = None
    cuisine: str | None = None
    grade: str | None = None
    last_inspection_date: str | None = None
    serious: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    average_stars: float | None = None
    review_count: int = 0


class RestaurantOut(BaseModel):
    city: str
    restaurant_id: str
    name: str | None = None
    address: str | None = None
    cuisine: str | None = None
    area: str | None = None
    hours: str | None = None
    grade: str | None = None
    score: float | None = None
    last_inspection_date: str | None = None
    serious: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    average_stars: float | None = None
    review_count: int = 0
    abstained: bool
    probability: float | None = None
    label: str
    trend: str | None = None
    recent_visit_count: int = 0
    recent_serious_count: int = 0
    peer_count: int = 0
    peer_graded_count: int = 0
    peer_standing: str | None = None
    score_trend: str | None = None
    codes: list[HistoryCode]
    visits: list[VisitOut] = []
    earlier_inspections: int = 0
    history: str = ""
    history_reason: str | None = None
    work_order: list[WorkOrderItemOut]
    work_order_reason: str | None = None
    brief: str = ""
    brief_reason: str | None = None
    reasons: list[str] = []


class AccountIn(BaseModel):
    name: str = ""
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class AccountOut(BaseModel):
    token: str
    name: str
    email: str


class ReviewIn(BaseModel):
    stars: int
    comment: str = ""


class ReviewOut(BaseModel):
    author: str
    stars: int
    comment: str
    created_at: str


class MineOut(BaseModel):
    stars: int
    comment: str


class ReviewListOut(BaseModel):
    average_stars: float | None = None
    review_count: int = 0
    mine: MineOut | None = None
    reviews: list[ReviewOut]


class FacetsOut(BaseModel):
    areas: list[str]
    cuisines: list[str]
    grades: list[str]
