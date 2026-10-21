"""Turn an Upwork job response and its search row into flat facts for the rules.

    f = facts.build(job=get_response, row=search_row, settings=profile_settings)

A fact the inputs don't carry stays None, and a rule that reads it is
reported as unknown rather than passed.
"""
import re
from datetime import datetime, timezone

FACT_NAMES = frozenset("""
job_id title url applied status contract_type hourly_min hourly_max fixed_budget
engagement full_time persons_to_hire invites interviews hired offered
client_hires client_feedback_count client_score client_spend client_hire_rate
client_jobs_posted client_gives_avg client_gives_min same_title_active
connects_cost connects_balance balance_after published_at age_hours proposals
proposals_label skills lane lane_skip_at_proposals rate_floor available_hours
min_balance unmet_qualifications unmet_qualification_count location_excluded
location_preferred_elsewhere
""".split())
TIERS = {"Fewer than 5": 0, "5 to 10": 5, "10 to 15": 10, "15 to 20": 15, "20 to 50": 20, "50+": 50}
FULL_TIME = {"FULL_TIME", "30+ hrs/week"}
ACTIVITY = {
    "invites": "invitesSent", "interviews": "totalInvitedToInterview",
    "hired": "totalHired", "offered": "totalOffered",
}


def build(job=None, row=None, settings=None, now=None, lane=None):
    settings = settings or {}
    f = dict.fromkeys(FACT_NAMES)
    f["skills"] = []
    if row:
        _from_row(f, row)
    quals = _from_job(f, job) if job else None
    _derive(f, settings, quals, now or datetime.now(timezone.utc))
    if job:
        f["location_excluded"], f["location_preferred_elsewhere"] = _location(
            job.get("preferred_locations"), settings.get("country"))
    _lane(f, settings, lane)
    return f


