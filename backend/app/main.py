from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .admin_seed import ensure_admin_seeded
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


@app.post("/complaints", response_model=ComplaintOut)
def create_complaint(complaint: ComplaintIn, user_id: int = Depends(get_current_user_id)):
    """Customer submits complaint text (+ optional city/state/zip).
    user_id comes from the session token, not from the request body -
    a customer can only ever file a complaint as themselves.
    ticket_no, date, time, and status are auto-filled. category
    (Algorithm 1) and priority (Algorithm 2) are auto-predicted UNLESS
    the client sends one (keeps a manual dropdown/override working
    too) - see app/classify.py and app/priority.py."""
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
        "user_id": user_id,
        "category": category,
        "priority": priority,
        "complaint": complaint.complaint,
        "date_month_year": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
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
