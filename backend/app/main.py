from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .admin_seed import ensure_admin_seeded
from .baseline_cache import get_baseline
from .dataset_seed import ensure_dataset_seeded
from .analytics import compute_analytics
from .auth import AuthError, build_new_user, next_user_id, validate_signup
from .categories import CATEGORIES
from .chatbot import ask_admin_chatbot, get_recommendation
from .cities import MYANMAR_CITIES
from .classify import classify_complaint
from .db import get_collection
from .ml import classifier_model, priority_model
from .models import (
    AdminChatbotRequest,
    AdminChatbotResponse,
    AdminComplaintIn,
    AdminComplaintListOut,
    AdminCustomerDetailOut,
    AdminCustomerListOut,
    AdminCustomerOut,
    AuthResponse,
    ChatbotRequest,
    ComplaintIn,
    ComplaintOut,
    ComplaintUpdate,
    LoginRequest,
    SignupRequest,
    UserOut,
)
from .priority import predict_priority
from .pulse import compute_pulse
from .security import verify_password
from .sessions import create_session, get_user_id_for_token
from .tickets import next_ticket_no
from .validation import ComplaintValidationError, validate_city, validate_complaint_text

YANGON_TZ = timezone(timedelta(hours=6, minutes=30))
VALID_STATUSES = ["Pending", "In Progress", "Resolved", "Closed"]

app = FastAPI(title="Loopline Complaint Classification API")

# Dev-friendly CORS so the frontend (plain HTML/JS) can call this from
# anywhere during development. Tighten allow_origins to the real
# frontend domain before deploying for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _seed_admin_on_startup():
    """Makes sure a demo admin account exists every time the API
    starts - critical for the in-memory DB fallback (no MONGODB_URI),
    since otherwise there'd be no way to log in as an admin without a
    separate manual step. Idempotent against real MongoDB too - see
    app/admin_seed.py."""
    ensure_admin_seeded()
    # Auto-seed the complaints collection from the banking dataset CSV
    # on first startup so the admin dashboard shows real analytics
    # immediately, without any separate data-loading step. Only runs
    # against the in-memory DB (no MONGODB_URI) and only when the
    # collection is empty. See app/dataset_seed.py and
    # docs/DECISIONS.md #26.
    ensure_dataset_seeded()


# ------------------------------------------------------- auth dependencies ----

