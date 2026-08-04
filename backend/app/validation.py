"""
Server-side validation for complaint submissions.

Loopline's complaint-length and city checks lived only in
frontend/script.js - real validation, but entirely client-side, so a
direct API call (curl, Postman, a script) could bypass it completely.
A junior team member's example prototype (Myactivities.zip) did this
validation server-side instead - see docs/DECISIONS.md #21/#22. This
module ports the same two checks here, with the same bounds
frontend/script.js already enforces (see isComplaintTextValid() and
the city autocomplete's exact-match check there), so POST /complaints
and POST /admin/complaints reject the same bad input the frontend
already tries to reject, even when the frontend is bypassed entirely.

Deliberately NOT porting frontend's fuzzier heuristics here (the
repeated-character / banned-single-word / "needs 3 real words" junk
detection around isComplaintTextValid() in script.js) - those are
judgment calls appropriate for a UI nudging a live user as they type,
not hard server-side rejections that could reject a legitimate
complaint written in an unusual style. Length and "is this a real
city" are unambiguous; those aren't - see docs/DECISIONS.md #22 for
the reasoning, and if this ever gets revisited, that's the function to
look at on the frontend side.
"""

from typing import Optional

from .cities import CITY_NAMES

MIN_COMPLAINT_LENGTH = 20
MAX_COMPLAINT_LENGTH = 1000


class ComplaintValidationError(Exception):
    """Raised for a complaint-field validation problem. The message is
    written to be safe to show directly to the end user (same
    convention as app.auth.AuthError)."""


def validate_complaint_text(text: str) -> None:
    stripped = (text or "").strip()
    if len(stripped) < MIN_COMPLAINT_LENGTH or len(stripped) > MAX_COMPLAINT_LENGTH:
        raise ComplaintValidationError(
            f"Complaint description must be between {MIN_COMPLAINT_LENGTH} and "
            f"{MAX_COMPLAINT_LENGTH} characters (got {len(stripped)})."
        )


def validate_city(city: Optional[str]) -> None:
    """city is optional on both POST /complaints and POST
    /admin/complaints - only validated if a non-blank value was
    actually sent. Case-insensitive on purpose (stricter than
    frontend's exact-match check) so a technically-valid city isn't
    rejected over casing alone from a direct API call."""
    if not city or not city.strip():
        return
    if city.strip().lower() not in CITY_NAMES:
        raise ComplaintValidationError(
            f"'{city}' isn't a recognized city. Choose one from the list, or leave city blank."
        )
