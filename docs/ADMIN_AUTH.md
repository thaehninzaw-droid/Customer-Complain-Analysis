# Admin authentication & authorization

## The model

Every user document has a `role` field: `"customer"` (default) or
`"admin"`. Login is shared - `POST /auth/login` works for both, the
only difference is what's in the response's `user.role`. The frontend
uses that to decide where to redirect (`activities.html` vs.
`admin-dashboard.html`), but **that's a UX convenience, not the
security boundary**.

The real boundary: every `/admin/*` route in `app/main.py` depends on
`get_current_admin_id`, which:
1. Resolves the bearer token to a real user_id (same as every other
   authenticated route - `get_current_user_id`).
2. Looks up that user's `role` in the database.
3. Returns 403 if it isn't `"admin"`.

So even if someone bypassed the frontend entirely and called
`/admin/complaints` directly with a valid *customer* token, they'd get
a 403. The frontend check and the backend check are independent -
this matters, because relying on "the UI just doesn't show an admin
link" as the only protection is a real, common vulnerability class
(this is in fact very close to the exact IDOR-shaped issue fixed
earlier in this project - see DECISIONS.md #9 - just re-applied to
"is this an admin" instead of "is this your own complaint").

## Why there's no admin signup page

The original SRS PDF explicitly separates "Customer Login / Sign Up"
from "Admin Login **< log in only >**" in the landing-page nav - the
team's own spec calls for admin accounts to not be publicly
self-service. There is no `POST /admin/signup` anywhere, and none of
the frontend admin pages have a signup form.

## How an admin account gets created instead

**Auto-seeding on API startup** (`app/admin_seed.py`,
`ensure_admin_seeded()`, called from `main.py`'s startup hook): every
time the API starts, it checks whether an account with `ADMIN_EMAIL`
exists and creates one with `role="admin"` if not. This is what makes
local development work with zero setup even when using the in-memory
database fallback (no `MONGODB_URI`) - otherwise there'd be no way to
create the very first admin account without a chicken-and-egg problem
(no signup endpoint, no way in).

**Standalone script for real deployments**
(`python -m data.seed_admin`): does the same thing, but as a one-off
script you run yourself against a real MongoDB Atlas connection -
useful because the API's auto-seed-on-startup only touches whichever
database *that process* is currently using, so if you're deploying
against Atlas, you want to seed the admin account there directly too
(running the script with `MONGODB_URI` set in its environment).

Both call the same underlying function, so there's exactly one place
this logic lives.

## Changing the default password

The default demo credentials (`admin@loopline.io` /
`ChangeMe123!`) are placeholders for local development ONLY. Before
deploying anywhere real:
1. Set `ADMIN_EMAIL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` in your real
   `.env` (or your hosting platform's environment variable settings)
   to something real before the API's first startup against that
   database.
2. If an account with the default email already got created (e.g.
   during early local testing against a shared database), either
   delete that user document directly or change `ADMIN_EMAIL` to a
   new address so a fresh one gets seeded.

`ensure_admin_seeded()` never overwrites an existing account's
password - it's idempotent (does nothing) once an account with that
email exists, so changing `ADMIN_PASSWORD` in `.env` after the account
already exists does NOT change that account's password. Update it via
a normal password-change flow if you build one, or drop and re-seed
the user document.

## What's still not built (be upfront about this)

- No password reset flow for admin (or customer) accounts.
- No support for multiple admin permission levels (everyone with
  `role="admin"` can do everything under `/admin/*` - there's no
  "read-only admin" or "supervisor vs. agent" distinction).
- Session tokens don't expire (see DECISIONS.md #9's "still open"
  note - this applies to admin sessions too, arguably with higher
  stakes since an admin token can read/edit every complaint).
- No audit log of who changed what (the SRS's admin Service SOP even
  mentions this: "logged for a supervisor review, separate from the
  customer-facing resolution" - there's no such log in this codebase
  yet, only the SOP document describing the intended process).

These are reasonable "not yet" items for a project at this stage, not
things quietly swept under the rug - see ROADMAP.md.