def money(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?", str(value))
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    return amount * {"k": 1e3, "m": 1e6}.get((match.group(2) or "").lower(), 1)


def parse_budget(text):
    """(hourly_min, hourly_max, fixed_budget) from a search row's budget string."""
    if not text:
        return None, None, None
    amounts = [money(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
    if "/hr" not in text:
        return None, None, (amounts[0] if amounts else None)
    if text.lower().startswith("up to"):
        return None, (amounts[0] if amounts else None), None
    if len(amounts) >= 2:
        return amounts[0], amounts[1], None
    return (amounts[0] if amounts else None), None, None


def parse_time(text):
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2})?(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$",
        (text or "").strip())
    if not match:
        return None
    day, hm, sec, frac, zone = match.groups()
    micro = (frac or "0")[:6].ljust(6, "0")
    if zone in (None, "Z"):
        zone = "+00:00"
    elif ":" not in zone:
        zone = zone[:3] + ":" + zone[3:]
    try:
        return datetime.fromisoformat(f"{day}T{hm}{sec or ':00'}.{micro}{zone}")
    except ValueError:
        return None


def unmet_qualifications(quals, mine):
    unmet = []
    jss = money(quals.get("min_job_success_score"))
    if jss and jss > (mine.get("job_success_score") or 0):
        unmet.append(f"Job Success Score {jss:g}%+")
    hours = money(quals.get("min_hours_worked"))
    if hours and hours > (mine.get("hours_worked") or 0):
        unmet.append(f"{hours:g}+ hours worked")
    earned = money(quals.get("min_earnings"))
    if earned and earned > (mine.get("earnings") or 0):
        unmet.append(f"${earned:,.0f}+ earned")
    if quals.get("rising_talent") is True and not mine.get("rising_talent"):
        unmet.append("Rising Talent")
    return unmet


def _from_row(f, row):
    f["job_id"] = str(row["id"]) if row.get("id") else None
    f["title"] = row.get("title")
    f["url"] = row.get("url")
    f["applied"] = bool(row.get("applied"))
    f["published_at"] = row.get("published_date")
    f["skills"] = list(row.get("skills") or [])
    f["engagement"] = row.get("engagement")
    f["connects_cost"] = row.get("connect_price")
    if row.get("job_type"):
        f["contract_type"] = str(row["job_type"]).upper()
    if row.get("proposal_count") is not None:
        f["proposals"] = int(row["proposal_count"])
        f["proposals_label"] = str(f["proposals"])
    elif row.get("proposals_tier") in TIERS:
        f["proposals"] = TIERS[row["proposals_tier"]]
        f["proposals_label"] = row["proposals_tier"]
    f["hourly_min"], f["hourly_max"], f["fixed_budget"] = parse_budget(row.get("budget"))
    client = row.get("client")
    if client is not None:
        f["client_feedback_count"] = client.get("total_reviews") or 0
        f["client_score"] = client.get("rating") if f["client_feedback_count"] else None
        f["client_spend"] = money(client.get("total_spent")) or 0.0
        f["client_jobs_posted"] = client.get("total_posted_jobs")
        f["client_hires"] = client.get("total_hires")


def _from_job(f, job):
    posting = (job.get("data") or {}).get("marketplaceJobPosting") or {}
    terms = posting.get("contractTerms") or {}
    hourly = terms.get("hourlyContractTerms") or {}
    fixed = terms.get("fixedPriceContractTerms") or {}
    activity = (posting.get("activityStat") or {}).get("jobActivity") or {}
    if posting.get("id"):
        f["job_id"] = str(posting["id"])
    f["title"] = (posting.get("content") or {}).get("title") or f["title"]
    f["url"] = posting.get("url") or f["url"]
    if "applied" in job:
        f["applied"] = bool(job["applied"])
    f["status"] = (posting.get("workFlowState") or {}).get("status")
    f["contract_type"] = terms.get("contractType") or f["contract_type"]
    f["persons_to_hire"] = terms.get("personsToHire")
    if hourly:
        f["hourly_min"] = hourly.get("hourlyBudgetMin") or None
        f["hourly_max"] = hourly.get("hourlyBudgetMax") or None
        f["engagement"] = hourly.get("engagementType") or f["engagement"]
    if fixed:
        f["fixed_budget"] = money((fixed.get("amount") or {}).get("rawValue"))
    for name, key in ACTIVITY.items():
        if key in activity:
            f[name] = activity[key]
    if "connects_cost" in job:
        f["connects_cost"] = job["connects_cost"]
    f["connects_balance"] = job.get("connects_balance")
    record = job.get("client_record")
    if record is not None:
        f["client_hires"] = record.get("jobs_with_hires") or 0
        f["client_feedback_count"] = record.get("feedback_count") or 0
        f["client_score"] = record.get("feedback_score") if f["client_feedback_count"] else None
        f["client_spend"] = money(record.get("spend_total")) or 0.0
        f["client_hire_rate"] = record.get("hire_rate_percent")
        f["client_jobs_posted"] = record.get("jobs_posted")
    _history(f, job.get("client_work_history"), record)
    return job.get("preferred_qualifications")


def _history(f, history, record):
    if history is None:
        if record is not None and not record.get("contracts_total"):
            f["same_title_active"] = False
        return
    given = [c["feedback_score"] for c in history.get("closed") or []
             if isinstance(c.get("feedback_score"), (int, float))]
    if given:
        f["client_gives_avg"] = round(sum(given) / len(given), 2)
        f["client_gives_min"] = min(given)
    open_titles = {_norm(c.get("title")) for c in history.get("open") or []}
    f["same_title_active"] = bool(f["title"]) and _norm(f["title"]) in open_titles


def _derive(f, settings, quals, now):
    if f["engagement"] is not None:
        f["full_time"] = f["engagement"] in FULL_TIME
    elif f["contract_type"] == "FIXED":
        f["full_time"] = False
    published = parse_time(f["published_at"]) if f["published_at"] else None
    if published:
        f["age_hours"] = round((now - published).total_seconds() / 3600, 1)
    if f["connects_cost"] is not None and f["connects_balance"] is not None:
        f["balance_after"] = f["connects_balance"] - f["connects_cost"]
    f["rate_floor"] = (settings.get("rates") or {}).get("floor_hourly")
    f["available_hours"] = (settings.get("availability") or {}).get("hours_per_week")
    f["min_balance"] = (settings.get("connects") or {}).get("min_balance")
    if quals is not None:
        f["unmet_qualifications"] = unmet_qualifications(quals, settings.get("qualifications") or {})
        f["unmet_qualification_count"] = len(f["unmet_qualifications"])


def _location(block, country):
    """(excluded, preferred elsewhere) from a get response's preferred_locations, or Nones when it can't be told."""
    if not isinstance(block, dict):
        return False, False
    names = {str(c).strip().lower() for c in block.get("countries") or []}
    elsewhere = any(v for k, v in block.items() if k not in ("countries", "location_required"))
    if not names and not elsewhere:
        return False, False
    if country and country.strip().lower() in names:
        return False, False
    if not country or elsewhere:
        return None, None
    required = bool(block.get("location_required"))
    return required, not required


def _lane(f, settings, chosen):
    lanes = settings.get("lanes") or []
    if chosen:
        match = next((lane for lane in lanes if lane.get("name") == chosen), None)
        if match is None and chosen != "other":
            raise ValueError(f"no lane named {chosen!r} in the profile")
    else:
        match = next((lane for lane in lanes if _in_lane(lane, f["title"] or "", f["skills"])), None)
    f["lane"] = match["name"] if match else "other"
    f["lane_skip_at_proposals"] = match.get("skip_at_proposals") if match else None


def _in_lane(lane, title, skills):
    words = set(_words(title))
    for term in lane.get("title_terms") or []:
        parts = _words(str(term))
        if parts and all(w in words or w + "s" in words for w in parts):
            return True
    wanted = {str(s).lower() for s in lane.get("skills") or []}
    return any(str(s).lower() in wanted for s in skills)


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def _norm(text):
    return " ".join(_words(text or ""))
