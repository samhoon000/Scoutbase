from datetime import datetime, timezone

WEIGHTS = {"funding": 20, "growth": 20, "data_intensity": 20, "industry_relevance": 15, "company_size": 15, "analytics_opportunity": 10}
DATA_HEAVY = {"e-commerce", "saas", "fintech", "logistics", "retail", "marketplace", "healthcare", "travel", "edtech", "analytics"}
PROJECTS = {
    "e-commerce": ["Sales dashboard", "Customer segmentation", "Product performance", "Retention analysis", "Marketing analytics"],
    "saas": ["MRR and ARR dashboard", "Churn analysis", "Cohort analysis", "Product usage analytics"],
    "logistics": ["Delivery performance", "Route analysis", "Cost analysis", "Operational dashboards"],
    "retail": ["Store performance", "Inventory analysis", "Revenue forecasting"],
    "fintech": ["Transaction analytics", "Risk dashboard", "Customer segmentation"],
}


def score_company(company: dict, weights: dict | None = None) -> dict:
    weights = weights or WEIGHTS
    industry = {x.casefold() for x in company.get("industry", [])}
    funding = company.get("funding") or {}
    amount = funding.get("total_amount_usd")
    last_date = funding.get("last_funding_date")
    employees = company.get("employees") or {}
    size = employees.get("exact") or employees.get("min")
    relevant = bool(industry & DATA_HEAVY)
    factors = {k: 0 for k in weights}
    reasons = []
    if amount is not None:
        factors["funding"] = round(weights["funding"] * (0.4 if amount < 1_000_000 else 0.7 if amount < 20_000_000 else 1))
        reasons.append(f"Reported funding of ${amount:,.0f}")
    if isinstance(last_date, datetime):
        months = (datetime.now(timezone.utc) - last_date.replace(tzinfo=last_date.tzinfo or timezone.utc)).days / 30.44
        if 0 <= months <= 24:
            factors["growth"] = weights["growth"]
            reasons.append("Funded within the last 24 months")
    if relevant:
        factors["data_intensity"] = round(weights["data_intensity"] * .8)
        factors["industry_relevance"] = weights["industry_relevance"]
        reasons.append(f"{next(iter(industry & DATA_HEAVY)).title()} can generate substantial operational data")
    if size is not None:
        factors["company_size"] = weights["company_size"] if 10 <= size <= 100 else round(weights["company_size"] * .5)
        reasons.append(f"Reported team size starts at {size}")
    projects = list(dict.fromkeys(p for key in industry for p in PROJECTS.get(key, [])))
    if projects:
        factors["analytics_opportunity"] = weights["analytics_opportunity"]
    total = min(100, sum(factors.values()))
    present = sum(bool(company.get(k)) for k in ("website", "description", "founded_year", "founders")) + bool(size is not None) + bool(amount is not None)
    sources = company.get("sources") or []
    reliability = sum(float(s.get("confidence", 0)) for s in sources) / len(sources) if sources else 0
    conflicts = len(company.get("field_conflicts") or [])
    confidence = max(0, min(100, round(
        40 * present / 6 + 40 * reliability + 20 * min(1, len({s.get("source_name") for s in sources}) / 3) - 5 * conflicts)))
    return {"prospect_score": total, "prospect_category": "Excellent" if total >= 80 else "Strong" if total >= 60 else "Emerging" if total >= 35 else "Limited evidence",
            "prospect_reason": reasons, "potential_analytics_projects": projects,
            "signals": {"growth_score": factors["growth"], "funding_score": factors["funding"], "data_intensity_score": factors["data_intensity"], "company_size_score": factors["company_size"], "industry_relevance_score": factors["industry_relevance"], "analytics_opportunity_score": factors["analytics_opportunity"]},
            "source_confidence": round(confidence / 100, 2), "data_confidence": confidence,
            "intelligence_classification": "inferred"}
