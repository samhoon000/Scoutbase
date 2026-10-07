from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO, StringIO
import csv
import json
import uuid
from bson import ObjectId
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pymongo import ASCENDING, DESCENDING
from .config import settings
from .database import db, initialize
from .demo import seed_demo
from .diagnostics import provider_status
from .models import OutreachInput, SavedInput, SearchCriteria, SearchInput, now
from .pipeline import run_discovery

USER_ID = "local-demo-user"  # Replace with authenticated principal in auth middleware.
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
    if criteria.query:
        q["name"] = {"$regex": __import__("re").escape(criteria.query[:100]), "$options": "i"}
    if criteria.country_code:
        q["location.country_code"] = criteria.country_code.upper()
    if criteria.region:
        q["location.region"] = criteria.region
    if criteria.city:
        q["location.city"] = criteria.city
    if criteria.industry:
        q["industry"] = {"$regex": "^" + __import__("re").escape(criteria.industry) + "$", "$options": "i"}
    for key, value, operator in (("employees.max", criteria.employees_min, "$gte"), ("employees.min", criteria.employees_max, "$lte"),
        ("funding.total_amount_usd", criteria.funding_min, "$gte"), ("funding.total_amount_usd", criteria.funding_max, "$lte"),
        ("funding.last_round.amount_usd", criteria.latest_round_min, "$gte"), ("funding.last_round.amount_usd", criteria.latest_round_max, "$lte"),
        ("founded_year", criteria.founded_min, "$gte"), ("founded_year", criteria.founded_max, "$lte"), ("prospect_score", criteria.score_min, "$gte")):
        if value is not None:
            q.setdefault(key, {})[operator] = value
    if criteria.funding_stage:
        q["funding.funding_stage"] = criteria.funding_stage
    if criteria.funded_within_months:
        q.setdefault("funding.last_funding_date", {})["$gte"] = now() - timedelta(days=criteria.funded_within_months * 30)
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
    if settings.demo_mode:
        seed_demo()
    yield


app = FastAPI(title="ProspectIQ API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])


@app.get("/api/health")
def health():
    db().command("ping")
    return {"ok": True, "demo_mode": settings.demo_mode, "database": "MongoDB" if settings.mongodb_uri else "in-memory demo"}


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
    result = db().companies.find_one({"_id": company_id(id)})
    if not result:
        raise HTTPException(404, "Company not found")
    return clean(result)


@app.post("/api/companies/discover")
async def discover(criteria: SearchCriteria, tasks: BackgroundTasks):
    if settings.demo_mode and not settings.mongodb_uri:
        raise HTTPException(400, "Live discovery requires MongoDB. Demo records remain searchable.")
    if not criteria.query.strip():
        raise HTTPException(400, "Enter a company name or keyword for the available free providers")
    job_id = str(uuid.uuid4())
    db().discovery_jobs.insert_one({"_id": job_id, "status": "queued", "stage": "Queued", "progress": 0, "criteria": criteria.model_dump(), "created_at": now(), "errors": []})
    tasks.add_task(run_discovery, job_id, criteria)
    return {"job_id": job_id}


@app.get("/api/jobs/{id}")
def job(id: str):
    result = db().discovery_jobs.find_one({"_id": id})
    if not result:
        raise HTTPException(404, "Job not found")
    return clean(result)


@app.post("/api/companies/{id}/enrich")
def enrich(id: str):
    result = db().companies.find_one({"_id": company_id(id)})
    if not result:
        raise HTTPException(404, "Company not found")
    # Discovery adapters presently provide all fields they can verify. Refresh is a new discovery by legal name.
    return {"message": "Use discovery with the company name to refresh official sources", "last_enriched_at": clean(result.get("last_enriched_at"))}


@app.get("/api/industries")
def industries():
    return sorted(x for x in db().companies.distinct("industry") if x)


@app.get("/api/countries")
def countries():
    return sorted(x for x in db().companies.distinct("location.country_code") if x)


@app.get("/api/saved-companies")
def saved():
    return clean(list(db().saved_companies.find({"user_id": USER_ID}).sort("updated_at", DESCENDING)))


@app.post("/api/saved-companies")
def save(data: SavedInput):
    company_id(data.company_id)
    if not db().companies.find_one({"_id": ObjectId(data.company_id)}):
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


@app.post("/api/searches")
def add_search(data: SearchInput):
    doc = {"user_id": USER_ID, "name": data.name, "criteria": data.criteria.model_dump(), "created_at": now()}
    result = db().searches.insert_one(doc)
    return clean({**doc, "_id": result.inserted_id})


@app.delete("/api/searches/{id}")
def delete_search(id: str):
    db().searches.delete_one({"_id": company_id(id), "user_id": USER_ID})
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard():
    companies = db().companies
    saved = db().saved_companies
    outreach = db().outreach
    pipeline = [{"$unwind": "$industry"}, {"$group": {"_id": "$industry", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 8}]
    countries = [{"$group": {"_id": "$location.country_code", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 8}]
    scores = list(companies.aggregate([{"$group": {"_id": None, "average": {"$avg": "$prospect_score"}}}]))
    return {"companies": companies.count_documents({}), "saved": saved.count_documents({"user_id": USER_ID}),
            "high_potential": companies.count_documents({"prospect_score": {"$gte": 80}}),
            "recently_funded": companies.count_documents({"funding.last_funding_date": {"$gte": now() - timedelta(days=730)}}),
            "contacted": outreach.count_documents({"user_id": USER_ID, "status": {"$in": ["contacted", "follow-up", "responded", "interested", "converted"]}}),
            "responses": outreach.count_documents({"user_id": USER_ID, "status": {"$in": ["responded", "interested", "converted"]}}),
            "average_score": round(scores[0]["average"] or 0) if scores else 0,
            "industries": list(companies.aggregate(pipeline)), "countries": list(companies.aggregate(countries)), "demo_mode": settings.demo_mode}


EXPORT_COLUMNS = [("Company", lambda c: c.get("name")), ("Website", lambda c: c.get("website")), ("LinkedIn", lambda c: c.get("linkedin_url")),
    ("Country", lambda c: c.get("location", {}).get("country_code")), ("City", lambda c: c.get("location", {}).get("city")),
    ("Industry", lambda c: ", ".join(c.get("industry", []))), ("Employees", lambda c: c.get("employees", {}).get("exact") or c.get("employees", {}).get("min")),
    ("Total Funding USD", lambda c: c.get("funding", {}).get("total_amount_usd")), ("Last Funding", lambda c: c.get("funding", {}).get("last_funding_date")),
    ("Founded", lambda c: c.get("founded_year")), ("Founders", lambda c: ", ".join(p.get("name", "") for p in c.get("founders", []))),
    ("Prospect Score", lambda c: c.get("prospect_score")), ("Growth Score", lambda c: c.get("signals", {}).get("growth_score")),
    ("Analytics Opportunity", lambda c: c.get("signals", {}).get("analytics_opportunity_score")),
    ("Prospect Reason", lambda c: "; ".join(c.get("prospect_reason", []))),
    ("Potential Projects", lambda c: "; ".join(c.get("potential_analytics_projects", []))),
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
    query = {"_id": {"$in": selected}} if selected else {}
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
