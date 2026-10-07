from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


class SearchCriteria(BaseModel):
    query: str = ""
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    industry: str | None = None
    employees_min: int | None = None
    employees_max: int | None = None
    funding_min: float | None = None
    funding_max: float | None = None
    latest_round_min: float | None = None
    latest_round_max: float | None = None
    funding_stage: str | None = None
    funded_within_months: int | None = None
    founded_min: int | None = None
    founded_max: int | None = None
    score_min: int | None = None
    sort: str = "prospect_score"
    order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class SavedInput(BaseModel):
    company_id: str
    tags: list[str] = []
    notes: str = ""
    priority: str = "medium"
    status: str = "new"


class OutreachInput(BaseModel):
    company_id: str
    status: str = "new"
    contact_person: str | None = None
    channel: str | None = None
    message: str | None = None
    response: str | None = None
    contact_date: datetime | None = None
    follow_up_date: datetime | None = None
    notes: str | None = None


class SearchInput(BaseModel):
    name: str
    criteria: SearchCriteria


class CompanyCandidate(BaseModel):
    name: str
    legal_name: str | None = None
    description: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    other_urls: list[str] = []
    location: dict[str, Any] = {}
    industry: list[str] = []
    sub_industries: list[str] = []
    business_model: list[str] = []
    founded_year: int | None = None
    incorporated_year: int | None = None
    company_status: str | None = None
    employees: dict[str, Any] = {}
    funding: dict[str, Any] = {}
    founders: list[dict[str, Any]] = []
    executives: list[dict[str, Any]] = []
    external_ids: dict[str, str] = {}
    source_name: str
    source_url: str
    source_type: str = "official API"
    demo: bool = False