def get_current_user_id(authorization: str = Header(default=None)) -> int:
    """Reads 'Authorization: Bearer <token>', looks up the session,
    and returns the real user_id behind it. Any endpoint that needs to
    know WHO is calling should depend on this instead of trusting a
    user_id typed into the request body - that's the fix for the IDOR
    issue (see app/sessions.py for the full explanation)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Expected: Bearer <token>",
        )
    token = authorization[len("Bearer "):]
    user_id = get_user_id_for_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    return user_id


def get_current_admin_id(user_id: int = Depends(get_current_user_id)) -> int:
    """Same idea as get_current_user_id, plus a role check. Every
    /admin/* endpoint depends on this instead - a valid customer
    session token is NOT enough to reach admin data, closing the gap
    that used to exist (see docs/ADMIN_AUTH.md for the full writeup:
    this used to be commented as "TEMPORARY / NOT SECURED YET" and now
    isn't)."""
    user = get_collection("users").find_one({"user_id": user_id})
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_id


@app.get("/")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------- auth ----

@app.post("/auth/signup", response_model=AuthResponse)
def signup(req: SignupRequest):
    try:
        validate_signup(req.username, req.email, req.password)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))

    users = list(get_collection("users").find())
    if any(u["email"].lower() == req.email.lower() for u in users):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    new_id = next_user_id([u["user_id"] for u in users])
    # role defaults to "customer" - there is deliberately no way for a
    # caller to request role="admin" here. Admin accounts are seeded
    # server-side only (see app/admin_seed.py) - matches the SRS's
    # "Admin Login <log in only>" (no public admin signup).
    doc = build_new_user(req.username, req.email, req.password, new_id)
    get_collection("users").insert_one(doc)

    token = create_session(doc["user_id"])
    user_out = UserOut(user_id=doc["user_id"], username=doc["username"], email=doc["email"], joined=doc["joined"], role=doc["role"])
    return AuthResponse(user=user_out, token=token)


@app.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Shared by both the customer login page and the admin login
    page - the ONLY difference is what the frontend does with
    `user.role` in the response (redirect to /activities.html vs
    /admin-dashboard.html). The actual admin-data protection happens
    server-side in get_current_admin_id, not here - so even if a
    customer's frontend were tampered with, they still can't reach
    admin endpoints without a real admin account."""
    users = list(get_collection("users").find())
    match = next((u for u in users if u["email"].lower() == req.email.lower()), None)
    if not match or not verify_password(req.password, match["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_session(match["user_id"])
    user_out = UserOut(
        user_id=match["user_id"], username=match["username"], email=match["email"],
        joined=match["joined"], role=match.get("role", "customer"),
    )
    return AuthResponse(user=user_out, token=token)


# ---------------------------------------------------------- complaints ----

def _to_complaint_out(doc: dict) -> ComplaintOut:
    return ComplaintOut(
        ticket_no=doc["ticket_no"],
        user_id=doc["user_id"],
        category=doc["category"],
        priority=doc.get("priority", "Low"),
        complaint=doc["complaint"],
        date_month_year=doc["date_month_year"],
        time=doc["time"],
        city=doc.get("city"),
        state=doc.get("state"),
        zipcode=doc.get("zipcode"),
        status=doc["status"],
        received_via=doc.get("received_via", "Web Form"),
    )


def _jaccard_similarity(a: str, b: str) -> float:
    """Simple Jaccard overlap on word sets after lowercasing.
    Returns a float in [0, 1]. Used by the same-day repeat rule."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _is_repeat_same_day(user_id: int, new_text: str, new_date: str, existing: list) -> bool:
    """Returns True when the same user already filed a complaint on the
    same calendar date AND the new text is substantially similar to at
    least one of those complaints (Jaccard overlap >= 0.7 on word sets,
    OR the normalised texts are an exact match after collapsing whitespace).

    Decision 34: same-user same-day similar complaint -> force High priority.
    Implemented server-side so the rule cannot be bypassed via the frontend.
    """
    new_norm = " ".join(new_text.lower().split())
    same_day = [
        c for c in existing
        if c.get("user_id") == user_id and c.get("date_month_year") == new_date
    ]
    for prev in same_day:
        prev_text = (prev.get("complaint") or "").strip()
        prev_norm = " ".join(prev_text.lower().split())
        if prev_norm == new_norm:
            return True
        if _jaccard_similarity(new_text, prev_text) >= 0.7:
            return True
    return False


@app.post("/complaints", response_model=ComplaintOut)
def create_complaint(complaint: ComplaintIn, user_id: int = Depends(get_current_user_id)):
    """Customer submits complaint text (+ optional city/state/zip).
    user_id comes from the session token, not from the request body -
    a customer can only ever file a complaint as themselves.
    ticket_no, date, time, and status are auto-filled.
    category (Algorithm 1) and priority (Algorithm 2) are auto-predicted
    server-side — the customer form no longer sends category.

    Decision 34: same-user same-day repeat rule — if this user already
    filed a substantially similar complaint today, priority is forced
    to High regardless of the model score. See _is_repeat_same_day()."""
    try:
        validate_complaint_text(complaint.complaint)
        validate_city(complaint.city)
    except ComplaintValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    category = classify_complaint(complaint.complaint)
    priority = predict_priority(complaint.complaint, category)
    now = datetime.now(YANGON_TZ)

    # Use the user-supplied incident date/time if provided and not in the future.
    # Fall back to server now() on any missing value or parse error.
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    if complaint.incident_date:
        try:
            incident_dt = datetime.strptime(
                f"{complaint.incident_date} {complaint.incident_time or '00:00:00'}",
                "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=YANGON_TZ)
            if incident_dt <= now:
                date_str = incident_dt.strftime("%Y-%m-%d")
                time_str = incident_dt.strftime("%H:%M:%S")
        except ValueError:
            pass  # malformed input — fall back to server now()

    collection = get_collection("complaints")
    existing = list(collection.find())

    # Same-user same-day repeat override (Decision 34)
    if _is_repeat_same_day(user_id, complaint.complaint, date_str, existing):
        priority = "High"

    doc = {
        "ticket_no": next_ticket_no([c["ticket_no"] for c in existing]),
        "user_id": user_id,
        "category": category,
        "priority": priority,
        "complaint": complaint.complaint,
        "date_month_year": date_str,
        "time": time_str,
        "city": complaint.city,
        "state": complaint.state,
        "zipcode": complaint.zipcode,
        "status": "Pending",
        "received_via": "Web Form",
    }
    collection.insert_one(doc)
    return _to_complaint_out(doc)


@app.get("/complaints", response_model=List[ComplaintOut])
def list_my_complaints(user_id: int = Depends(get_current_user_id)):
    """Activities page: returns ONLY the logged-in caller's own
    complaints - derived from their token, not a query parameter
    anyone could change."""
    docs = list(get_collection("complaints").find({"user_id": user_id}))
    return [_to_complaint_out(d) for d in docs]


@app.get("/dashboard-stats")
def dashboard_stats():
    """Aggregate counts only (no individual complaint text), so this
    one is left public - there's much less at stake in someone seeing
    'we got 40 billing complaints this month' than in them reading
    another customer's actual complaint."""
    docs = list(get_collection("complaints").find())
    analytics = compute_analytics(docs)
    return {
        "total": analytics["total"],
        "by_category": analytics["by_category"],
        "by_status": analytics["by_status"],
        "by_priority": analytics["by_priority"],
    }


@app.get("/issues/pulse")
def issues_pulse():
    """Matches fetchPulseData()'s expected shape exactly: an array of
    12 numbers, 0-100, one per month."""
    docs = list(get_collection("complaints").find())
    dates = [d["date_month_year"] for d in docs if d.get("date_month_year")]
    return compute_pulse(dates)


@app.get("/categories")
def list_categories():
    """Single source of truth for the category list. Both frontend
    forms fetch from here instead of hardcoding their own <option>
    lists - see docs/FRONTEND_INTEGRATION.md."""
    return CATEGORIES


@app.get("/cities")
def list_cities():
    """Single source of truth for the Myanmar city -> state/zip lookup
    (see app/cities.py) - added so server-side validation (used by
    POST /complaints and POST /admin/complaints) and the frontend's
    own copy in script.js's MYANMAR_CITIES aren't the only two places
    this list can ever be checked against. The frontend doesn't fetch
    from here yet (still uses its own hardcoded copy, generated from
    the exact same source - see docs/DECISIONS.md #22) - a reasonable
    follow-up, not done in this pass."""
    return MYANMAR_CITIES


# --------------------------------------------------------- admin: complaints ----

@app.get("/admin/complaints", response_model=AdminComplaintListOut)
def list_all_complaints_admin(
    admin_id: int = Depends(get_current_admin_id),
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = Query(default=None, description="Matches ticket # (exact) or complaint text (substring, case-insensitive)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
):
    """The admin dashboard's main data table (SRS 3.1.A: 'View
    incoming complaints in real-time', filter by category/ticket ID/
    status). NOW SECURED - this used to be reachable by anyone with no
    auth check at all (see docs/ADMIN_AUTH.md for that history); it's
    behind get_current_admin_id like every other /admin/* route now.

    Filtering/pagination happens in Python after one `.find()`, same
    style as the rest of this small codebase (see pulse.py,
    analytics.py) rather than building Mongo query objects - simple,
    and completely fine at the ~2000-row scale the SRS describes."""
    docs = list(get_collection("complaints").find())

    if category:
        docs = [d for d in docs if d.get("category") == category]
    if status:
        docs = [d for d in docs if d.get("status") == status]
    if priority:
        docs = [d for d in docs if d.get("priority") == priority]
    if search:
        search_lower = search.strip().lower()
        if search.strip().isdigit():
            ticket_match = int(search.strip())
            docs = [d for d in docs if d.get("ticket_no") == ticket_match or search_lower in d.get("complaint", "").lower()]
        else:
            docs = [d for d in docs if search_lower in d.get("complaint", "").lower()]

    docs.sort(key=lambda d: d.get("ticket_no", 0), reverse=True)

    total = len(docs)
    start = (page - 1) * page_size
    page_docs = docs[start:start + page_size]

    return AdminComplaintListOut(
        items=[_to_complaint_out(d) for d in page_docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/admin/complaints/baseline", response_model=AdminComplaintListOut)
def list_baseline_complaints(
    admin_id: int = Depends(get_current_admin_id),
    category: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=200),
):
    """Serves the full banking dataset (12,000 rows) from the CSV file,
    with Algorithm 1 and Algorithm 2 applied to every row, paginated
    and filterable with the same interface as GET /admin/complaints.

    Results are cached in memory after the first call (a few seconds
    to classify all rows on first request, instant thereafter).
    Read-only - rows come from the CSV, not the live database, so
    inline edits are not applied here. See app/baseline_cache.py."""
    rows = get_baseline()

    if category:
        rows = [r for r in rows if r.get("category") == category]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if priority:
        rows = [r for r in rows if r.get("priority") == priority]
    if search:
        sl = search.strip().lower()
        if search.strip().isdigit():
            tn = int(search.strip())
            rows = [r for r in rows if r.get("ticket_no") == tn or sl in r.get("complaint", "").lower()]
        else:
            rows = [r for r in rows if sl in r.get("complaint", "").lower()]

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    return AdminComplaintListOut(
        items=[ComplaintOut(
            ticket_no=r["ticket_no"],
            user_id=r["user_id"],
            complaint=r["complaint"],
            category=r["category"],
            priority=r["priority"],
            status=r["status"],
            date_month_year=r["date_month_year"],
            time=r.get("time", ""),
            city=r.get("city", ""),
            state=r.get("state", ""),
            zipcode=r.get("zipcode", ""),
            received_via=r.get("received_via", "Web Form"),
        ) for r in page_rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.post("/admin/complaints", response_model=ComplaintOut)
def create_complaint_admin(complaint: AdminComplaintIn, admin_id: int = Depends(get_current_admin_id)):
    """Manual entry by an admin (SRS 3.1.A: 'Admin capability to
    manually input complaints, e.g. received via phone call'). Not
    tied to a customer's session/account - user_id is set to 0 to mean
    "no linked customer account" (see models.AdminComplaintIn)."""
    try:
        validate_complaint_text(complaint.complaint)
        validate_city(complaint.city)
    except ComplaintValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    category = complaint.category or classify_complaint(complaint.complaint)
    priority = complaint.priority or predict_priority(complaint.complaint, category)
    now = datetime.now(YANGON_TZ)
    collection = get_collection("complaints")
    existing = list(collection.find())

    doc = {
        "ticket_no": next_ticket_no([c["ticket_no"] for c in existing]),
        "user_id": 0,
        "category": category,
        "priority": priority,
        "complaint": complaint.complaint,
        "date_month_year": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "city": complaint.city,
        "state": complaint.state,
        "zipcode": complaint.zipcode,
        "status": complaint.status or "Pending",
        "received_via": complaint.received_via or "Manual Entry",
    }
    collection.insert_one(doc)
    return _to_complaint_out(doc)


@app.patch("/admin/complaints/{ticket_no}", response_model=ComplaintOut)
def update_complaint_admin(ticket_no: int, patch: ComplaintUpdate, admin_id: int = Depends(get_current_admin_id)):
    """Inline status/category/priority editing from the admin table
    (SRS 3.1.A: 'Edit complaint details', 'Update complaint status').
    Only the fields actually sent get changed."""
    if patch.status is not None and patch.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")
    if patch.category is not None and patch.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")
    if patch.priority is not None and patch.priority not in ["Low", "Medium", "High"]:
        raise HTTPException(status_code=400, detail="priority must be one of ['Low', 'Medium', 'High']")

    collection = get_collection("complaints")
    existing = collection.find_one({"ticket_no": ticket_no})
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No complaint with ticket_no {ticket_no}")

    updates_raw = patch.model_dump(exclude_unset=True) if hasattr(patch, "model_dump") else patch.dict(exclude_unset=True)
    updates = {k: v for k, v in updates_raw.items() if v is not None}
    if updates:
        collection.update_one({"ticket_no": ticket_no}, {"$set": updates})

    updated = collection.find_one({"ticket_no": ticket_no})
    return _to_complaint_out(updated)


@app.get("/admin/analytics")
def admin_analytics(admin_id: int = Depends(get_current_admin_id)):
    """Richer version of /dashboard-stats for the admin charts (SRS
    3.1.C: monthly volume, category distribution, trend analysis) -
    admin-only mainly because it's a natural home for anything more
    detailed added later, not because today's numbers are especially
    sensitive on their own."""
    docs = list(get_collection("complaints").find())
    return compute_analytics(docs)


@app.get("/admin/ml-status")
def admin_ml_status(admin_id: int = Depends(get_current_admin_id)):
    """Lets the admin dashboard show whether Algorithm 1/2 are running
    the trained models or the rule-based fallback, plus the metrics
    from the last training run - see app/ml/train_classifier.py and
    app/ml/train_priority.py. Useful for demoing that these are real
    trained models, not just placeholders."""
    import json
    from pathlib import Path

    artifacts_dir = Path(__file__).resolve().parent / "ml" / "artifacts"

    def _read_metrics(name):
        path = artifacts_dir / name
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    return {
        "category_model": {
            "available": classifier_model.is_available(),
            "metrics": _read_metrics("category_metrics.json"),
        },
        "priority_model": {
            "available": priority_model.is_available(),
            "metrics": _read_metrics("priority_metrics.json"),
        },
    }


# --------------------------------------------------------- admin: customers ----
# Performance model:
#   - Users collection is small (O(100s) rows max for a thesis demo).
#     Full scan is fine; the result is filtered + sorted in Python.
#   - Complaint counts for the list view: one targeted query filtered
#     to the page_ids currently on screen — O(page_size) not O(N).
#   - Detail view: one find({user_id}) — O(user_complaints), no global scan.
#   No ORM, no extra library — consistent with the rest of the codebase.

def _build_customer_out(u: dict, complaint_count: int) -> AdminCustomerOut:
    """Single place that maps a raw users document to AdminCustomerOut,
    so we never accidentally include password_hash or other raw fields."""
    return AdminCustomerOut(
        user_id=u["user_id"],
        username=u["username"],
        email=u["email"],
        joined=u.get("joined", ""),
        role=u.get("role", "customer"),
        complaint_count=complaint_count,
    )


@app.get("/admin/customers", response_model=AdminCustomerListOut)
def list_customers_admin(
    admin_id: int = Depends(get_current_admin_id),
    search: Optional[str] = Query(default=None, description="Match against username or email (case-insensitive)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    # 1. Filter customers only — one pass, never exposes admin rows.
    users = [u for u in get_collection("users").find() if u.get("role") == "customer"]

    if search:
        sl = search.strip().lower()
        users = [u for u in users
                 if sl in u.get("username", "").lower()
                 or sl in u.get("email", "").lower()]

    # Defensive deduplication by user_id.
    # Protects against accidental duplicate documents in MongoDB
    # (no unique index) or rare race conditions during signup.
    seen_ids: set[int] = set()
    unique_users = []
    for u in users:
        uid = u.get("user_id")
        if uid is not None and uid not in seen_ids:
            seen_ids.add(uid)
            unique_users.append(u)
    users = unique_users

    users.sort(key=lambda u: u.get("joined", ""), reverse=True)

    total = len(users)
    start = (page - 1) * page_size
    page_users = users[start:start + page_size]

    # 2. Count complaints only for the users visible on this page.
    #    One targeted query rather than scanning every complaint.
    page_ids = [u["user_id"] for u in page_users]
    counts: dict[int, int] = {uid: 0 for uid in page_ids}
    if page_ids:
        for c in get_collection("complaints").find({"user_id": {"$in": page_ids}}, {"user_id": 1}):
            uid = c.get("user_id")
            if uid in counts:
                counts[uid] += 1

    return AdminCustomerListOut(
        items=[_build_customer_out(u, counts.get(u["user_id"], 0)) for u in page_users],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/admin/customers/{user_id}", response_model=AdminCustomerDetailOut)
def get_customer_admin(user_id: int, admin_id: int = Depends(get_current_admin_id)):
    user = get_collection("users").find_one({"user_id": user_id})
    if not user or user.get("role") != "customer":
        raise HTTPException(status_code=404, detail=f"Customer {user_id} not found.")

    # One targeted query — complaint_count == len(result), no second scan.
    complaints = sorted(
        get_collection("complaints").find({"user_id": user_id}),
        key=lambda c: c.get("ticket_no", 0),
        reverse=True,
    )

    return AdminCustomerDetailOut(
        user=_build_customer_out(user, len(complaints)),
        complaints=[_to_complaint_out(c) for c in complaints],
    )



# ------------------------------------------------------------- chatbot ----

@app.post("/chatbot/recommend")
def chatbot_recommend(req: ChatbotRequest):
    """Customer-facing homepage widget + a quick per-ticket suggestion
    for admins: category in, recommended action out. Tries the real
    RAG pipeline (Gemini + Qdrant) first, falls back to a template if
    it isn't configured - see app/chatbot.py."""
    category = classify_complaint(req.complaint_text)
    recommendation = get_recommendation(req.complaint_text, category)
    return {"category": category, "recommendation": recommendation}


@app.post("/admin/chatbot/ask", response_model=AdminChatbotResponse)
def admin_chatbot_ask(req: AdminChatbotRequest, admin_id: int = Depends(get_current_admin_id)):
    """The Admin AI Chatbot module (SRS 3.2): free-form Q&A grounded
    in the indexed SOP knowledge base (data/knowledge_base/), optionally
    scoped to a specific ticket."""
    ticket_context = None
    if req.ticket_no is not None:
        ticket = get_collection("complaints").find_one({"ticket_no": req.ticket_no})
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"No complaint with ticket_no {req.ticket_no}")
        ticket_context = (
            f"Ticket #{ticket['ticket_no']} | Category: {ticket.get('category')} | "
            f"Priority: {ticket.get('priority')} | Status: {ticket.get('status')}\n"
            f"Complaint text: {ticket.get('complaint')}"
        )

    result = ask_admin_chatbot(req.question, ticket_context=ticket_context)
    return AdminChatbotResponse(**result)
