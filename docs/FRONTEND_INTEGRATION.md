# Frontend integration

This used to be a plan for wiring the frontend to a real backend
("here's the code to add"). That work is now done - this doc records
what changed and why, for anyone picking this up later.

## Categories: single source of truth (done)

The category list used to be hardcoded in three places that had
already drifted apart (the survey form, the complaint form, and the
backend classifier). Now there's exactly one: `GET /categories`
(`app/categories.py`). `script.js`'s `populateCategorySelect()` fetches
it once and repopulates both `#s-category` (index.html's survey form)
and `#f-category` (activities.html's complaint form) - the hardcoded
`<option>` lists still in the HTML are just there as a visible
fallback until the fetch completes (or if the API's ever unreachable).

## Auth: real sessions, not localStorage (done)

`auth.js` used to keep a `users` array in `localStorage` and "log in"
by just checking it client-side - no server involved at all, and
nothing stopped anyone from editing that array directly. Now:
`POST /auth/signup` / `POST /auth/login` return `{user, token}`, and
that gets stored in **`sessionStorage`** (not `localStorage`) as
`loopline_session` - clears when the tab closes rather than persisting
indefinitely, which matters more now that the token is a real
credential rather than a cosmetic label. Every authenticated request
sends `Authorization: Bearer <token>` (see `llAuthHeaders()` /
`adminAuthHeaders()`).

## Complaints: server-backed, with a client-side cache (done)

`script.js` keeps an in-memory `llComplaintsCache` array, refreshed via
`llRefreshComplaintsCache()` (calls `GET /complaints`, which the
backend already filters to "my complaints" using the session token).
This exists so the many synchronous helpers that already existed
(`renderComplaintTable`, `updateComplaintStats`,
`findComplaintByTicket`) didn't all need to become `async` individually
- refresh the cache once after any change, read from it everywhere
else, same as before.

## Removed: customer-side complaint editing

The original prototype let a logged-in customer edit their own
complaint's `category` and `status` directly (an "Edit" button + modal
on the Activities page). **This has been removed.** Per the SRS,
editing category/status is explicitly an Admin Dashboard capability
(Module 3.1: "Edit complaint details," "Update complaint status"), not
a Customer Portal one - customers only ever *view* status (the SRS's
"Complaint History & Status Tracking" section describes a read-only
Resolved/Pending indicator, nothing more). The old behavior only
existed because there was no server-side authorization yet to enforce
that distinction; now that there is (see docs/ADMIN_AUTH.md), the
UI limitation matches the intended one. That capability now lives on
`admin-dashboard.html`, backed by `PATCH /admin/complaints/{ticket_no}`.

Customers can also now leave the category field on "Auto-detect" when
filing a complaint, rather than being forced to guess one themselves -
matches the SRS's stated goal of automatic categorization for
customer-submitted complaints. Picking one manually still works too
(sent as an override).

## Admin portal: built from scratch

Nothing existed here before (no admin login page, no dashboard, no
data table, no charts, no chatbot UI) - see ROADMAP.md and
DECISIONS.md for the full history. Now: `admin-login.html`,
`admin-dashboard.html`, `admin-chatbot.html`, sharing `admin.js` for
the auth guard/API helper and each with their own page-specific JS.
Deliberately reuses the existing design tokens/components
(`style.css`) rather than inventing a separate visual style for the
admin side - see the top of the "Admin Portal" section in `style.css`
for the reasoning.

## What's still a client-only demo, on purpose

The homepage's **survey form** and **contact form** (`index.html`)
were left exactly as they were - a client-side "thanks, recorded
(demo)" toast, no backend call. The SRS's actual complaint-management
flow is the Complaint Form on the Customer Portal
(`activities.html`), not this homepage survey; wiring the survey to a
real endpoint wasn't asked for anywhere in the spec, and adding one
felt like scope creep rather than a fix. If the team wants this wired
up later, it'd need a new `POST /survey`-shaped endpoint - nothing
currently reuses `/complaints` for it and it shouldn't, since a survey
response isn't a complaint.
