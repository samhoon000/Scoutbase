from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class SearchCriteria(BaseModel):
    query: str = Field("", max_length=120)
    country_code: str | None = Field(None, max_length=2)
    countries: list[str] = Field(default_factory=list, max_length=25)
    region: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    industry: str | None = Field(None, max_length=80)
    industries: list[str] = Field(default_factory=list, max_length=25)
    company_types: list[str] = Field(default_factory=list, max_length=15)
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
    growth_score_min: int | None = None
    analytics_opportunity_min: int | None = Field(None, ge=0, le=10)
    recently_founded_years: int | None = Field(None, ge=1, le=50)
    active_company: bool = False
    growing_headcount: bool = False
    multiple_growth_signals: bool = False
    high_transaction_volume: bool = False
    large_customer_base: bool = False
    multiple_products: bool = False
    operational_data_heavy: bool = False
    sort: str = "prospect_score"
    order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    force_refresh: bool = False

    @model_validator(mode="after")
    def validate_ranges(self):
        for lower, upper in (("employees_min", "employees_max"), ("funding_min", "funding_max"),
                             ("latest_round_min", "latest_round_max"), ("founded_min", "founded_max")):
            start, end = getattr(self, lower), getattr(self, upper)
            if start is not None and start < 0 or end is not None and end < 0:
                raise ValueError(f"{lower} and {upper} must be nonnegative")
            if start is not None and end is not None and start > end:
                raise ValueError(f"{lower} must not exceed {upper}")
        if self.score_min is not None and not 0 <= self.score_min <= 100:
            raise ValueError("score_min must be 0–100")
        if self.growth_score_min is not None and not 0 <= self.growth_score_min <= 20:
            raise ValueError("growth_score_min must be 0–20")
        if self.funded_within_months is not None and self.funded_within_months < 1:
            raise ValueError("funded_within_months must be positive")
        if any(len(code) != 2 or not code.isalpha() for code in self.countries):
            raise ValueError("countries must contain two-letter country codes")
        return self


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


class SearchRenameInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


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
    technology_signals: dict[str, Any] = {}
    filing_signals: dict[str, Any] = {}
    source_name: str
    source_url: str
    source_type: str = "official API"
