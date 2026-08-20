# API Reference

Base URL: `http://127.0.0.1:8000` locally (see `frontend/config.js`).
Interactive docs (Swagger UI) at `/docs` once the server's running -
this file is a companion for reading offline, not a replacement.

Every authenticated endpoint expects `Authorization: Bearer <token>`,
where `<token>` comes from `/auth/signup` or `/auth/login`'s response.

---

## Auth

### `POST /auth/signup`
Body: `{"username": str, "email": str, "password": str}`
→ `201`-ish `AuthResponse`: `{"user": {...}, "token": str}`

Password rules (see `app/auth.py`): 8+ characters, 1 uppercase letter,
1 special character from `!@#$%^&*`.

### `POST /auth/login`
Body: `{"email": str, "password": str}`
→ `AuthResponse`, same shape. Shared by customer and admin login pages
- check `user.role` to know which.

---

## Complaints (customer)

### `POST /complaints` 🔒
Body: `{"complaint": str, "city"?: str, "state"?: str, "zipcode"?: str, "category"?: str, "priority"?: str}`
→ `ComplaintOut`

`category`/`priority` are optional - omit them to let Algorithm 1 /
Algorithm 2 auto-fill. `user_id` is never in the body; it comes from
the bearer token.

Server-side validation (see `app/validation.py`, `docs/DECISIONS.md`
#21/#22) → `400` if either fails:
- `complaint`: 20-1000 characters after trimming whitespace.
- `city`, if sent and non-blank: must match one of the 63 entries in
  `app/cities.py` / `GET /cities` (case-insensitive). Omit it entirely
  to skip this check.

### `GET /complaints` 🔒
→ `ComplaintOut[]` - only the caller's own complaints.

### `GET /categories`
→ `["Billing", "Financial", "Technical", "Service", "Others"]` - single
source of truth, both frontend forms fetch this instead of hardcoding it.

### `GET /cities`
→ `[{"city": str, "state": str, "zip": str}, ...]` (63 entries) - single
source of truth for the Myanmar city → state/zip lookup used by the
complaint form's autocomplete and by the server-side `city` check
above (`app/cities.py`). The frontend doesn't fetch from here yet
(still uses its own hardcoded, identically-sourced copy in
`script.js`'s `MYANMAR_CITIES`) - see `docs/DECISIONS.md` #22.

### `GET /dashboard-stats`
→ `{"total": int, "by_category": {...}, "by_status": {...}, "by_priority": {...}}`
Public aggregate counts, no individual complaint text.

### `GET /issues/pulse`
→ `number[12]`, each 0-100 - powers the homepage "pulse" chart.

---

## Chatbot

### `POST /chatbot/recommend`
Body: `{"complaint_text": str}`
→ `{"category": str, "recommendation": str}`
Used by the homepage's floating chat widget. RAG-backed if
`GEMINI_API_KEY` is set, template fallback otherwise (transparent to
the caller either way).

---

## Admin (all require an admin-role bearer token → 403 otherwise)

### `GET /admin/complaints` 🔒👑
Query params: `category`, `status`, `priority`, `search` (ticket # or
text substring), `page` (default 1), `page_size` (default 25, max 200)
→ `AdminComplaintListOut`: `{"items": ComplaintOut[], "total": int, "page": int, "page_size": int}`

### `POST /admin/complaints` 🔒👑
Body (`AdminComplaintIn`): `{"complaint": str, "city"?, "state"?, "zipcode"?, "category"?, "priority"?, "status"?, "received_via"?}`
→ `ComplaintOut` (with `user_id: 0`, meaning "no linked customer account")

For phone-in / walk-in / manually-logged complaints. `received_via`
defaults to `"Manual Entry"`. Same server-side `complaint`/`city`
validation as `POST /complaints` above, → `400` on failure.

### `PATCH /admin/complaints/{ticket_no}` 🔒👑
Body (`ComplaintUpdate`, all optional): `{"status"?, "category"?, "priority"?}`
→ updated `ComplaintOut`
Only sent fields change. `404` if the ticket doesn't exist, `400` if a
value isn't one of the allowed options.

### `GET /admin/analytics` 🔒👑
→
```json
{
  "total": int,
  "by_category": {...}, "by_status": {...}, "by_priority": {...}, "by_received_via": {...},
  "monthly_volume": [{"month": "2026-07", "count": int}, ...12 entries...],
  "busiest_month": {"month": ..., "count": ...} | null,
  "trend": {"this_month": int, "last_month": int, "delta": int, "delta_pct": float} | null
}
```

### `GET /admin/ml-status` 🔒👑
→
```json
{
  "category_model": {"available": bool, "metrics": {...} | null},
  "priority_model": {"available": bool, "metrics": {...} | null}
}
```
`metrics` is the exact contents of the last training run's
`*_metrics.json` (see docs/ALGORITHMS.md) - `null` if that model
hasn't been trained yet.

### `POST /admin/chatbot/ask` 🔒👑
Body (`AdminChatbotRequest`): `{"question": str, "ticket_no"?: int}`
→ `AdminChatbotResponse`: `{"answer": str, "sources": string[], "used_rag": bool}`

If `ticket_no` is given, that complaint's category/priority/status/
text is pulled in as extra context automatically. `404` if that ticket
doesn't exist.

---

Legend: 🔒 = requires a valid session token (any role). 👑 = requires
`role: "admin"` specifically (403 for a valid customer token).

### `GET /admin/customers` 🔒👑
Query params: `search` (string, optional — matches username or email, case-insensitive), `page` (int, default 1), `page_size` (int, default 20, max 100).

→ `AdminCustomerListOut`:
```json
{
  "items": [
    {
      "user_id": 12,
      "username": "aung_min",
      "email": "aung@example.com",
      "joined": "2026-03-15T08:22:11+00:00",
      "role": "customer",
      "complaint_count": 3
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 20
}
```
Only users with `role == "customer"` are returned. Admin accounts are never exposed here.

### `GET /admin/customers/{user_id}` 🔒👑
→ `AdminCustomerDetailOut`:
```json
{
  "user": { ...AdminCustomerOut fields... },
  "complaints": [ ...ComplaintOut objects, newest first... ]
}
```
`404` if `user_id` does not exist or belongs to an admin account. Password hashes are never included in any response.
