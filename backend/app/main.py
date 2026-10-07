from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO, StringIO
import csv
import json
import re
import uuid
from bson import ObjectId
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pymongo import ASCENDING, DESCENDING
from .config import settings
from .database import db, initialize
from .diagnostics import provider_status
from .filter_taxonomy import industry_aliases
from .models import OutreachInput, SavedInput, SearchCriteria, SearchInput, SearchRenameInput, now
from .pipeline import run_discovery, run_enrichment

USER_ID = "local-user"  # Replace with authenticated principal in auth middleware.
SORTS = {"prospect_score", "funding.total_amount_usd", "employees.min", "founded_year", "funding.last_funding_date", "signals.growth_score", "signals.analytics_opportunity_score"}
STATUSES = {"new", "researching", "contacted", "follow-up", "responded", "rejected", "interested", "converted"}


def clean(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {("id" if k == "_id" else k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def company_id(value):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid company id")
    return ObjectId(value)


def mongo_filter(criteria: SearchCriteria):
    q = {}
    clauses = []
    if criteria.query:
        q["name"] = {"$regex": __import__("re").escape(criteria.query[:100]), "$options": "i"}
    selected_countries = [x.upper() for x in (criteria.countries or ([criteria.country_code] if criteria.country_code else []))]
    if selected_countries:
        q["location.country_code"] = {"$in": selected_countries}
    if criteria.region:
        q["location.region"] = criteria.region
    if criteria.city:
        q["location.city"] = criteria.city
    selected_industries = criteria.industries or ([criteria.industry] if criteria.industry else [])
    if selected_industries:
        names = set().union(*(industry_aliases(value) for value in selected_industries))
        q["industry"] = {"$in": [re.compile("^" + re.escape(value) + "$", re.I) for value in names]}
    if criteria.company_types:
        q["business_model"] = {"$in": [re.compile("^" + re.escape(value) + "$", re.I) for value in criteria.company_types]}
    if criteria.employees_min is not None or criteria.employees_max is not None:
        exact = {}
        interval = {}
        if criteria.employees_min is not None:
            exact["$gte"] = criteria.employees_min
            interval["employees.max"] = {"$gte": criteria.employees_min}
        if criteria.employees_max is not None:
            exact["$lte"] = criteria.employees_max
            interval["employees.min"] = {"$lte": criteria.employees_max}
        clauses.append({"$or": [{"employees.exact": exact}, {**interval, "employees.exact": {"$exists": False}}]})
    for key, value, operator in (("funding.total_amount_usd", criteria.funding_min, "$gte"), ("funding.total_amount_usd", criteria.funding_max, "$lte"),
        ("funding.last_round.amount_usd", criteria.latest_round_min, "$gte"), ("funding.last_round.amount_usd", criteria.latest_round_max, "$lte"),
        ("founded_year", criteria.founded_min, "$gte"), ("founded_year", criteria.founded_max, "$lte"),
        ("prospect_score", criteria.score_min, "$gte"), ("signals.growth_score", criteria.growth_score_min, "$gte")):
        if value is not None:
            q.setdefault(key, {})[operator] = value
    if criteria.funding_stage:
        q["funding.funding_stage"] = criteria.funding_stage
    if criteria.funded_within_months:
        q.setdefault("funding.last_funding_date", {})["$gte"] = now() - timedelta(days=criteria.funded_within_months * 30)
    if criteria.recently_founded_years:
        q.setdefault("founded_year", {})["$gte"] = now().year - criteria.recently_founded_years
    if criteria.active_company:
        q["company_status"] = {"$in": [re.compile("^active$", re.I), re.compile("^operating$", re.I)]}
    if criteria.growing_headcount:
        q["signals.growing_headcount"] = True
    if criteria.multiple_growth_signals:
        q["signals.multiple_growth_signals"] = True
    if criteria.analytics_opportunity_min is not None:
        q["signals.analytics_opportunity_score"] = {"$gte": criteria.analytics_opportunity_min}
    for field in ("high_transaction_volume", "large_customer_base", "multiple_products", "operational_data_heavy"):
        if getattr(criteria, field):
            q[f"opportunity_evidence.{field}"] = True
    if clauses:
        q["$and"] = clauses
    return q


def list_companies(criteria):
    query = mongo_filter(criteria)
    order = ASCENDING if criteria.order == "asc" else DESCENDING
    sort = criteria.sort if criteria.sort in SORTS else "prospect_score"
    cursor = db().companies.find(query).sort([(sort, order), ("_id", ASCENDING)]).skip((criteria.page - 1) * criteria.page_size).limit(criteria.page_size)
    return {"items": clean(list(cursor)), "total": db().companies.count_documents(query), "page": criteria.page, "page_size": criteria.page_size}


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="ScoutBase API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])


@app.get("/api/health")
def health():
    db().command("ping")
    from .integrations.sec import has_declared_contact
    return {"ok": True, "database": "MongoDB", "sec_enrichment_configured": has_declared_contact(settings.sec_user_agent)}


@app.get("/api/health/providers")
async def health_providers():
    return await provider_status()


@app.get("/api/companies")
def companies(criteria: SearchCriteria = __import__("fastapi").Depends()):
    return list_companies(criteria)


@app.post("/api/companies/search")
def search(criteria: SearchCriteria):
    return list_companies(criteria)


@app.get("/api/companies/{id}")
def company(id: str):
    result = db().companies.find_one({"_id": company_id(id), **mongo_filter(SearchCriteria())})
    if not result:
        raise HTTPException(404, "Company not found")
    return clean(result)


@app.post("/api/companies/discover")
async def discover(criteria: SearchCriteria, tasks: BackgroundTasks):
    if not (criteria.query.strip() or criteria.industry or criteria.country_code or criteria.industries or criteria.countries):
        raise HTTPException(400, "Enter a company name, industry, or country")
    if len(criteria.countries) > 1 or len(criteria.industries) > 1:
        raise HTTPException(400, "External discovery currently supports one country and one industry per run; stored search supports multiple")
    discovery_criteria = criteria.model_copy(update={
        "country_code": criteria.countries[0] if criteria.countries else criteria.country_code,
        "industry": criteria.industries[0] if criteria.industries else criteria.industry,
    })
    criteria_key = json.dumps(criteria.model_dump(exclude={"force_refresh", "page", "page_size", "sort", "order"}), sort_keys=True)
    if not criteria.force_refresh:
        active = db().discovery_jobs.find_one({"criteria_key": criteria_key, "status": {"$in": ["queued", "running"]}},
            sort=[("created_at", DESCENDING)])
        if active:
            return {"job_id": active["_id"], "reused": True}
        recent = db().discovery_jobs.find_one({"criteria_key": criteria_key, "status": "completed", "errors": [],
            "completed_at": {"$gte": now() - timedelta(days=settings.refresh_days)}}, sort=[("completed_at", DESCENDING)])
        if recent:
            return {"job_id": recent["_id"], "reused": True}
    existing = db().companies.count_documents(mongo_filter(criteria))
    if not criteria.force_refresh and existing >= criteria.page_size:
        stale_query = {"$and": [mongo_filter(criteria), {"$or": [
            {"last_verified_at": {"$lt": now() - timedelta(days=settings.refresh_days)}},
            {"last_verified_at": {"$exists": False}},
        ]}]}
        if db().companies.count_documents(stale_query) == 0:
            job_id = str(uuid.uuid4())
            db().discovery_jobs.insert_one({"_id": job_id, "status": "completed", "stage": "Sufficient fresh stored matches",
                "progress": 100, "criteria": criteria.model_dump(), "criteria_key": criteria_key, "existing": existing,
                "found": 0, "valid_candidates": 0, "duplicates": 0, "unique_companies": 0,
                "rejected_candidates": 0, "enriched": 0, "provider_status": {}, "errors": [],
                "created_at": now(), "completed_at": now()})
            return {"job_id": job_id, "reused": True}
    job_id = str(uuid.uuid4())
    db().discovery_jobs.insert_one({"_id": job_id, "status": "queued", "stage": "Queued", "progress": 0,
        "criteria": criteria.model_dump(), "criteria_key": criteria_key, "existing": existing,
        "created_at": now(), "errors": [], "provider_status": {}})
    tasks.add_task(run_discovery, job_id, discovery_criteria)
    return {"job_id": job_id}


@app.get("/api/jobs/{id}")
def job(id: str):
    result = db().discovery_jobs.find_one({"_id": id})
    if not result:
        raise HTTPException(404, "Job not found")
    return clean(result)


@app.post("/api/companies/{id}/enrich")
def enrich(id: str, tasks: BackgroundTasks, force_refresh: bool = False):
    result = db().companies.find_one({"_id": company_id(id), **mongo_filter(SearchCriteria())})
    if not result:
        raise HTTPException(404, "Company not found")
    recent = result.get("last_enriched_at")
    if recent and not force_refresh and recent >= now() - timedelta(days=settings.refresh_days):
        return {"status": "fresh", "last_enriched_at": clean(recent)}
    job_id = str(uuid.uuid4())
    db().discovery_jobs.insert_one({"_id": job_id, "status": "queued", "stage": "Queued", "progress": 0,
        "company_id": id, "created_at": now(), "errors": [], "provider_status": {}})
    tasks.add_task(run_enrichment, job_id, id)
    return {"job_id": job_id}


@app.get("/api/industries")
def industries():
    return sorted(x for x in db().companies.distinct("industry", mongo_filter(SearchCriteria())) if x)


@app.get("/api/countries")
def countries():
    return sorted(x for x in db().companies.distinct("location.country_code", mongo_filter(SearchCriteria())) if x)


@app.get("/api/filter-options")
def filter_options():
    visible = mongo_filter(SearchCriteria())
    collection = db().companies
    industries = sorted(x for x in collection.distinct("industry", visible) if x)
    countries = sorted(x for x in collection.distinct("location.country_code", visible) if x)
    regions = sorted(x for x in collection.distinct("location.region", visible) if x)
    cities = sorted(x for x in collection.distinct("location.city", visible) if x)
    models = sorted(x for x in collection.distinct("business_model", visible) if x)
    funding_stages = sorted(x for x in collection.distinct("funding.funding_stage", visible) if x)
    coverage = {field: collection.count_documents({**visible, field: {"$exists": True, "$ne": None}})
                for field in ("company_status", "signals.growing_headcount", "signals.multiple_growth_signals",
                              "opportunity_evidence.high_transaction_volume", "opportunity_evidence.large_customer_base",
                              "opportunity_evidence.multiple_products", "opportunity_evidence.operational_data_heavy")}
    return {"industries": industries, "countries": countries, "regions": regions, "cities": cities,
            "company_types": models, "funding_stages": funding_stages, "coverage": coverage}


@app.get("/api/saved-companies")
def saved():
    return clean(list(db().saved_companies.find({"user_id": USER_ID}).sort("updated_at", DESCENDING)))


@app.post("/api/saved-companies")
def save(data: SavedInput):
    company_id(data.company_id)
    if not db().companies.find_one({"_id": ObjectId(data.company_id), **mongo_filter(SearchCriteria())}):
        raise HTTPException(404, "Company not found")
    if data.status not in STATUSES or data.priority not in {"low", "medium", "high"}:
        raise HTTPException(400, "Invalid status or priority")
    doc = {**data.model_dump(), "user_id": USER_ID, "updated_at": now()}
    db().saved_companies.update_one({"user_id": USER_ID, "company_id": data.company_id}, {"$set": doc, "$setOnInsert": {"created_at": now()}}, upsert=True)
    return doc


@app.delete("/api/saved-companies/{id}")
def unsave(id: str):
    db().saved_companies.delete_one({"user_id": USER_ID, "company_id": id})
    return {"ok": True}


@app.get("/api/outreach")
def outreach():
    return clean(list(db().outreach.find({"user_id": USER_ID}).sort("updated_at", DESCENDING)))


@app.post("/api/outreach")
def add_outreach(data: OutreachInput):
    company_id(data.company_id)
    if data.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    doc = {**data.model_dump(), "user_id": USER_ID, "created_at": now(), "updated_at": now()}
    inserted = db().outreach.insert_one(doc)
    return clean({**doc, "_id": inserted.inserted_id})


@app.patch("/api/outreach/{id}")
def update_outreach(id: str, data: OutreachInput):
    if data.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    result = db().outreach.find_one_and_update({"_id": company_id(id), "user_id": USER_ID}, {"$set": {**data.model_dump(), "updated_at": now()}}, return_document=True)
    if not result:
        raise HTTPException(404, "Outreach record not found")
    return clean(result)


@app.get("/api/searches")
def searches():
    return clean(list(db().searches.find({"user_id": USER_ID}).sort("created_at", DESCENDING)))


@app.get("/api/searches/{id}")
def get_search(id: str):
    result = db().searches.find_one({"_id": company_id(id), "user_id": USER_ID})
    if not result:
        raise HTTPException(404, "Search not found")
    return clean(result)


@app.post("/api/searches")
def add_search(data: SearchInput):
    doc = {"user_id": USER_ID, "name": data.name, "criteria": data.criteria.model_dump(), "created_at": now()}
    result = db().searches.insert_one(doc)
    return clean({**doc, "_id": result.inserted_id})


@app.delete("/api/searches/{id}")
def delete_search(id: str):
    db().searches.delete_one({"_id": company_id(id), "user_id": USER_ID})
    return {"ok": True}


@app.patch("/api/searches/{id}")
def rename_search(id: str, data: SearchRenameInput):
    result = db().searches.find_one_and_update({"_id": company_id(id), "user_id": USER_ID},
        {"$set": {"name": data.name.strip(), "updated_at": now()}}, return_document=True)
    if not result:
        raise HTTPException(404, "Search not found")
    return clean(result)


@app.get("/api/dashboard")
def dashboard():
    companies = db().companies
    saved = db().saved_companies
    outreach = db().outreach
    visible = mongo_filter(SearchCriteria())
    pipeline = [{"$match": visible}, {"$unwind": "$industry"}, {"$group": {"_id": "$industry", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 8}]
    countries = [{"$match": visible}, {"$group": {"_id": "$location.country_code", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 8}]
    scores = list(companies.aggregate([{"$match": visible}, {"$group": {"_id": None, "average": {"$avg": "$prospect_score"}}}]))
    return {"companies": companies.count_documents(visible), "saved": saved.count_documents({"user_id": USER_ID}),
            "high_potential": companies.count_documents({**visible, "prospect_score": {"$gte": 80}}),
            "recently_funded": companies.count_documents({**visible, "funding.last_funding_date": {"$gte": now() - timedelta(days=730)}}),
            "contacted": outreach.count_documents({"user_id": USER_ID, "status": {"$in": ["contacted", "follow-up", "responded", "interested", "converted"]}}),
            "responses": outreach.count_documents({"user_id": USER_ID, "status": {"$in": ["responded", "interested", "converted"]}}),
            "average_score": round(scores[0]["average"] or 0) if scores else 0,
            "industries": list(companies.aggregate(pipeline)), "countries": list(companies.aggregate(countries))}


EXPORT_COLUMNS = [("Company", lambda c: c.get("name")), ("Website", lambda c: c.get("website")), ("LinkedIn", lambda c: c.get("linkedin_url")),
    ("Country", lambda c: c.get("location", {}).get("country_code")), ("City", lambda c: c.get("location", {}).get("city")),
    ("Industry", lambda c: ", ".join(c.get("industry", []))), ("Employees", lambda c: c.get("employees", {}).get("exact") or c.get("employees", {}).get("min")),
    ("Total Funding USD", lambda c: c.get("funding", {}).get("total_amount_usd")), ("Last Funding", lambda c: c.get("funding", {}).get("last_funding_date")),
    ("Founded", lambda c: c.get("founded_year")), ("Founders", lambda c: ", ".join(p.get("name", "") for p in c.get("founders", []))),
    ("Contact Person", lambda c: (c.get("founders") or c.get("executives") or [{}])[0].get("name")),
    ("Contact LinkedIn", lambda c: (c.get("founders") or c.get("executives") or [{}])[0].get("linkedin_url")),
    ("Prospect Score", lambda c: c.get("prospect_score")), ("Growth Score", lambda c: c.get("signals", {}).get("growth_score")),
    ("Data Intensity", lambda c: c.get("signals", {}).get("data_intensity_score")),
    ("Analytics Opportunity", lambda c: c.get("signals", {}).get("analytics_opportunity_score")),
    ("Prospect Reason", lambda c: "; ".join(c.get("prospect_reason", []))),
    ("Potential Projects", lambda c: "; ".join(c.get("potential_analytics_projects", []))),
    ("Data Confidence", lambda c: c.get("data_confidence")),
    ("Source", lambda c: "; ".join(s.get("source_name", "") for s in c.get("sources", [])))]


def safe_export_cell(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@app.get("/api/export")
def export(format: str = "csv", ids: str = ""):
    selected = [company_id(x) for x in ids.split(",") if x] if ids else []
    query = {**mongo_filter(SearchCriteria()), **({"_id": {"$in": selected}} if selected else {})}
    records = list(db().companies.find(query).limit(10000))
    rows = [[safe_export_cell(getter(c)) for _, getter in EXPORT_COLUMNS] for c in records]
    if format == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Prospects"
        ws.append([name for name, _ in EXPORT_COLUMNS])
        for row in rows:
            ws.append([str(v) if hasattr(v, "isoformat") else v for v in row])
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=prospects.xlsx"})
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([name for name, _ in EXPORT_COLUMNS])
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=prospects.csv"})
