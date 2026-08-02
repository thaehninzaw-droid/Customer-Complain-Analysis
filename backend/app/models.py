from typing import List, Optional

from pydantic import BaseModel


# ---- auth ----

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    user_id: int
    username: str
    email: str
    joined: str
    # "customer" (default) or "admin". Safe to expose to the user
    # themselves - it's how the frontend decides whether to show the
    # "Admin Portal" link/redirect after login. The server-side check
    # that actually matters lives in main.py's get_current_admin_id -
    # this field alone grants nothing.
    role: str = "customer"


class AuthResponse(BaseModel):
    """Returned by both /auth/signup and /auth/login.

    `token` must be sent back as `Authorization: Bearer <token>` on
    every request that needs to know who's calling (filing a
    complaint, listing "my" complaints). This is what closes the
    IDOR gap - see app/sessions.py for the why."""
    user: UserOut
    token: str


# ---- complaints ----
# Field names match what script.js already stores client-side:
# ticket_no, category, complaint, date_month_year, time, city, state,
# zipcode, status, user_id.
#
# Note: user_id is NOT part of ComplaintIn anymore. It used to be -
# but that meant a client could just say "I am user 47" in the request
# body with no proof. Now it's derived server-side from the session
# token instead (see get_current_user_id in app/main.py).

class ComplaintIn(BaseModel):
    complaint: str
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    # Leave category/priority unset to let the backend auto-classify/
    # auto-predict (Algorithm 1 / Algorithm 2). Send either to override
    # - keeps today's manual dropdown behavior working too.
    category: Optional[str] = None
    priority: Optional[str] = None


class ComplaintOut(BaseModel):
    ticket_no: int
    user_id: int
    category: str
    priority: str
    complaint: str
    date_month_year: str
    time: str
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    status: str
    # "Web Form" for customer submissions, "Manual Entry" (or a more
    # specific sub-type like "Phone Call") for admin-entered ones -
    # matches the SRS's "received via" dataset column.
    received_via: str = "Web Form"


class ComplaintUpdate(BaseModel):
    """PATCH /admin/complaints/{ticket_no} body - every field optional,
    only the ones sent get changed. This is how the admin dashboard's
    inline status/category/priority editing works (SRS Module 3.1.A:
    'Update complaint status', 'Edit complaint details')."""
    status: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None


class AdminComplaintIn(BaseModel):
    """POST /admin/complaints body - manual entry by an admin (SRS:
    'Admin capability to manually input complaints, e.g. received via
    phone call'). Unlike the customer-facing ComplaintIn, this isn't
    tied to a session's own identity - the admin is filing on behalf
    of someone else, so there's no "user_id" concept here at all;
    those complaints get user_id=0 to mark "no linked customer
    account" (see docs/ADMIN_AUTH.md)."""
    complaint: str
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = "Pending"
    received_via: Optional[str] = "Manual Entry"


class AdminComplaintListOut(BaseModel):
    """Paginated response for GET /admin/complaints - the dataset is
    meant to grow to ~2000+ rows (per the SRS), so this never just
    dumps everything in one response."""
    items: List[ComplaintOut]
    total: int
    page: int
    page_size: int


# ---- chatbot ----

class ChatbotRequest(BaseModel):
    complaint_text: str


class AdminChatbotRequest(BaseModel):
    """POST /admin/chatbot/ask - the Admin AI Chatbot module (SRS 3.2).
    An admin can ask a free-form question, optionally scoped to one
    specific ticket (its text + category get pulled in as context
    automatically)."""
    question: str
    ticket_no: Optional[int] = None


class AdminChatbotResponse(BaseModel):
    answer: str
    sources: List[str] = []
    # True if this came from the real Gemini+Qdrant RAG pipeline,
    # False if it fell back to the template response (no GEMINI_API_KEY
    # configured, or the API call failed) - shown as a small badge in
    # the admin chatbot UI so it's never ambiguous which one answered.
    used_rag: bool = False
